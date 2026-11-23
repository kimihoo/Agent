"""知识库与合同访问权限计算。"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Contract, KBPermission, KnowledgeBase, User


def allowed_kb_ids(db: Session, user: User) -> list[int]:
    """当前用户可读取的知识库 ID 列表。"""
    if user.role == "admin":
        return [row.id for row in db.execute(select(KnowledgeBase.id))]

    promoted = user.role in ("hr", "finance", "legal")

    kb_rows = db.execute(select(KnowledgeBase)).scalars().all()
    explicit = db.execute(
        select(KBPermission).where(
            or_(
                (KBPermission.principal_type == "user") & (KBPermission.principal == user.username),
                (KBPermission.principal_type == "role") & (KBPermission.principal == user.role),
                (KBPermission.principal_type == "department") & (KBPermission.principal == user.department),
            )
        )
    ).scalars().all()
    granted = {p.kb_id: p.permission for p in explicit}

    allowed: list[int] = []
    for kb in kb_rows:
        if kb.visibility in ("public", "internal"):
            allowed.append(kb.id)
            continue
        if kb.created_by == user.id or kb.department == user.department:
            allowed.append(kb.id)
            continue
        if kb.id in granted:
            allowed.append(kb.id)
            continue
        # 部门专员可读取自己部门相关库（管理员能力之外的兜底）
        if promoted and kb.department == user.department:
            allowed.append(kb.id)
    return allowed


def can_read_kb(db: Session, user: User, kb_id: int) -> bool:
    return kb_id in allowed_kb_ids(db, user)


def can_write_kb(db: Session, user: User, kb: KnowledgeBase) -> bool:
    if user.role == "admin" or kb.created_by == user.id:
        return True
    grant = db.execute(
        select(KBPermission).where(
            KBPermission.kb_id == kb.id,
            KBPermission.permission == "write",
            or_(
                (KBPermission.principal_type == "user") & (KBPermission.principal == user.username),
                (KBPermission.principal_type == "role") & (KBPermission.principal == user.role),
                (KBPermission.principal_type == "department") & (KBPermission.principal == user.department),
            ),
        )
    ).scalar_one_or_none()
    if grant:
        return True
    return kb.department == user.department and user.role in ("hr", "finance", "legal")


def can_view_contract(user: User, contract: Contract) -> bool:
    return user.role in ("admin", "legal", "finance") or contract.uploaded_by == user.id


def can_review_contract(user: User) -> bool:
    return user.role in ("admin", "legal")
