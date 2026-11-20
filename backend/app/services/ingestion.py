"""文档入库流水线：解析 -> 切片 -> 向量化 -> 落库。"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..config import PARSED_DIR
from ..models import Chunk, Document
from .chunker import chunk_document
from .embedding import embed_texts, to_bytes
from .parser import parse_file


def parsed_text_path(doc_id: int) -> Path:
    return PARSED_DIR / f"{doc_id}.txt"


def ingest_document(db: Session, doc: Document) -> Document:
    """同步解析并索引文档；失败时记录错误但保留文件便于重试。"""
    doc.status = "pending"
    doc.error = ""
    db.flush()

    try:
        parsed = parse_file(Path(doc.stored_path), doc.filename)
    except Exception as exc:  # noqa: BLE001
        doc.status = "failed"
        doc.error = f"解析失败：{exc}"
        db.commit()
        return doc

    parsed_text_path(doc.id).write_text(parsed.full_text, encoding="utf-8")
    chunks = chunk_document(parsed)
    if not chunks:
        doc.status = "failed"
        doc.error = "文档解析后没有可索引的正文内容"
        db.commit()
        return doc

    db.execute(delete(Chunk).where(Chunk.doc_id == doc.id))
    vectors = embed_texts([f"{chunk.section} {chunk.content}" for chunk in chunks])

    for seq, (chunk, vector) in enumerate(zip(chunks, vectors)):
        db.add(
            Chunk(
                doc_id=doc.id,
                kb_id=doc.kb_id,
                seq=seq,
                content=chunk.content,
                page=chunk.page,
                section=chunk.section,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                token_count=chunk.token_count,
                embedding=to_bytes(vector),
            )
        )

    doc.page_count = parsed.page_count
    doc.char_count = len(parsed.full_text)
    doc.chunk_count = len(chunks)
    doc.status = "ready"
    doc.error = ""
    db.commit()
    return doc


def delete_document(db: Session, doc: Document) -> None:
    Path(doc.stored_path).unlink(missing_ok=True)
    parsed_text_path(doc.id).unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
