"""User management routes for POS Pro."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.ratelimit import consume_attempt
from app.core.security import get_current_user, hash_password, validate_password
from app.core.permissions import has_permission
from app.db.models import User
from app.db.session import get_db
from app.services.audit_service import log_audit
from app.schemas.requests import UserSave

router = APIRouter(prefix="/api/users", tags=["users"])


def _rate_limit_or_403(key: str, limit_type: str):
    from fastapi import status
    allowed, remaining = consume_attempt(key, limit_type)
    if not allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"تجاوزت الحد المسموح. حاول بعد {remaining // 60 + 1} دقيقة")


@router.get("")
async def list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "user_view"):
        raise HTTPException(403, "لا تملك صلاحية")
    return [
        {"id": u.id, "name": u.name, "login": u.login, "role": u.role, "active": u.active, "created_at": u.created_at.isoformat() if u.created_at else None}
        for u in db.query(User).order_by(User.name).all()
    ]


@router.post("")
async def save_user(payload: UserSave, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _rate_limit_or_403(f"user_write:{user.id}", "write")
    if not has_permission(user, "user_save"):
        raise HTTPException(403, "صلاحية المدير مطلوبة")
    data = payload.model_dump()
    uid = data.get("id")
    name = data["name"].strip()
    login_ = data["login"].strip()
    role = data["role"]
    password = data.get("password") or ""
    if not name or not login_:
        raise HTTPException(400, "الاسم واسم الدخول مطلوبان")
    if role not in ("admin", "manager", "cashier"):
        raise HTTPException(400, "دور غير صحيح")
    if uid:
        u = db.query(User).filter(User.id == uid).first()
        if not u:
            raise HTTPException(404, "مستخدم غير موجود")
        existing = db.query(User).filter(User.login == login_, User.id != uid).first()
        if existing:
            raise HTTPException(400, "اسم الدخول مستخدم")
        if u.role == "admin" and role != "admin" and u.active:
            active_admins = db.query(User).filter(User.role == "admin", User.active.is_(True)).count()
            if active_admins <= 1:
                raise HTTPException(409, "لا يمكن خفض صلاحية آخر مدير فعّال")
        changed_security = (u.role != role)
        u.name = name
        u.login = login_
        u.role = role
        if password:
            try: validate_password(password)
            except ValueError as exc: raise HTTPException(400, str(exc))
            u.password_hash = hash_password(password)
            changed_security = True
        if changed_security:
            u.token_version = int(u.token_version or 0) + 1
    else:
        if not password:
            raise HTTPException(400, "كلمة المرور مطلوبة لمستخدم جديد")
        try: validate_password(password)
        except ValueError as exc: raise HTTPException(400, str(exc))
        existing = db.query(User).filter(User.login == login_).first()
        if existing:
            raise HTTPException(400, "اسم الدخول مستخدم")
        u = User(name=name, login=login_, role=role, password_hash=hash_password(password), active=True)
        db.add(u)
    try:
        log_audit(db, user, "user_save", f"{'تعديل' if uid else 'إضافة'} مستخدم: {name}", request.client.host if request else None, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر حفظ المستخدم")
    return {"ok": True, "id": u.id}


@router.delete("/{uid}")
async def delete_user(uid: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "delete_user"):
        raise HTTPException(403, "صلاحية المدير مطلوبة")
    if uid == user.id:
        raise HTTPException(400, "لا يمكنك تعطيل نفسك")
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(404, "مستخدم غير موجود")
    if u.role == "admin" and u.active:
        active_admins = db.query(User).filter(User.role == "admin", User.active.is_(True)).count()
        if active_admins <= 1:
            raise HTTPException(409, "لا يمكن تعطيل آخر مدير فعّال")
    name = u.name
    u.active = False
    u.token_version = int(u.token_version or 0) + 1
    try:
        log_audit(db, user, "user_disable", f"تعطيل: {name}", request.client.host if request else None, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر تعطيل المستخدم")
    return {"ok": True}

