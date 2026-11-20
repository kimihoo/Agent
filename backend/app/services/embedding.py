"""向量化：优先调用 OpenAI 兼容 Embedding 接口，未配置时使用本地哈希向量兜底。"""
from __future__ import annotations

import hashlib
import math
import re

import httpx
import jieba
import numpy as np

from ..config import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_DIM,
    EMBEDDING_ENABLED,
    EMBEDDING_MODEL,
)

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9_]+")
STOPWORDS = {
    "的", "了", "和", "与", "及", "或", "在", "是", "为", "对", "中", "上", "下",
    "我们", "公司", "可以", "需要", "进行", "以及", "等", "按", "按照", "关于",
}


def tokenize(text: str) -> list[str]:
    """中文分词 + 英文/数字词 + 中文二元组，用于 BM25 与本地向量。"""
    text = text.lower()
    words = [
        w.strip()
        for w in jieba.lcut(text)
        if w.strip() and w not in STOPWORDS and _TOKEN_RE.search(w)
    ]
    compact = re.sub(r"\s+", "", text)
    bigrams = [
        compact[i : i + 2]
        for i in range(len(compact) - 1)
        if _TOKEN_RE.search(compact[i]) and _TOKEN_RE.search(compact[i + 1])
    ]
    return words + bigrams


def _hash_embedding(text: str, dim: int) -> np.ndarray:
    vector = np.zeros(dim, dtype=np.float32)
    tokens = tokenize(text)
    if not tokens:
        return vector
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    for token, count in counts.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "little")
        index = value % dim
        sign = 1.0 if (value >> 63) & 1 else -1.0
        vector[index] += sign * (1.0 + math.log(count))
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector /= norm
    return vector


def _openai_embeddings(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    with httpx.Client(timeout=60) as client:
        for start in range(0, len(texts), 64):
            batch = texts[start : start + 64]
            response = client.post(
                f"{EMBEDDING_BASE_URL}/embeddings",
                headers={"Authorization": f"Bearer {EMBEDDING_API_KEY}"},
                json={"model": EMBEDDING_MODEL, "input": batch},
            )
            response.raise_for_status()
            data = response.json()["data"]
            vectors.extend([item["embedding"] for item in data])
    return vectors


def embed_texts(texts: list[str]) -> list[np.ndarray]:
    if not texts:
        return []
    if EMBEDDING_ENABLED:
        try:
            raw = _openai_embeddings(texts)
            result = []
            for vector in raw:
                arr = np.asarray(vector, dtype=np.float32)
                norm = np.linalg.norm(arr)
                result.append(arr / norm if norm else arr)
            return result
        except Exception:
            pass  # 网络或额度异常时退回本地向量，保证服务可用
    return [_hash_embedding(text, EMBEDDING_DIM) for text in texts]


def embed_query(text: str) -> np.ndarray:
    return embed_texts([text])[0]


def to_bytes(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_bytes(blob: bytes | None) -> np.ndarray | None:
    if not blob:
        return None
    return np.frombuffer(blob, dtype=np.float32)


def backend_name() -> str:
    return f"openai:{EMBEDDING_MODEL}" if EMBEDDING_ENABLED else f"local-hash:{EMBEDDING_DIM}"
