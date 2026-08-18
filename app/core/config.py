"""Centralized configuration for POS Pro.

All settings are derived from environment variables with sensible defaults.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env_text(name: str, default: str = "") -> str:
    """Return a stripped env value, treating an explicitly empty value as unset."""
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    """Read an integer env value while safely accepting blank Vercel fields."""
    raw = _env_text(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "static"
FONTS_DIR = STATIC_DIR / "assets" / "fonts"

# Runtime directories. Vercel only provides ephemeral writable storage under /tmp.
_runtime_default = "/tmp/pospro" if os.environ.get("VERCEL") else str(BASE_DIR / "runtime")
RUNTIME_DIR = Path(_env_text("POS_RUNTIME_DIR", _runtime_default))
DATA_DIR = RUNTIME_DIR / "database"
BACKUP_DIR = RUNTIME_DIR / "backups"
EXPORT_DIR = RUNTIME_DIR / "exports"
LOGS_DIR = RUNTIME_DIR / "logs"

LEGACY_DATA_DIR = BASE_DIR / "data"
LEGACY_BACKUP_DIR = BASE_DIR / "backups"
DB_PATH = DATA_DIR / "pospro.db"
LEGACY_DB_PATH = LEGACY_DATA_DIR / "pospro.db"

# Environment
POS_ENV = _env_text("POS_ENV", "development").lower()
IS_PRODUCTION = POS_ENV == "production"

# Database
POS_DATABASE_URL = _env_text("POS_DATABASE_URL")
IS_SQLITE = not POS_DATABASE_URL or POS_DATABASE_URL.startswith("sqlite:")
if IS_SQLITE:
    DATABASE_URL = f"sqlite:///{DB_PATH}" if not POS_DATABASE_URL else POS_DATABASE_URL
else:
    # Neon/Vercel commonly injects a generic postgresql:// URL. SQLAlchemy maps
    # that to psycopg2 by default, but POS Pro ships psycopg v3. Explicitly use
    # the psycopg driver so Vercel does not require psycopg2.
    DATABASE_URL = (
        "postgresql+psycopg://" + POS_DATABASE_URL[len("postgresql://"):]
        if POS_DATABASE_URL.startswith("postgresql://")
        else POS_DATABASE_URL
    )

if IS_PRODUCTION and IS_SQLITE:
    raise RuntimeError("Production deployment requires POS_DATABASE_URL pointing to PostgreSQL; SQLite is development-only")

_serverless = bool(os.environ.get("VERCEL"))
DB_POOL_SIZE = _env_int("POS_DB_POOL_SIZE", 3 if _serverless else 10)
DB_MAX_OVERFLOW = _env_int("POS_DB_MAX_OVERFLOW", 2 if _serverless else 20)
DB_POOL_TIMEOUT = _env_int("POS_DB_POOL_TIMEOUT", 10)
if DB_POOL_SIZE < 1 or DB_POOL_SIZE > 50 or DB_MAX_OVERFLOW < 0 or DB_MAX_OVERFLOW > 100 or DB_POOL_TIMEOUT < 1 or DB_POOL_TIMEOUT > 120:
    raise RuntimeError("Invalid database pool settings")

# Security
POS_JWT_SECRET = _env_text("POS_JWT_SECRET")
POS_ADMIN_PASSWORD = _env_text("POS_ADMIN_PASSWORD")
POS_ADMIN_LOGIN = _env_text("POS_ADMIN_LOGIN", "admin")
POS_ADMIN_NAME = _env_text("POS_ADMIN_NAME", "المدير")
TOKEN_EXPIRE_HOURS = _env_int("POS_TOKEN_HOURS", 12)
SCRYPT_N = _env_int("POS_SCRYPT_N", 32768)
if SCRYPT_N < 16384 or SCRYPT_N > 131072 or (SCRYPT_N & (SCRYPT_N - 1)) != 0:
    raise RuntimeError("POS_SCRYPT_N must be a power of two between 16384 and 131072")
if TOKEN_EXPIRE_HOURS < 1 or TOKEN_EXPIRE_HOURS > 168:
    raise RuntimeError("POS_TOKEN_HOURS must be between 1 and 168")

if IS_PRODUCTION:
    if len(POS_JWT_SECRET) < 32:
        raise RuntimeError("POS_JWT_SECRET must be set to at least 32 characters in production")
    if len(POS_ADMIN_PASSWORD) < 12:
        raise RuntimeError("POS_ADMIN_PASSWORD must be set to at least 12 characters in production")

# Server
POS_HOST = _env_text("POS_HOST", "127.0.0.1")
POS_PORT = _env_int("POS_PORT", 8000)
_configured_hosts = [
    h.strip()
    for h in _env_text("POS_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
    if h.strip()
]
if IS_PRODUCTION and "*" in _configured_hosts:
    raise RuntimeError("POS_ALLOWED_HOSTS cannot contain a bare * in production")

# Trust only exact Vercel-generated hosts, never a broad *.vercel.app wildcard.
for _vercel_host_var in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
    _host = _env_text(_vercel_host_var).lower()
    if _host and "://" not in _host and "/" not in _host and _host not in _configured_hosts:
        _configured_hosts.append(_host)
POS_ALLOWED_HOSTS = ",".join(_configured_hosts)

# CORS
_configured_origins = [
    o.strip().rstrip("/")
    for o in _env_text(
        "POS_ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000",
    ).split(",")
    if o.strip()
]
for _vercel_host_var in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
    _host = _env_text(_vercel_host_var).lower()
    _origin = f"https://{_host}" if _host and "://" not in _host and "/" not in _host else ""
    if _origin and _origin not in _configured_origins:
        _configured_origins.append(_origin)
ALLOWED_ORIGINS = ",".join(_configured_origins)
CORS_ORIGINS = list(_configured_origins)

APP_TITLE = "POS Pro"
APP_VERSION = "3.4.0"
