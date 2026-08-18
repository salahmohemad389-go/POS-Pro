"""Audit log routes for POS Pro."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from app.db.models import AuditLog
from app.db.session import get_db
from app.core.security import get_current_user
from app.core.permissions import has_permission
from app.db.models import User
from app.services.audit_service import log_audit

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
async def list_audit(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    q: Optional[str] = None,
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not has_permission(user, "audit_view"):
        raise HTTPException(403, "لا تملك صلاحية")
    query = db.query(AuditLog)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(AuditLog.action.ilike(like), AuditLog.details.ilike(like), AuditLog.user_name.ilike(like)))
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if date_from:
        try:
            query = query.filter(AuditLog.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(AuditLog.created_at <= datetime.fromisoformat(date_to))
        except ValueError:
            pass
    total = query.count()
    items = query.order_by(desc(AuditLog.created_at)).offset((page - 1) * limit).limit(limit).all()
    return {
        "total": total,
        "items": [
            {"id": a.id, "user_name": a.user_name or "", "action": a.action, "details": a.details or "", "ip": a.ip, "created_at": a.created_at.isoformat() if a.created_at else None}
            for a in items
        ],
    }


@router.get("/actions")
async def list_audit_actions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "audit_view"):
        raise HTTPException(403, "لا تملك صلاحية")
    actions = db.query(AuditLog.action).distinct().all()
    return sorted([a[0] for a in actions if a[0]])


@router.delete("")
async def clear_audit(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "audit_clear"):
        raise HTTPException(403, "صلاحية المدير مطلوبة")
    try:
        db.query(AuditLog).delete()
        log_audit(db, user, "audit_clear", "مسح السجل", request.client.host if request else None, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر مسح سجل التدقيق")
    return {"ok": True}
