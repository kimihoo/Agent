"""混合检索：BM25 稀疏检索 + 向量语义检索，RRF 融合并按文档去重。"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import EMBEDDING_ENABLED, RETRIEVAL_TOP_K
from ..models import Chunk, Document, KnowledgeBase
from .embedding import embed_query, from_bytes, tokenize


@dataclass
class Hit:
    chunk: Chunk
    doc_title: str
    kb_name: str
    score: float
    bm25: float
    dense: float


_lock = threading.Lock()
_token_cache: dict[int, list[str]] = {}
_index_state: dict = {"key": None, "df": {}, "avgdl": 1.0, "tokens": {}}

# 企业常见同义词扩展，缓解“年假/年休假”“账期/付款期限”这类表述差异
QUERY_SYNONYMS = {
    "年假": ["年休假", "带薪休假"],
    "请假": ["休假", "假期", "审批"],
    "出差": ["差旅"],
    "住宿": ["住宿费"],
    "报销": ["费用报销"],
    "付款": ["支付"],
    "账期": ["付款期限", "支付期限"],
    "违约": ["违约责任", "赔偿"],
    "保密": ["保密义务"],
}


def _expand_query(query: str) -> str:
    extra: list[str] = []
    for word, synonyms in QUERY_SYNONYMS.items():
        if word in query:
            extra.extend(synonyms)
    return " ".join([query, *extra])


def _build_index(chunks: list[Chunk]) -> tuple[dict[str, int], float, dict[int, list[str]]]:
    key = (len(chunks), max((c.id for c in chunks), default=0))
    with _lock:
        if _index_state["key"] == key:
            return _index_state["df"], _index_state["avgdl"], _index_state["tokens"]
        df: dict[str, int] = {}
        tokens_by_id: dict[int, list[str]] = {}
        total_len = 0
        for chunk in chunks:
            tokens = _token_cache.get(chunk.id)
            if tokens is None:
                tokens = tokenize(f"{chunk.section} {chunk.content}")
                _token_cache[chunk.id] = tokens
            tokens_by_id[chunk.id] = tokens
            total_len += len(tokens)
            for token in set(tokens):
                df[token] = df.get(token, 0) + 1
        avgdl = total_len / len(chunks) if chunks else 1.0
        _index_state.update(key=key, df=df, avgdl=avgdl, tokens=tokens_by_id)
        return df, avgdl, tokens_by_id


def _bm25_scores(query_tokens: list[str], chunks: list[Chunk], df: dict[str, int], avgdl: float,
                 tokens_by_id: dict[int, list[str]]) -> dict[int, float]:
    n = len(chunks)
    k1, b = 1.2, 0.75
    scores: dict[int, float] = {}
    for chunk in chunks:
        tokens = tokens_by_id[chunk.id]
        if not tokens:
            continue
        length = len(tokens)
        tf: dict[str, int] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        score = 0.0
        for token in set(query_tokens):
            freq = tf.get(token)
            if not freq:
                continue
            doc_freq = df.get(token, 0)
            idf = math.log(1 + (n - doc_freq + 0.5) / (doc_freq + 0.5))
            score += idf * freq * (k1 + 1) / (freq + k1 * (1 - b + b * length / avgdl))
        if score > 0:
            scores[chunk.id] = score
    return scores


def retrieve(db: Session, query: str, kb_ids: list[int], top_k: int = RETRIEVAL_TOP_K) -> list[Hit]:
    if not kb_ids or not query.strip():
        return []

    rows = db.execute(
        select(Chunk, Document.title, KnowledgeBase.name)
        .join(Document, Chunk.doc_id == Document.id)
        .join(KnowledgeBase, Chunk.kb_id == KnowledgeBase.id)
        .where(Chunk.kb_id.in_(kb_ids), Document.status == "ready")
    ).all()
    chunks = [row[0] for row in rows]
    if not chunks:
        return []

    meta = {row[0].id: (row[1], row[2]) for row in rows}
    expanded = _expand_query(query)
    query_tokens = tokenize(expanded)
    df, avgdl, tokens_by_id = _build_index(chunks)
    bm25 = _bm25_scores(query_tokens, chunks, df, avgdl, tokens_by_id)

    dense: dict[int, float] = {}
    query_vector = embed_query(expanded)
    for chunk in chunks:
        vector = from_bytes(chunk.embedding)
        if vector is None or vector.shape != query_vector.shape:
            continue
        similarity = float(np.dot(query_vector, vector))
        dense[chunk.id] = similarity

    bm25_max = max(bm25.values(), default=0.0)
    dense_max = max(dense.values(), default=0.0)
    if bm25_max <= 0 and dense_max <= 0:
        return []

    candidates = {cid for cid, value in bm25.items() if value >= bm25_max * 0.25}
    if EMBEDDING_ENABLED and dense_max > 0:
        candidates |= {cid for cid, value in dense.items() if value >= max(0.25, dense_max * 0.6)}
    if not candidates:
        return []

    fused: dict[int, float] = {}
    for cid in candidates:
        bm25_part = bm25.get(cid, 0.0) / bm25_max if bm25_max else 0.0
        dense_part = max(dense.get(cid, 0.0), 0.0) / dense_max if dense_max else 0.0
        if EMBEDDING_ENABLED:
            fused[cid] = 0.55 * bm25_part + 0.45 * dense_part
        else:
            # 本地哈希向量仅用于同分排序微调，检索排序以 BM25 为主
            fused[cid] = 0.85 * bm25_part + 0.15 * dense_part

    ranked = sorted(fused.items(), key=lambda item: item[1], reverse=True)
    best = ranked[0][1]
    if best <= 0:
        return []
    by_id = {chunk.id: chunk for chunk in chunks}

    hits: list[Hit] = []
    per_doc: dict[int, int] = {}
    for cid, score in ranked:
        if score < best * 0.45:
            break
        chunk = by_id[cid]
        if per_doc.get(chunk.doc_id, 0) >= 2:
            continue
        per_doc[chunk.doc_id] = per_doc.get(chunk.doc_id, 0) + 1
        title, kb_name = meta[cid]
        hits.append(
            Hit(
                chunk=chunk,
                doc_title=title,
                kb_name=kb_name,
                score=score,
                bm25=bm25.get(cid, 0.0),
                dense=dense.get(cid, 0.0),
            )
        )
        if len(hits) >= top_k:
            break
    return hits
