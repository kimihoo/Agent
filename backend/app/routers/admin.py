"""系统管理：用户、审计日志、运行状态。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import LLM_ENABLED
from ..db import get_db
from ..models import AuditLog, Chunk, Contract, Document, KnowledgeBase, User
from ..schemas import UserIn, UserPatch
from ..security import get_current_user, hash_password, require_admin
from ..services.audit import log
from ..services.embedding import backend_name
from ..services.llm import provider_name

router = APIRouter(prefix="/api", tags=["admin"])

ROLES = {"admin", "hr", "finance", "legal", "employee"}


def user_row(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "department": user.department,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
    }


@router.get("/users")
def list_users(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return [user_row(user) for user in db.execute(select(User).order_by(User.id)).scalars()]


@router.post("/users")
def create_user(payload: UserIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if payload.role not in ROLES:
        raise HTTPException(400, "角色不合法")
    if db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none():
        raise HTTPException(400, "用户名已存在")
    user = User(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        department=payload.department,
        role=payload.role,
    )
    db.add(user)
    log(db, admin.id, "user.create", "user", payload.username, payload.role)
    db.commit()
    return {"id": user.id}


@router.patch("/users/{user_id}")
def update_user(user_id: int, payload: UserPatch, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    if payload.role is not None:
        if payload.role not in ROLES:
            raise HTTPException(400, "角色不合法")
        user.role = payload.role
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    if payload.department is not None:
        user.department = payload.department
    if payload.is_active is not None:
        if user.id == admin.id and not payload.is_active:
            raise HTTPException(400, "不能停用当前登录账号")
        user.is_active = payload.is_active
    if payload.password:
        user.password_hash = hash_password(payload.password)
    log(db, admin.id, "user.update", "user", user.id, "role=%s active=%s" % (user.role, user.is_active))
    db.commit()
    return {"ok": True}


@router.get("/audit-logs")
def audit_logs(limit: int = 100, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    rows = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500))).scalars().all()
    names = {user.id: user.display_name for user in db.execute(select(User)).scalars()}
    return [
        {
            "id": row.id,
            "actor": names.get(row.actor_id, "系统"),
            "action": row.action,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "detail": row.detail,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/system/status")
def system_status(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    contract_counts = dict(db.execute(
        select(Contract.status, func.count(Contract.id)).group_by(Contract.status)
    ).all())
    return {
        "llm": provider_name(),
        "llm_enabled": LLM_ENABLED,
        "embedding": backend_name(),
        "stats": {
            "users": db.scalar(select(func.count(User.id))) or 0,
            "knowledge_bases": db.scalar(select(func.count(KnowledgeBase.id))) or 0,
            "documents": db.scalar(select(func.count(Document.id))) or 0,
            "chunks": db.scalar(select(func.count(Chunk.id))) or 0,
            "contracts": db.scalar(select(func.count(Contract.id))) or 0,
            "contracts_pending": contract_counts.get("pending_review", 0)
            + contract_counts.get("needs_changes", 0),
        },
    }
