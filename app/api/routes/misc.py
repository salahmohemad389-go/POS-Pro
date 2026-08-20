"""Miscellaneous routes (root, favicon, static)."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response as FastAPIResponse
from fastapi.responses import FileResponse, HTMLResponse, Response, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.setting_service import get_settings_cached

STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "static"

router = APIRouter(tags=["misc"])
log = logging.getLogger("pospro.client")


@router.get("/")
async def root():
    """Serve the UI and same-origin startup helpers before app.js."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    if '</head>' in html:
        extras = (
            '<link rel="stylesheet" href="/static/css/upgrade.css">\n'
            '<link rel="manifest" href="/manifest.webmanifest">\n'
            '<link rel="icon" href="/app-icon">\n'
            '<link rel="apple-touch-icon" href="/app-icon">\n'
            '<meta name="application-name" content="POS">\n'
            '<meta name="apple-mobile-web-app-capable" content="yes">\n'
            '<meta name="apple-mobile-web-app-status-bar-style" content="default">\n'
        )
        html = html.replace('</head>', extras + '</head>', 1)
    marker = '<script type="module" src="/static/app.js"></script>'
    shell = (
        '<script src="/static/client_diag.js" defer></script>\n'
        '<script src="/static/js/upgrade_dom.js"></script>\n'
        '<script src="/static/js/final_ui_patch.js"></script>\n'
        '<script src="/static/js/owner_ui_v4.js"></script>\n'
        + marker
    )
    if marker in html:
        html = html.replace(marker, shell, 1)
    return HTMLResponse(content=html)


@router.get("/api/branding", include_in_schema=False)
async def public_branding(db: Session = Depends(get_db)):
    """Public, non-sensitive branding used by the login screen."""
    settings = get_settings_cached(db)
    return {
        "store_name": settings.get("store_name") or "POS",
        "tagline": settings.get("tagline") or "",
        "logo": settings.get("logo") or "",
    }


@router.post("/api/client-error", include_in_schema=False)
async def client_error(request: Request):
    """Log bounded, non-sensitive browser startup diagnostics."""
    try:
        data = await request.json()
    except Exception:
        return FastAPIResponse(status_code=204)

    def clean(name: str, limit: int) -> str:
        value = data.get(name, "") if isinstance(data, dict) else ""
        return str(value).replace("\n", " ").replace("\r", " ")[:limit]

    log.warning(
        "CLIENT_JS_ERROR kind=%s source=%s line=%s col=%s message=%s",
        clean("kind", 80),
        clean("source", 300),
        clean("line", 20),
        clean("col", 20),
        clean("message", 1000),
    )
    return FastAPIResponse(status_code=204)


@router.get("/favicon.ico")
async def favicon():
    # Browsers that still probe /favicon.ico should use the same dynamic store icon.
    return RedirectResponse(url="/app-icon", status_code=307)


@router.get("/api/health", include_in_schema=False)
async def health():
    from sqlalchemy import text
    from app.core.config import APP_VERSION
    from app.db.session import engine
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"ok": True, "version": APP_VERSION, "database": engine.dialect.name}
    except Exception:
        return FastAPIResponse(status_code=503, content='{"ok":false,"database":"unavailable"}', media_type="application/json")
