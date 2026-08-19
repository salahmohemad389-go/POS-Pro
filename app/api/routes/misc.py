"""Miscellaneous routes (root, favicon, static)."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response as FastAPIResponse
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.setting_service import get_settings_cached

STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "static"

router = APIRouter(tags=["misc"])
log = logging.getLogger("pospro.client")


@router.get("/")
async def root():
    """Serve the UI and load a small same-origin diagnostic before app.js.

    The diagnostic is intentionally temporary while the production login UI is
    being investigated. It only reports JavaScript error metadata; it never
    reads or sends form values, cookies, or credentials.
    """
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    if '</head>' in html:
        html = html.replace('</head>', '<link rel="stylesheet" href="/static/css/upgrade.css">\n</head>', 1)
    marker = '<script type="module" src="/static/app.js"></script>'
    shell = (
        '<script src="/static/client_diag.js" defer></script>\n'
        '<script src="/static/js/upgrade_dom.js"></script>\n'
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
    for name in ("favicon.ico", "favicon.png"):
        path = STATIC_DIR / name
        if path.exists():
            return FileResponse(str(path))
    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    return Response(content=base64.b64decode(png_b64), media_type="image/png")


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
