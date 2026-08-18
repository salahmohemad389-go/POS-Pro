"""Authentication helpers with built-in scrypt + HS256 JWT.

New passwords use Python's built-in scrypt. Legacy bcrypt hashes remain
supported when the optional bcrypt package is installed.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import DATA_DIR, POS_JWT_SECRET, TOKEN_EXPIRE_HOURS, SCRYPT_N
from app.db.session import get_db

try:
    import bcrypt as _bcrypt  # legacy-hash compatibility
except Exception:
    _bcrypt = None

SECRET_KEY_FILE = DATA_DIR / "secret.key"
ALGORITHM = "HS256"
_SCRYPT_N = SCRYPT_N
_SCRYPT_R = 8
_SCRYPT_P = 1


def _load_or_create_secret() -> str:
    if SECRET_KEY_FILE.exists():
        value = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
        if len(value) >= 32:
            return value
    key = secrets.token_urlsafe(48)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SECRET_KEY_FILE.write_text(key, encoding="utf-8")
    try:
        SECRET_KEY_FILE.chmod(0o600)
    except Exception:
        pass
    return key


SECRET_KEY = POS_JWT_SECRET or _load_or_create_secret()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def validate_password(plain: str) -> None:
    if not isinstance(plain, str) or len(plain) < 12:
        raise ValueError("كلمة المرور يجب ألا تقل عن 12 حرفاً")
    if len(plain.encode("utf-8")) > 1024:
        raise ValueError("كلمة المرور طويلة جداً")


def hash_password(plain: str) -> str:
    validate_password(plain)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        plain.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32, maxmem=128 * 1024 * 1024
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64url(salt)}${_b64url(digest)}"


def verify_password(plain: str, hashed: str) -> bool:
    try:
        if hashed.startswith("scrypt$"):
            _, n, r, p, salt_b64, digest_b64 = hashed.split("$", 5)
            actual = hashlib.scrypt(
                plain.encode("utf-8"), salt=_b64url_decode(salt_b64),
                n=int(n), r=int(r), p=int(p), dklen=32, maxmem=128 * 1024 * 1024,
            )
            return hmac.compare_digest(actual, _b64url_decode(digest_b64))
        if hashed.startswith(("$2a$", "$2b$", "$2y$")) and _bcrypt is not None:
            return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        pass
    return False


def password_needs_upgrade(hashed: str) -> bool:
    value = hashed or ""
    if not value.startswith("scrypt$"):
        return True
    try:
        _, n, r, p, _salt, _digest = value.split("$", 5)
        return int(n) < _SCRYPT_N or int(r) != _SCRYPT_R or int(p) != _SCRYPT_P
    except Exception:
        return True


def create_token(user_id: int, role: str, token_version: int = 0) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id), "role": role, "ver": int(token_version or 0),
        "iat": now, "exp": now + int(TOKEN_EXPIRE_HOURS * 3600),
    }
    header = {"alg": "HS256", "typ": "JWT"}
    a = _b64url(json.dumps(header, separators=(",", ":")).encode())
    b = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(SECRET_KEY.encode(), f"{a}.{b}".encode(), hashlib.sha256).digest()
    return f"{a}.{b}.{_b64url(sig)}"


def decode_token(token: str) -> dict:
    try:
        a, b, c = token.split(".")
        expected = hmac.new(SECRET_KEY.encode(), f"{a}.{b}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(c)):
            return {}
        payload = json.loads(_b64url_decode(b))
        if int(payload.get("exp", 0)) <= int(time.time()):
            return {}
        return payload
    except Exception:
        return {}


def get_current_user(request: Request, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    from app.db.models import User
    token = request.cookies.get("pos_session")
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "غير مصرح")
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "جلسة منتهية")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "مستخدم غير موجود")
    if int(payload.get("ver", 0)) != int(getattr(user, "token_version", 0) or 0):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "تم إلغاء هذه الجلسة")
    return user


def require_roles(*roles):
    def _check(user=Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "لا تملك صلاحية لهذا الإجراء")
        return user
    return _check


require_admin = require_roles("admin")
require_manager = require_roles("admin", "manager")
require_any = require_roles("admin", "manager", "cashier")
