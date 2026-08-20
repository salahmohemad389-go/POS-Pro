"""POS Pro - Web-only FastAPI application entry point.

This is the new modular entry point. All routes are registered via routers.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.core.middleware import RequestSizeLimitMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import IS_SQLITE, DATABASE_URL, ALLOWED_ORIGINS, POS_ALLOWED_HOSTS, APP_TITLE, APP_VERSION
from app.db.bootstrap import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("pospro")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("=" * 50)
    log.info("POS Pro starting (web-only)...")
    init_db()
    db_info = DATABASE_URL if IS_SQLITE else DATABASE_URL.split("@")[-1]
    log.info("DB: %s", db_info)
    log.info("CORS origins: %s", origins if 'origins' in globals() else ALLOWED_ORIGINS)
    log.info("=" * 50)
    yield

app = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)

app.add_middleware(RequestSizeLimitMiddleware, max_bytes=12 * 1024 * 1024)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[h.strip() for h in POS_ALLOWED_HOSTS.split(",") if h.strip()])
app.add_middleware(GZipMiddleware, minimum_size=500)

origins = [o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.middleware("http")
async def same_origin_guard(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.cookies.get("pos_session"):
        origin = (request.headers.get("origin") or "").rstrip("/")
        if origin:
            host_origin = f"{request.url.scheme}://{request.headers.get('host', '')}".rstrip("/")
            allowed = set(origins) | {host_origin}
            if origin not in allowed:
                return JSONResponse(status_code=403, content={"detail": "مصدر الطلب غير مسموح"})
    return await call_next(request)

@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-src 'self' blob:; frame-ancestors 'none'"
    )
    return response

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Register all route routers
from app.api.routes import auth, products, categories, suppliers, customers, invoices, combined, users, audit, settings, backup, reports, misc, customization_v4
from app.services.live_customizations import install_live_customizations
from app.services.owner_customizations_v4 import install_owner_customizations_v4
from app.services.market_readiness import install_market_readiness

install_live_customizations()
install_owner_customizations_v4()
install_market_readiness()

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(categories.router)
app.include_router(suppliers.router)
app.include_router(customers.router)
app.include_router(invoices.router)
app.include_router(combined.router)
app.include_router(users.router)
app.include_router(audit.router)
app.include_router(settings.router)
app.include_router(backup.router)
app.include_router(reports.router)
app.include_router(customization_v4.router)
app.include_router(misc.router)