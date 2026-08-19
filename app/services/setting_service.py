"""Cached application settings plus flexible UI preferences.

Core business settings stay in the ``settings`` table. UI-only preferences are
stored in a tiny JSON table so new appearance/navigation/shortcut options can be
added without a schema migration for every toggle.
"""

from __future__ import annotations

import base64
import json
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import Setting

_CACHE: Optional[dict[str, Any]] = None
_CACHE_TTL: int = 30

UI_DEFAULTS: dict[str, Any] = {
    "feature_invoices_enabled": True,
    "feature_customers_enabled": True,
    "quick_qty_enabled": True,
    "primary_color": "#2563eb",
    "accent_color": "#0891b2",
    "shortcut_new_sale": "Alt+N",
    "shortcut_search": "Alt+S",
    "shortcut_return": "Alt+R",
    "shortcut_cash": "Alt+C",
    "shortcut_credit": "Alt+D",
    "shortcut_partial": "Alt+P",
    "shortcut_clear_cart": "Alt+X",
    "shortcut_sidebar": "Alt+B",
    "shortcut_invoices": "Alt+I",
}
UI_SETTINGS_KEYS = frozenset(UI_DEFAULTS)

_SEEDED_STORE_NAMES = {"صالح الأسناوي", "صالح الأستاذ"}
_SEEDED_TAGLINES = {"لتوريد وتركيب أدوات صحية", "توريد وتركيب أدوات صحية"}
_SEEDED_BRANCHES = {"أبو خليفة", "ابو خلفية"}


def _ensure_ui_table(db: Session) -> None:
    bind = db.get_bind()
    with bind.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS pos_ui_settings "
            "(id INTEGER PRIMARY KEY, data TEXT NOT NULL DEFAULT '{}')"
        )


def _load_ui_settings(db: Session) -> dict[str, Any]:
    _ensure_ui_table(db)
    row = db.execute(text("SELECT data FROM pos_ui_settings WHERE id = 1")).first()
    if not row or not row[0]:
        return dict(UI_DEFAULTS)
    try:
        raw = json.loads(row[0])
    except Exception:
        raw = {}
    clean = dict(UI_DEFAULTS)
    if isinstance(raw, dict):
        for key in UI_SETTINGS_KEYS:
            if key in raw:
                clean[key] = raw[key]
    return clean


def save_ui_settings(db: Session, values: dict[str, Any]) -> None:
    """Merge validated UI preferences into the single settings row."""
    if not values:
        return
    current = _load_ui_settings(db)
    for key, value in values.items():
        if key in UI_SETTINGS_KEYS:
            current[key] = value
    payload = json.dumps(current, ensure_ascii=False, separators=(",", ":"))
    db.execute(
        text(
            "INSERT INTO pos_ui_settings(id, data) VALUES (1, :data) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data"
        ),
        {"data": payload},
    )


@lru_cache(maxsize=1)
def _bundled_logo_data_url() -> str:
    """Return the old bundled Salah logo so it can be treated as legacy seed data."""
    try:
        logo_path = Path(__file__).resolve().parent.parent.parent / "static" / "assets" / "logo.png"
        if not logo_path.exists():
            return ""
        return "data:image/png;base64," + base64.b64encode(logo_path.read_bytes()).decode("ascii")
    except Exception:
        return ""


def _branding_values(s: Setting) -> dict[str, str]:
    raw_name = (s.store_name or "").strip()
    seeded = raw_name in _SEEDED_STORE_NAMES
    logo = s.logo or ""
    if logo and logo == _bundled_logo_data_url():
        logo = ""
    tagline = (s.tagline or "").strip()
    slogan = (s.slogan or "").strip()
    branch = (s.branch or "").strip()
    if seeded:
        raw_name = "POS"
        if tagline in _SEEDED_TAGLINES:
            tagline = ""
        if slogan in _SEEDED_BRANCHES:
            slogan = ""
        if branch in _SEEDED_BRANCHES:
            branch = ""
    return {
        "store_name": raw_name or "POS",
        "tagline": tagline,
        "slogan": slogan,
        "branch": branch,
        "logo": logo,
    }


def get_settings_cached(db: Session) -> dict[str, Any]:
    global _CACHE
    now = time.time()
    if _CACHE and (now - _CACHE.get("_ts", 0)) < _CACHE_TTL:
        return {k: v for k, v in _CACHE.items() if not k.startswith("_")}
    s = db.query(Setting).first()
    if not s:
        _CACHE = {**UI_DEFAULTS, "store_name": "POS", "_ts": now}
        return {k: v for k, v in _CACHE.items() if not k.startswith("_")}

    branding = _branding_values(s)
    _CACHE = {
        **branding,
        "phone": s.phone or "",
        "address": s.address or "",
        "currency": s.currency or "ج.م",
        "tax_rate": float(s.tax_rate or 0),
        "vat_enabled": bool(getattr(s, "vat_enabled", False)),
        "footer": s.footer or "",
        "copies": s.copies or 1,
        "header_position": s.header_position or "top",
        "quick_qty": s.quick_qty or "1,5,10,20,30,50,100",
        "printer_type": s.printer_type or "browser",
        "auto_print_after_sale": bool(s.auto_print_after_sale),
        "theme": s.theme or "light",
        "custom_lines": s.custom_lines or "",
        "invoice_format": s.invoice_format or "a4",
        "header_note": s.header_note or "",
        "terms_conditions": s.terms_conditions or "",
        "warranty_text": s.warranty_text or "",
        "max_items_per_page": s.max_items_per_page or 15,
        "feature_reports_enabled": bool(getattr(s, "feature_reports_enabled", True)),
        "feature_suppliers_enabled": bool(getattr(s, "feature_suppliers_enabled", True)),
        **_load_ui_settings(db),
        "_ts": now,
    }
    return {k: v for k, v in _CACHE.items() if not k.startswith("_")}


def invalidate_settings_cache():
    global _CACHE
    _CACHE = None


def cached(key: str) -> Optional[Any]:
    import app.core.cache as _mod
    return _mod.get(key)


def cache_set(key: str, value: Any) -> None:
    import app.core.cache as _mod
    _mod.set(key, value)


def cache_invalidate(key: str) -> None:
    import app.core.cache as _mod
    _mod.invalidate(key)
