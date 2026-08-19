"""In-memory settings cache for POS Pro.

Avoids a DB hit per request. The cache is invalidated when settings are saved.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.db.models import Setting

_CACHE: Optional[dict[str, Any]] = None
_CACHE_TTL: int = 30  # seconds


def get_settings_cached(db: Session) -> dict[str, Any]:
    global _CACHE
    now = time.time()
    if _CACHE and (now - _CACHE.get("_ts", 0)) < _CACHE_TTL:
        return {k: v for k, v in _CACHE.items() if not k.startswith("_")}
    from app.db.models import Setting
    s = db.query(Setting).first()
    if not s:
        _CACHE = {}
        return {}
    _CACHE = {
        "store_name": s.store_name or "",
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
        "feature_reports_enabled": bool(getattr(s, "feature_reports_enabled", True)),
        "feature_suppliers_enabled": bool(getattr(s, "feature_suppliers_enabled", True)),
        "_ts": now,
    }
    return {k: v for k, v in _CACHE.items() if not k.startswith("_")}


def invalidate_settings_cache():
    global _CACHE
    _CACHE = None


def cached(key: str) -> Optional[Any]:
    """Generic 30s cache for categories etc."""
    import app.core.cache as _mod
    return _mod.get(key)


def cache_set(key: str, value: Any) -> None:
    import app.core.cache as _mod
    _mod.set(key, value)


def cache_invalidate(key: str) -> None:
    import app.core.cache as _mod
    _mod.invalidate(key)
