"""User management routes for POS Pro."""

from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.ratelimit import consume_attempt
from app.core.security import get_current_user, hash_password, validate_password
from app.core.permissions import get_user_permissions, has_permission
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


def _visible_user_dict(actor: User, u: User) -> dict:
    data = {
        "id": u.id,
        "name": u.name,
        "login": u.login,
        "role": u.role,
        "active": bool(u.active),
        "is_owner": bool(getattr(u, "is_owner", False)),
        "expires_at": u.expires_at.isoformat() if getattr(u, "expires_at", None) else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "effective_permissions": sorted(get_user_permissions(u)),
    }
    if bool(getattr(actor, "is_owner", False)):
        data["permissions"] = u.permissions
    return data


def _assert_manageable(actor: User, target: User) -> None:
    if bool(getattr(target, "is_owner", False)) and target.id != actor.id:
        raise HTTPException(403, "حساب المالك الرئيسي محمي")
    if not bool(getattr(actor, "is_owner", False)) and target.role == "admin" and target.id != actor.id:
        raise HTTPException(403, "لا يمكنك إدارة حساب مدير آخر")


@router.get("")
async def list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "user_view"):
        raise HTTPException(403, "لا تملك صلاحية")
    query = db.query(User)
    if not bool(getattr(user, "is_owner", False)):
        query = query.filter(User.is_owner.is_(False))
    rows = query.order_by(User.name, User.id).all()
    return [_visible_user_dict(user, u) for u in rows]


@router.post("")
async def save_user(payload: UserSave, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _rate_limit_or_403(f"user_write:{user.id}", "write")
    if not has_permission(user, "user_save"):
        raise HTTPException(403, "صلاحية إدارة المستخدمين مطلوبة")

    data = payload.model_dump()
    uid = data.get("id")
    name = data["name"].strip()
    login_ = data["login"].strip()
    role = data["role"]
    password = data.get("password") or ""
    active = bool(data.get("active", True))
    expires_at = data.get("expires_at")
    if expires_at is not None and expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
    permissions = data.get("permissions")

    if not name or not login_:
        raise HTTPException(400, "الاسم واسم الدخول مطلوبان")
    if role not in ("admin", "manager", "cashier"):
        raise HTTPException(400, "دور غير صحيح")
    if not bool(getattr(user, "is_owner", False)) and role == "admin" and (not uid or int(uid) != user.id):
        raise HTTPException(403, "إنشاء أو ترقية مدير جديد متاح للمالك الرئيسي فقط")
    if permissions is not None and not bool(getattr(user, "is_owner", False)):
        raise HTTPException(403, "تخصيص الصلاحيات متاح للمالك الرئيسي فقط")

    if uid:
        u = db.query(User).filter(User.id == uid).first()
        if not u:
            raise HTTPException(404, "مستخدم غير موجود")
        _assert_manageable(user, u)
        if bool(getattr(u, "is_owner", False)):
            if role != "admin":
                raise HTTPException(409, "لا يمكن تخفيض صلاحية المالك الرئيسي")
            if not active:
                raise HTTPException(409, "لا يمكن تعطيل المالك الرئيسي")
            if expires_at is not None:
                raise HTTPException(409, "لا يمكن وضع تاريخ انتهاء للمالك الرئيسي")
            if permissions is not None:
                raise HTTPException(409, "صلاحيات المالك الرئيسي لا يمكن تقييدها")
            role = "admin"
            active = True
            expires_at = None
            permissions = None
        if u.id == user.id and not active:
            raise HTTPException(400, "لا يمكنك تعطيل حسابك الحالي")
        existing = db.query(User).filter(User.login == login_, User.id != uid).first()
        if existing:
            raise HTTPException(400, "اسم الدخول مستخدم")

        changed_security = (
            u.role != role
            or bool(u.active) != active
            or getattr(u, "expires_at", None) != expires_at
        )
        u.name = name
        u.login = login_
        u.role = role
        u.active = active
        u.expires_at = expires_at
        if bool(getattr(user, "is_owner", False)) and not bool(getattr(u, "is_owner", False)):
            if u.permissions != permissions:
                u.permissions = permissions
                changed_security = True
        if password:
            try:
                validate_password(password)
            except ValueError as exc:
                raise HTTPException(400, str(exc))
            u.password_hash = hash_password(password)
            changed_security = True
        if changed_security:
            u.token_version = int(u.token_version or 0) + 1
    else:
        if not password:
            raise HTTPException(400, "كلمة المرور مطلوبة لمستخدم جديد")
        try:
            validate_password(password)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        existing = db.query(User).filter(User.login == login_).first()
        if existing:
            raise HTTPException(400, "اسم الدخول مستخدم")
        u = User(
            name=name,
            login=login_,
            role=role,
            password_hash=hash_password(password),
            active=active,
            expires_at=expires_at,
            permissions=permissions if bool(getattr(user, "is_owner", False)) else None,
            is_owner=False,
        )
        db.add(u)

    try:
        log_audit(db, user, "user_save", f"{'تعديل' if uid else 'إضافة'} مستخدم: {name}", request.client.host if request else None, commit=False)
        db.commit()
        db.refresh(u)
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر حفظ المستخدم")
    return {"ok": True, "id": u.id, "user": _visible_user_dict(user, u)}


@router.post("/{uid}/revoke-sessions")
async def revoke_user_sessions(uid: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "user_revoke_sessions") and not bool(getattr(user, "is_owner", False)):
        raise HTTPException(403, "لا تملك صلاحية")
    if uid == user.id:
        raise HTTPException(400, "استخدم تسجيل الخروج لإلغاء جلستك الحالية")
    target = db.query(User).filter(User.id == uid).first()
    if not target:
        raise HTTPException(404, "مستخدم غير موجود")
    _assert_manageable(user, target)
    target.token_version = int(target.token_version or 0) + 1
    try:
        log_audit(db, user, "user_revoke_sessions", f"إلغاء جلسات: {target.name}", request.client.host if request else None, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر إلغاء الجلسات")
    return {"ok": True}


@router.delete("/{uid}")
async def delete_user(uid: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "delete_user"):
        raise HTTPException(403, "صلاحية المدير مطلوبة")
    if uid == user.id:
        raise HTTPException(400, "لا يمكنك تعطيل نفسك")
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(404, "مستخدم غير موجود")
    _assert_manageable(user, u)
    if bool(getattr(u, "is_owner", False)):
        raise HTTPException(403, "لا يمكن تعطيل حساب المالك الرئيسي")
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
