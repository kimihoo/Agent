"""RAG 问答与会话管理（SSE 流式输出）。"""
from __future__ import annotations

import json
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db, session_scope
from ..models import Conversation, Message, User
from ..schemas import ChatRequest
from ..security import get_current_user
from ..services.llm import answer_stream, provider_name
from ..services.permissions import allowed_kb_ids
from ..services.retrieval import Hit, retrieve

router = APIRouter(prefix="/api", tags=["chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def citation_list(hits: list[Hit]) -> list[dict]:
    citations = []
    for index, hit in enumerate(hits, start=1):
        citations.append({
            "index": index,
            "chunk_id": hit.chunk.id,
            "doc_id": hit.chunk.doc_id,
            "doc_title": hit.doc_title,
            "kb_name": hit.kb_name,
            "page": hit.chunk.page,
            "section": hit.chunk.section,
            "snippet": hit.chunk.content[:400],
            "start_char": hit.chunk.start_char,
            "end_char": hit.chunk.end_char,
            "score": round(hit.score, 4),
        })
    return citations


def _prepare(db: Session, user: User, payload: ChatRequest) -> tuple[list[Hit], list[dict], Conversation, int]:
    allowed = allowed_kb_ids(db, user)
    if not allowed:
        raise HTTPException(403, "当前账号没有任何知识库权限")
    kb_ids = [kb_id for kb_id in payload.kb_ids if kb_id in allowed] if payload.kb_ids else allowed
    if not kb_ids:
        raise HTTPException(403, "所选知识库不在你的权限范围内")

    hits = retrieve(db, payload.question, kb_ids)
    citations = citation_list(hits)

    conversation = None
    if payload.conversation_id:
        conversation = db.get(Conversation, payload.conversation_id)
        if not conversation or conversation.user_id != user.id:
            raise HTTPException(404, "会话不存在")
    if conversation is None:
        conversation = Conversation(user_id=user.id, title=payload.question[:40])
        db.add(conversation)
        db.flush()

    db.add(Message(conversation_id=conversation.id, role="user", content=payload.question))
    conversation.updated_at = datetime.now()
    db.commit()
    return hits, citations, conversation, conversation.id


@router.post("/chat/stream")
def chat_stream(payload: ChatRequest, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    start = time.perf_counter()
    hits, citations, _conversation, conversation_id = _prepare(db, user, payload)
    provider = provider_name()
    question = payload.question

    def generate():
        yield _sse("meta", {"conversation_id": conversation_id, "provider": provider,
                            "retrieved": len(hits)})
        yield _sse("citations", {"citations": citations})
        full = ""
        try:
            for token in answer_stream(question, hits):
                full += token
                yield _sse("token", {"text": token})
        except Exception as exc:  # noqa: BLE001
            fallback = f"\n\n（回答生成中断：{exc}）"
            full += fallback
            yield _sse("token", {"text": fallback})

        latency = int((time.perf_counter() - start) * 1000)
        with session_scope() as session:
            message = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=full,
                citations=json.dumps(citations, ensure_ascii=False),
                provider=provider,
                latency_ms=latency,
            )
            session.add(message)
            session.flush()
            message_id = message.id
        yield _sse("done", {"message_id": message_id, "latency_ms": latency, "provider": provider})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/ask")
def chat_ask(payload: ChatRequest, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    start = time.perf_counter()
    hits, citations, _conversation, conversation_id = _prepare(db, user, payload)
    answer = "".join(answer_stream(payload.question, hits))
    latency = int((time.perf_counter() - start) * 1000)
    message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=answer,
        citations=json.dumps(citations, ensure_ascii=False),
        provider=provider_name(),
        latency_ms=latency,
    )
    db.add(message)
    db.commit()
    return {
        "conversation_id": conversation_id,
        "answer": answer,
        "citations": citations,
        "provider": provider_name(),
        "latency_ms": latency,
    }


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.execute(
        select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc())
    ).scalars().all()
    counts = {}
    for row in db.execute(
        select(Message.conversation_id, Message.id).where(
            Message.conversation_id.in_([conv.id for conv in rows])
        )
    ).all():
        counts[row[0]] = counts.get(row[0], 0) + 1
    return [
        {"id": conv.id, "title": conv.title, "updated_at": conv.updated_at.isoformat(),
         "message_count": counts.get(conv.id, 0)}
        for conv in rows
    ]


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(404, "会话不存在")
    messages = db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
    ).scalars().all()
    return {
        "id": conv.id,
        "title": conv.title,
        "messages": [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "citations": json.loads(msg.citations or "[]"),
                "provider": msg.provider,
                "latency_ms": msg.latency_ms,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in messages
        ],
    }


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(404, "会话不存在")
    db.delete(conv)
    db.commit()
    return {"ok": True}
