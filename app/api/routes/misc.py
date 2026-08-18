"""Miscellaneous routes (root, favicon, static)."""

from __future__ import annotations

import base64
from pathlib import Path

from fastapi import APIRouter, Response as FastAPIResponse
from fastapi.responses import FileResponse, Response

STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "static"

router = APIRouter(tags=["misc"])


@router.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


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
