"""知识库与文档管理。"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR
from ..db import get_db
from ..models import Chunk, Document, KBPermission, KnowledgeBase, User
from ..schemas import KBIn, KBPermissionIn
from ..security import get_current_user
from ..services.audit import log
from ..services.ingestion import delete_document, ingest_document, parsed_text_path
from ..services.permissions import allowed_kb_ids, can_read_kb, can_write_kb

router = APIRouter(prefix="/api", tags=["knowledge"])

ALLOWED_SUFFIX = {"pdf", "docx", "txt", "md", "markdown"}
MAX_SIZE = 25 * 1024 * 1024


def doc_dict(doc: Document, kb_name: str = "") -> dict:
    return {
        "id": doc.id,
        "kb_id": doc.kb_id,
        "kb_name": kb_name,
        "title": doc.title,
        "filename": doc.filename,
        "size": doc.size,
        "status": doc.status,
        "error": doc.error,
        "page_count": doc.page_count,
        "char_count": doc.char_count,
        "chunk_count": doc.chunk_count,
        "created_at": doc.created_at.isoformat(),
    }


def _kb_or_404(db: Session, kb_id: int) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    return kb


@router.get("/kbs")
def list_kbs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ids = allowed_kb_ids(db, user)
    kbs = db.execute(select(KnowledgeBase).where(KnowledgeBase.id.in_(ids))).scalars().all()
    doc_counts = dict(db.execute(
        select(Document.kb_id, func.count(Document.id)).group_by(Document.kb_id)
    ).all())
    chunk_counts = dict(db.execute(
        select(Chunk.kb_id, func.count(Chunk.id)).group_by(Chunk.kb_id)
    ).all())
    result = []
    for kb in kbs:
        can_write = can_write_kb(db, user, kb)
        result.append({
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "department": kb.department,
            "visibility": kb.visibility,
            "document_count": doc_counts.get(kb.id, 0),
            "chunk_count": chunk_counts.get(kb.id, 0),
            "my_permission": "write" if can_write else "read",
            "updated_at": kb.updated_at.isoformat(),
        })
    result.sort(key=lambda item: item["id"])
    return result


@router.post("/kbs")
def create_kb(payload: KBIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role == "employee":
        raise HTTPException(403, "普通员工不能创建知识库，请联系部门专员或管理员")
    if payload.visibility not in ("public", "internal", "restricted"):
        raise HTTPException(400, "visibility 仅支持 public/internal/restricted")
    kb = KnowledgeBase(
        name=payload.name.strip(),
        description=payload.description.strip(),
        department=payload.department,
        visibility=payload.visibility,
        created_by=user.id,
    )
    db.add(kb)
    db.commit()
    log(db, user.id, "kb.create", "kb", kb.id, kb.name)
    db.commit()
    return {"id": kb.id}


@router.patch("/kbs/{kb_id}")
def update_kb(kb_id: int, payload: KBIn, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    kb = _kb_or_404(db, kb_id)
    if not can_write_kb(db, user, kb):
        raise HTTPException(403, "没有该知识库的写权限")
    kb.name = payload.name.strip()
    kb.description = payload.description.strip()
    kb.department = payload.department
    kb.visibility = payload.visibility
    log(db, user.id, "kb.update", "kb", kb.id, kb.name)
    db.commit()
    return {"ok": True}


@router.delete("/kbs/{kb_id}")
def remove_kb(kb_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kb = _kb_or_404(db, kb_id)
    if user.role != "admin" and kb.created_by != user.id:
        raise HTTPException(403, "只有管理员或创建人可以删除知识库")
    for doc in list(kb.documents):
        Path(doc.stored_path).unlink(missing_ok=True)
        parsed_text_path(doc.id).unlink(missing_ok=True)
    name = kb.name
    db.delete(kb)
    log(db, user.id, "kb.delete", "kb", kb_id, name)
    db.commit()
    return {"ok": True}


@router.get("/kbs/{kb_id}/documents")
def list_documents(kb_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not can_read_kb(db, user, kb_id):
        raise HTTPException(403, "没有该知识库的访问权限")
    kb = _kb_or_404(db, kb_id)
    docs = db.execute(select(Document).where(Document.kb_id == kb_id).order_by(Document.id.desc())).scalars().all()
    return [doc_dict(doc, kb.name) for doc in docs]


@router.post("/kbs/{kb_id}/documents")
def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    title: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = _kb_or_404(db, kb_id)
    if not can_write_kb(db, user, kb):
        raise HTTPException(403, "没有该知识库的写权限")
    filename = file.filename or "未命名文档"
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix not in ALLOWED_SUFFIX:
        raise HTTPException(400, f"仅支持 {', '.join(sorted(ALLOWED_SUFFIX))} 格式")
    data = file.file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(400, "文件超过 25MB 限制")
    if not data:
        raise HTTPException(400, "文件内容为空")

    stored = UPLOAD_DIR / f"{uuid.uuid4().hex}.{suffix}"
    stored.write_bytes(data)
    doc = Document(
        kb_id=kb_id,
        title=(title or filename.rsplit(".", 1)[0]).strip()[:200],
        filename=filename,
        stored_path=str(stored),
        mime=file.content_type or "",
        size=len(data),
        uploaded_by=user.id,
    )
    db.add(doc)
    db.commit()
    ingest_document(db, doc)
    log(db, user.id, "doc.upload", "document", doc.id, f"{doc.title} -> {doc.status}")
    db.commit()
    return doc_dict(doc, kb.name)


@router.post("/documents/{doc_id}/reindex")
def reindex(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    kb = _kb_or_404(db, doc.kb_id)
    if not can_write_kb(db, user, kb):
        raise HTTPException(403, "没有该知识库的写权限")
    ingest_document(db, doc)
    log(db, user.id, "doc.reindex", "document", doc.id, doc.status)
    db.commit()
    return doc_dict(doc, kb.name)


@router.delete("/documents/{doc_id}")
def remove_document(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    kb = _kb_or_404(db, doc.kb_id)
    if not can_write_kb(db, user, kb):
        raise HTTPException(403, "没有该知识库的写权限")
    title = doc.title
    delete_document(db, doc)
    log(db, user.id, "doc.delete", "document", doc_id, title)
    db.commit()
    return {"ok": True}


@router.get("/documents/{doc_id}/text")
def document_text(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    if not can_read_kb(db, user, doc.kb_id):
        raise HTTPException(403, "没有该文档的访问权限")
    path = parsed_text_path(doc.id)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return {"id": doc.id, "title": doc.title, "text": text[:300000], "truncated": len(text) > 300000}


@router.get("/kbs/{kb_id}/permissions")
def list_permissions(kb_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kb = _kb_or_404(db, kb_id)
    if not can_write_kb(db, user, kb):
        raise HTTPException(403, "没有权限")
    rows = db.execute(select(KBPermission).where(KBPermission.kb_id == kb_id)).scalars().all()
    return [
        {"id": row.id, "principal_type": row.principal_type, "principal": row.principal,
         "permission": row.permission}
        for row in rows
    ]


@router.post("/kbs/{kb_id}/permissions")
def add_permission(kb_id: int, payload: KBPermissionIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    kb = _kb_or_404(db, kb_id)
    if not can_write_kb(db, user, kb):
        raise HTTPException(403, "没有权限")
    if payload.principal_type not in ("user", "role", "department"):
        raise HTTPException(400, "principal_type 仅支持 user/role/department")
    existing = db.execute(
        select(KBPermission).where(
            KBPermission.kb_id == kb_id,
            KBPermission.principal_type == payload.principal_type,
            KBPermission.principal == payload.principal,
        )
    ).scalar_one_or_none()
    if existing:
        existing.permission = payload.permission
    else:
        db.add(KBPermission(kb_id=kb_id, **payload.model_dump()))
    log(db, user.id, "kb.grant", "kb", kb_id, f"{payload.principal_type}:{payload.principal}")
    db.commit()
    return {"ok": True}


@router.delete("/kbs/{kb_id}/permissions/{perm_id}")
def remove_permission(kb_id: int, perm_id: int, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    kb = _kb_or_404(db, kb_id)
    if not can_write_kb(db, user, kb):
        raise HTTPException(403, "没有权限")
    perm = db.get(KBPermission, perm_id)
    if perm and perm.kb_id == kb_id:
        db.delete(perm)
        db.commit()
    return {"ok": True}
