"""Authentication routes for POS Pro."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import PERMISSION_MATRIX, has_permission
from app.core.ratelimit import consume_attempt, record_success
from app.core.security import create_token, get_current_user, hash_password, verify_password, password_needs_upgrade, validate_password
from app.core.config import IS_PRODUCTION, TOKEN_EXPIRE_HOURS, POS_ADMIN_LOGIN, POS_ADMIN_PASSWORD
from app.db.session import get_db
from app.db.models import AuditLog, User
from app.services.audit_service import log_audit
from app.schemas.requests import LoginRequest, ChangeCredentials

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _recover_first_admin_login(db: Session, login_: str, password: str) -> User | None:
    """Recover a newly provisioned database whose bootstrap admin credentials drifted.

    This recovery is deliberately narrow:
    - it only accepts the configured admin password;
    - it accepts the configured login or the conventional ``admin`` alias;
    - it only runs before the first successful login has ever been audited;
    - it only runs when exactly one admin exists;
    - after the first successful login, normal database credentials are authoritative.

    That fixes first-deploy credential drift without turning the environment
    password into a permanent backdoor after the operator changes credentials.
    """
    if not POS_ADMIN_PASSWORD or len(POS_ADMIN_PASSWORD) < 12:
        return None

    submitted_login = login_.strip()
    configured_login = (POS_ADMIN_LOGIN or "admin").strip()
    accepted_logins = {configured_login.casefold(), "admin"}
    if submitted_login.casefold() not in accepted_logins:
        return None
    if not hmac.compare_digest(password, POS_ADMIN_PASSWORD):
        return None
    if db.query(AuditLog.id).filter(AuditLog.action == "login").first() is not None:
        return None

    admins = db.query(User).filter(User.role == "admin").order_by(User.id.asc()).all()
    if len(admins) != 1:
        return None

    admin = admins[0]
    # If the operator used the conventional first-login alias, keep it as the
    # persisted login so the same credentials continue working after recovery.
    recovered_login = configured_login if submitted_login.casefold() == configured_login.casefold() else "admin"
    login_owner = db.query(User).filter(User.login == recovered_login, User.id != admin.id).first()
    if login_owner:
        return None

    try:
        admin.login = recovered_login
        admin.password_hash = hash_password(POS_ADMIN_PASSWORD)
        admin.active = True
        admin.token_version = int(admin.token_version or 0) + 1
        db.commit()
        db.refresh(admin)
        return admin
    except Exception:
        db.rollback()
        return None


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    login_ = payload.login.strip()
    password = payload.password
    if not login_ or not password:
        raise HTTPException(400, "أدخل البيانات")

    client_ip = request.client.host if request else "unknown"
    rate_key = f"{client_ip}:{login_}"
    allowed, remaining = consume_attempt(rate_key, "login")
    if not allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"تجاوزت الحد المسموح. حاول بعد {remaining // 60 + 1} دقيقة")

    user = db.query(User).filter(User.login == login_).first()
    credentials_ok = bool(user and user.active and verify_password(password, user.password_hash))
    if not credentials_ok:
        recovered = _recover_first_admin_login(db, login_, password)
        if recovered is None:
            raise HTTPException(401, "اسم المستخدم أو كلمة المرور غير صحيحة")
        user = recovered

    record_success(rate_key)
    if password_needs_upgrade(user.password_hash):
        try:
            user.password_hash = hash_password(password)
            user.token_version = int(user.token_version or 0) + 1
            db.commit()
        except ValueError:
            db.rollback()
    token = create_token(user.id, user.role, user.token_version)
    response.set_cookie(
        "pos_session", token, httponly=True, secure=IS_PRODUCTION, samesite="strict",
        max_age=int(TOKEN_EXPIRE_HOURS * 3600), path="/",
    )
    log_audit(db, user, "login", f"دخول {user.name}", request.client.host if request else None)
    return {"ok": True, "user": {"id": user.id, "name": user.name, "role": user.role, "login": user.login}}


@router.post("/logout")
async def logout(request: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.token_version = int(user.token_version or 0) + 1
    try:
        log_audit(db, user, "logout", "تسجيل خروج", request.client.host if request else None, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر تسجيل الخروج بأمان")
    response.delete_cookie("pos_session", path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "name": user.name, "role": user.role, "login": user.login}


@router.get("/permissions")
async def get_my_permissions(user: User = Depends(get_current_user)):
    role = user.role or "cashier"
    return {
        "role": role,
        "permissions": sorted(PERMISSION_MATRIX.get(role, frozenset())),
        "all_roles": {r: sorted(p) for r, p in PERMISSION_MATRIX.items()} if user.role == "admin" else {},
    }


@router.post("/change-credentials")
async def change_credentials(payload: ChangeCredentials, request: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_login = (payload.login or "").strip()
    new_pass = payload.password or ""
    current_pass = payload.current_password or ""
    if not new_login and not new_pass:
        raise HTTPException(400, "أدخل قيمة جديدة")
    if new_login:
        existing = db.query(User).filter(User.login == new_login, User.id != user.id).first()
        if existing:
            raise HTTPException(400, "اسم الدخول مستخدم")
        user.login = new_login
    if new_pass:
        if not current_pass or not verify_password(current_pass, user.password_hash):
            raise HTTPException(400, "كلمة المرور الحالية غير صحيحة")
        try:
            validate_password(new_pass)
            user.password_hash = hash_password(new_pass)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    user.token_version = int(user.token_version or 0) + 1
    log_audit(db, user, "credentials_change", "تغيير بيانات الدخول", request.client.host if request else None, commit=False)
    db.commit()
    token = create_token(user.id, user.role, user.token_version)
    response.set_cookie(
        "pos_session", token, httponly=True, secure=IS_PRODUCTION, samesite="strict",
        max_age=int(TOKEN_EXPIRE_HOURS * 3600), path="/",
    )
    return {"ok": True, "user": {"id": user.id, "name": user.name, "role": user.role, "login": user.login}}
