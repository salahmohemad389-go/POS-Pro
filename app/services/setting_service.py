"""In-memory settings cache for POS Pro.

Avoids a DB hit per request. The cache is invalidated when settings are saved.
Advanced UI preferences are stored in a compact JSON column that is added
idempotently for existing installations.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db.models import Setting

_CACHE: Optional[dict[str, Any]] = None
_CACHE_TTL: int = 30

_UI_DEFAULTS: dict[str, Any] = {
    "primary_color": "#163b63",
    "accent_color": "#c99a35",
    "feature_products_enabled": True,
    "feature_customers_enabled": True,
    "feature_invoices_enabled": True,
    "feature_suppliers_enabled": True,
    "feature_reports_enabled": True,
    "feature_audit_enabled": True,
    "quick_qty_enabled": True,
    "shortcuts": {
        "new_sale": "F2",
        "return_invoice": "F3",
        "focus_search": "F4",
        "cash_checkout": "F8",
        "credit_checkout": "F9",
        "clear_cart": "F10",
        "toggle_sidebar": "F6",
    },
}


def _has_ui_config_column(db: Session) -> bool:
    try:
        return any(c["name"] == "ui_config" for c in inspect(db.bind).get_columns("settings"))
    except Exception:
        return False


def ensure_ui_config_column(db: Session) -> None:
    if _has_ui_config_column(db):
        return
    try:
        db.execute(text("ALTER TABLE settings ADD COLUMN ui_config TEXT DEFAULT '{}'"))
        db.flush()
    except Exception:
        db.rollback()
        if not _has_ui_config_column(db):
            raise


def _load_ui_config(db: Session) -> dict[str, Any]:
    result = dict(_UI_DEFAULTS)
    result["shortcuts"] = dict(_UI_DEFAULTS["shortcuts"])
    if not _has_ui_config_column(db):
        return result
    try:
        raw = db.execute(text("SELECT ui_config FROM settings ORDER BY id LIMIT 1")).scalar()
        parsed = json.loads(raw or "{}") if isinstance(raw, str) else {}
        if isinstance(parsed, dict):
            for key, value in parsed.items():
                if key == "shortcuts" and isinstance(value, dict):
                    result["shortcuts"].update({str(k): str(v) for k, v in value.items()})
                elif key in result:
                    result[key] = value
    except Exception:
        return result
    return result


def save_ui_config(db: Session, config: dict[str, Any] | None) -> None:
    if config is None:
        return
    ensure_ui_config_column(db)
    current = _load_ui_config(db)
    allowed = set(_UI_DEFAULTS)
    for key, value in config.items():
        if key not in allowed:
            continue
        if key == "shortcuts":
            if isinstance(value, dict):
                shortcuts = dict(current.get("shortcuts") or {})
                for action, shortcut in value.items():
                    shortcuts[str(action)] = str(shortcut or "").strip()[:32]
                current["shortcuts"] = shortcuts
        elif key in {"feature_products_enabled", "feature_customers_enabled", "feature_invoices_enabled", "feature_suppliers_enabled", "feature_reports_enabled", "feature_audit_enabled", "quick_qty_enabled"}:
            current[key] = bool(value)
        elif key in {"primary_color", "accent_color"}:
            s = str(value or "").strip()
            if len(s) <= 32:
                current[key] = s
    payload = json.dumps(current, ensure_ascii=False, separators=(",", ":"))
    db.execute(text("UPDATE settings SET ui_config = :payload"), {"payload": payload})


def get_settings_cached(db: Session) -> dict[str, Any]:
    global _CACHE
    now = time.time()
    if _CACHE and (now - _CACHE.get("_ts", 0)) < _CACHE_TTL:
        return {k: v for k, v in _CACHE.items() if not k.startswith("_")}
    s = db.query(Setting).first()
    if not s:
        _CACHE = {}
        return {}
    ui = _load_ui_config(db)
    _CACHE = {
        "store_name": s.store_name or "POS",
        "branch": s.branch or "",
        "phone": s.phone or "",
        "address": s.address or "",
        "currency": s.currency or "ج.م",
        "tax_rate": float(s.tax_rate or 0),
        "vat_enabled": bool(getattr(s, "vat_enabled", False)),
        "footer": s.footer or "",
        "copies": s.copies or 1,
        "logo": s.logo or "",
        "header_position": s.header_position or "top",
        "quick_qty": s.quick_qty or "1,5,10,20,30,50,100",
        "printer_type": s.printer_type or "browser",
        "auto_print_after_sale": bool(s.auto_print_after_sale),
        "theme": s.theme or "light",
        "tagline": s.tagline or "",
        "slogan": s.slogan or "",
        "custom_lines": s.custom_lines or "",
        "invoice_format": s.invoice_format or "a4",
        "header_note": s.header_note or "",
        "terms_conditions": s.terms_conditions or "",
        "warranty_text": s.warranty_text or "",
        "max_items_per_page": s.max_items_per_page or 15,
        "feature_reports_enabled": bool(ui.get("feature_reports_enabled", getattr(s, "feature_reports_enabled", True))),
        "feature_suppliers_enabled": bool(ui.get("feature_suppliers_enabled", getattr(s, "feature_suppliers_enabled", True))),
        "ui_config": ui,
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
