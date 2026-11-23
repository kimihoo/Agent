"""大模型调用：OpenAI 兼容接口 + 无密钥时的抽取式回答兜底。"""
from __future__ import annotations

import json
import re
from collections.abc import Iterator

import httpx

from ..config import LLM_API_KEY, LLM_BASE_URL, LLM_ENABLED, LLM_MODEL, LLM_TIMEOUT
from .embedding import tokenize
from .retrieval import Hit, _expand_query

SYSTEM_PROMPT = """你是企业「AI 知识库助手」，服务于公司内部员工。
回答规则：
1. 只能依据【参考资料】作答，不得编造制度条款、金额、期限或流程。
2. 用简体中文，条理清晰，优先给结论再给依据。
3. 每个关键结论后用 [编号] 标注来源，例如：年假需提前 3 个工作日申请 [1]。
4. 如果资料不足以回答，明确说明“现有资料未涵盖”，并指出可以咨询的部门。
5. 涉及合同、财务、法务等高风险内容时，提醒以正式文件和人工审核为准。"""


def provider_name() -> str:
    return f"openai:{LLM_MODEL}" if LLM_ENABLED else "local-extractive"


def _context(hits: list[Hit], limit: int = 6500) -> str:
    parts: list[str] = []
    used = 0
    for index, hit in enumerate(hits, start=1):
        block = (
            f"[{index}] 来源：《{hit.doc_title}》"
            f"（知识库：{hit.kb_name}；位置：{hit.chunk.section or '正文'}）\n"
            f"{hit.chunk.content}"
        )
        if used + len(block) > limit:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def _openai_stream(messages: list[dict], temperature: float = 0.2) -> Iterator[str]:
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}
    with httpx.Client(timeout=LLM_TIMEOUT) as client:
        with client.stream(
            "POST",
            f"{LLM_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content") or ""
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta


def chat_completion(messages: list[dict], temperature: float = 0.0) -> str:
    if not LLM_ENABLED:
        raise RuntimeError("未配置大模型")
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}
    with httpx.Client(timeout=LLM_TIMEOUT) as client:
        response = client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


def _best_excerpt(text: str, query: str, width: int = 240) -> str:
    """在切片内定位与问题最相关的句子，并向前后扩展到一段可读原文。"""
    query_words = {word for word in tokenize(_expand_query(query)) if len(word) >= 2}
    sentences = [part for part in re.split(r"(?<=[。；！？\n])", text) if part.strip()]
    if not sentences:
        return text.strip()[:width]
    scores = []
    for sentence in sentences:
        score = sum(2 for word in query_words if word in sentence)
        pairs = set(re.findall(r"[\u4e00-\u9fff]{2}", sentence)) & query_words
        scores.append(score + 0.2 * len(pairs))
    best = max(range(len(sentences)), key=lambda index: scores[index])
    start = end = best
    length = len(sentences[best])
    # 先向前补上下文，保证条目编号、金额等关键信息不被截断，再向后扩展
    while start > 0 and length + len(sentences[start - 1]) <= width * 0.7:
        start -= 1
        length += len(sentences[start])
    while end < len(sentences) - 1 and length + len(sentences[end + 1]) <= width:
        end += 1
        length += len(sentences[end])
    return "".join(sentences[start : end + 1]).strip()[: width + 60]


def _location(hit: Hit) -> str:
    section = hit.chunk.section or "正文"
    if section.startswith(hit.doc_title):
        section = section[len(hit.doc_title):].strip(" /")
    return section or "正文"


def _local_answer(question: str, hits: list[Hit]) -> str:
    if not hits:
        return (
            "现有企业资料中未找到与该问题直接相关的内容。\n\n"
            "建议：确认问题表述是否准确，或在「知识库」中补充相关制度文件；"
            "也可以联系人力资源部或信息中心进一步确认。"
        )
    lines = ["根据企业知识库资料，整理如下：\n"]
    top_score = hits[0].score
    used = 0
    for index, hit in enumerate(hits[:4], start=1):
        if hit.score < top_score * 0.8:
            break
        excerpt = _best_excerpt(hit.chunk.content, question)
        lines.append(f"{index}. 《{hit.doc_title}》{_location(hit)}\n{excerpt} [{index}]\n")
        used += 1
        if used >= 3:
            break
    lines.append(
        "以上内容由检索到的资料自动整理，具体执行请以公司正式发布的制度文件为准；"
        "如涉及合同或资金事项，请提交相关责任部门审核。"
    )
    return "\n".join(lines)


def answer_stream(question: str, hits: list[Hit]) -> Iterator[str]:
    if not LLM_ENABLED:
        yield _local_answer(question, hits)
        return
    if not hits:
        yield _local_answer(question, hits)
        return
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"【参考资料】\n{_context(hits)}\n\n【员工问题】\n{question}",
        },
    ]
    try:
        yield from _openai_stream(messages)
    except Exception:
        yield _local_answer(question, hits)
