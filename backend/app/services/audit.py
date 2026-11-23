"""审计日志。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AuditLog


def log(db: Session, actor_id: int | None, action: str, target_type: str = "",
        target_id: str | int = "", detail: str = "") -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            detail=detail[:2000],
        )
    )
