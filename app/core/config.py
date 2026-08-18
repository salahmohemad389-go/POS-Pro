"""Centralized configuration for POS Pro.

All settings are derived from environment variables with sensible defaults.
Import this module to access any configuration value.

Environment variables:
    POS_ENV              - "development" or "production" (default: development)
    POS_DATABASE_URL     - SQLAlchemy database URL (default: SQLite at runtime/database/pospro.db)
    POS_SECRET_KEY       - (deprecated, use POS_JWT_SECRET)
    POS_JWT_SECRET       - JWT signing secret (required in production, >= 32 chars)
    POS_ADMIN_PASSWORD   - Initial admin password (required in production, >= 12 chars)
    POS_ADMIN_LOGIN      - Initial admin login name (default: admin)
    POS_ADMIN_NAME       - Initial admin display name (default: المدير)
    POS_HOST             - Optional server bind host for deployment tooling (default: 0.0.0.0)
    POS_PORT             - Server bind port (default: 8000)
    POS_ALLOWED_ORIGINS  - Comma-separated CORS origins
    POS_TOKEN_HOURS      - JWT token expiry in hours (default: 12)
    POS_DB_POOL_SIZE     - DB connection pool size (default: 10)
    POS_DB_MAX_OVERFLOW   - DB pool overflow (default: 20)
"""

from __future__ import annotations

import os
from pathlib import Path

# ═══════════════════════════════════════════════════
# Base paths
# ═══════════════════════════════════════════════════
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "static"
FONTS_DIR = STATIC_DIR / "assets" / "fonts"

# Runtime directories (for SQLite DB, backups, exports, logs)
RUNTIME_DIR = Path(os.environ.get("POS_RUNTIME_DIR", "/tmp/pospro" if os.environ.get("VERCEL") else str(BASE_DIR / "runtime")))
DATA_DIR = RUNTIME_DIR / "database"
BACKUP_DIR = RUNTIME_DIR / "backups"
EXPORT_DIR = RUNTIME_DIR / "exports"
LOGS_DIR = RUNTIME_DIR / "logs"

# Legacy data directory (for backward compatibility during migration)
LEGACY_DATA_DIR = BASE_DIR / "data"
LEGACY_BACKUP_DIR = BASE_DIR / "backups"

# Database file
DB_PATH = DATA_DIR / "pospro.db"
LEGACY_DB_PATH = LEGACY_DATA_DIR / "pospro.db"

# ═══════════════════════════════════════════════════
# Environment
# ═══════════════════════════════════════════════════
POS_ENV = os.environ.get("POS_ENV", "development").strip().lower()
IS_PRODUCTION = POS_ENV == "production"

# ═══════════════════════════════════════════════════
# Database
# ═══════════════════════════════════════════════════
POS_DATABASE_URL = os.environ.get("POS_DATABASE_URL", "").strip()
IS_SQLITE = not POS_DATABASE_URL or POS_DATABASE_URL.startswith("sqlite:")

if IS_SQLITE and not POS_DATABASE_URL:
    DATABASE_URL = f"sqlite:///{DB_PATH}"
else:
    DATABASE_URL = POS_DATABASE_URL

if IS_PRODUCTION and IS_SQLITE:
    raise RuntimeError("Production deployment requires POS_DATABASE_URL pointing to PostgreSQL; SQLite is development-only")

_serverless = bool(os.environ.get("VERCEL"))
DB_POOL_SIZE = int(os.environ.get("POS_DB_POOL_SIZE", "3" if _serverless else "10"))
DB_MAX_OVERFLOW = int(os.environ.get("POS_DB_MAX_OVERFLOW", "2" if _serverless else "20"))
DB_POOL_TIMEOUT = int(os.environ.get("POS_DB_POOL_TIMEOUT", "10"))
if DB_POOL_SIZE < 1 or DB_POOL_SIZE > 50 or DB_MAX_OVERFLOW < 0 or DB_MAX_OVERFLOW > 100 or DB_POOL_TIMEOUT < 1 or DB_POOL_TIMEOUT > 120:
    raise RuntimeError("Invalid database pool settings")

# ═══════════════════════════════════════════════════
# Security
# ═══════════════════════════════════════════════════
POS_JWT_SECRET = os.environ.get("POS_JWT_SECRET", "").strip()
POS_ADMIN_PASSWORD = os.environ.get("POS_ADMIN_PASSWORD", "").strip()
POS_ADMIN_LOGIN = os.environ.get("POS_ADMIN_LOGIN", "admin").strip()
POS_ADMIN_NAME = os.environ.get("POS_ADMIN_NAME", "المدير").strip()
TOKEN_EXPIRE_HOURS = int(os.environ.get("POS_TOKEN_HOURS", "12"))
SCRYPT_N = int(os.environ.get("POS_SCRYPT_N", "32768"))
if SCRYPT_N < 16384 or SCRYPT_N > 131072 or (SCRYPT_N & (SCRYPT_N - 1)) != 0:
    raise RuntimeError("POS_SCRYPT_N must be a power of two between 16384 and 131072")
if TOKEN_EXPIRE_HOURS < 1 or TOKEN_EXPIRE_HOURS > 168:
    raise RuntimeError("POS_TOKEN_HOURS must be between 1 and 168")

# Production safety checks
if IS_PRODUCTION:
    if len(POS_JWT_SECRET) < 32:
        raise RuntimeError(
            "POS_JWT_SECRET must be set to at least 32 characters in production"
        )
    if len(POS_ADMIN_PASSWORD) < 12:
        raise RuntimeError(
            "POS_ADMIN_PASSWORD must be set to at least 12 characters in production"
        )

# ═══════════════════════════════════════════════════
# Server
# ═══════════════════════════════════════════════════
POS_HOST = os.environ.get("POS_HOST", "127.0.0.1").strip()
POS_PORT = int(os.environ.get("POS_PORT", "8000"))
_configured_hosts = [h.strip() for h in os.environ.get("POS_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h.strip()]
if IS_PRODUCTION and "*" in _configured_hosts:
    raise RuntimeError("POS_ALLOWED_HOSTS cannot contain a bare * in production")

# Vercel exposes the current deployment and stable production host names at runtime.
# Trust only those exact generated hosts; do not broadly trust every *.vercel.app site.
for _vercel_host_var in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
    _host = os.environ.get(_vercel_host_var, "").strip().lower()
    if _host and "://" not in _host and "/" not in _host and _host not in _configured_hosts:
        _configured_hosts.append(_host)
POS_ALLOWED_HOSTS = ",".join(_configured_hosts)

# ═══════════════════════════════════════════════════
# CORS
# ═══════════════════════════════════════════════════
_configured_origins = [o.strip().rstrip("/") for o in os.environ.get(
    "POS_ALLOWED_ORIGINS",
    "http://127.0.0.1:8000,http://localhost:8000",
).split(",") if o.strip()]
for _vercel_host_var in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
    _host = os.environ.get(_vercel_host_var, "").strip().lower()
    _origin = f"https://{_host}" if _host and "://" not in _host and "/" not in _host else ""
    if _origin and _origin not in _configured_origins:
        _configured_origins.append(_origin)
ALLOWED_ORIGINS = ",".join(_configured_origins)
CORS_ORIGINS = list(_configured_origins)

# ═══════════════════════════════════════════════════
# Application constants
# ═══════════════════════════════════════════════════
APP_TITLE = "POS Pro"
APP_VERSION = "3.4.0"
