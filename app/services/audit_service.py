"""Audit logging service for POS Pro."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import AuditLog, User


def log_audit(
    db: Session,
    user: Optional[User],
    action: str,
    details: str,
    ip: Optional[str] = None,
    *,
    commit: bool = True,
) -> None:
    rec = AuditLog(
        user_id=user.id if user else None,
        user_name=user.name if user else "",
        action=action,
        details=details,
        ip=ip,
    )
    db.add(rec)
    if commit:
        db.commit()
