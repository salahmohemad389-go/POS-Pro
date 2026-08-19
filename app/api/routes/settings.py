"""Settings routes for POS Pro."""

from __future__ import annotations

import re

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.permissions import has_permission
from app.core.security import get_current_user
from app.db.models import Setting, User
from app.db.session import get_db
from app.schemas.requests import SettingsSave
from app.services.audit_service import log_audit
from app.services.setting_service import (
    UI_SETTINGS_KEYS,
    get_settings_cached,
    invalidate_settings_cache,
    save_ui_settings,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_BOOL_KEYS = {
    "feature_invoices_enabled",
    "feature_customers_enabled",
    "feature_products_enabled",
    "feature_audit_enabled",
    "quick_qty_enabled",
}
_COLOR_KEYS = {"primary_color", "accent_color"}
_SHORTCUT_KEYS = {key for key in UI_SETTINGS_KEYS if key.startswith("shortcut_")}


def _normalize_shortcut(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) > 24:
        raise HTTPException(422, "الاختصار طويل جداً")
    parts = [p.strip() for p in raw.replace(" ", "").split("+") if p.strip()]
    if not parts:
        return ""
    key = parts[-1].upper()
    modifiers = []
    aliases = {"CONTROL": "Ctrl", "CTRL": "Ctrl", "ALT": "Alt", "SHIFT": "Shift"}
    for p in parts[:-1]:
        name = aliases.get(p.upper())
        if not name or name in modifiers:
            raise HTTPException(422, f"اختصار غير صالح: {raw}")
        modifiers.append(name)
    if not (re.fullmatch(r"F(?:[1-9]|1[0-2])", key) or re.fullmatch(r"[A-Z0-9]", key)):
        raise HTTPException(422, "استخدم حرفاً/رقماً إنجليزياً أو F1 إلى F12")
    ordered = [x for x in ("Ctrl", "Alt", "Shift") if x in modifiers]
    return "+".join([*ordered, key])


def _validate_ui_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(422, "بيانات إعدادات الواجهة غير صالحة")
    unknown = [k for k in payload if k not in UI_SETTINGS_KEYS]
    if unknown:
        raise HTTPException(422, "إعدادات غير معروفة: " + ", ".join(unknown[:5]))
    clean = {}
    for key, value in payload.items():
        if key in _BOOL_KEYS:
            if not isinstance(value, bool):
                raise HTTPException(422, f"{key} يجب أن يكون تفعيل/إلغاء")
            clean[key] = value
        elif key in _COLOR_KEYS:
            value = str(value or "").strip()
            if not _COLOR_RE.fullmatch(value):
                raise HTTPException(422, "اللون يجب أن يكون بصيغة #RRGGBB")
            clean[key] = value.lower()
        elif key in _SHORTCUT_KEYS:
            clean[key] = _normalize_shortcut(value)
    return clean


@router.get("")
async def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_settings_cached(db)


@router.post("")
async def save_settings(payload: SettingsSave, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "settings_save"):
        raise HTTPException(403, "لا تملك صلاحية")
    data = payload.model_dump(exclude_unset=True)
    s = db.query(Setting).first()
    if not s:
        s = Setting()
        db.add(s)
    for k, value in data.items():
        setattr(s, k, value)
    try:
        log_audit(db, user, "settings_save", "حفظ الإعدادات", request.client.host if request else None, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر حفظ الإعدادات")
    invalidate_settings_cache()
    return {"ok": True}


@router.post("/ui")
async def save_ui_preferences(
    request: Request,
    payload: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save appearance, section visibility, quick-quantity and shortcut preferences."""
    if not has_permission(user, "settings_save"):
        raise HTTPException(403, "لا تملك صلاحية")
    clean = _validate_ui_payload(payload)
    try:
        save_ui_settings(db, clean)
        log_audit(db, user, "settings_ui_save", "حفظ إعدادات الواجهة والاختصارات", request.client.host if request else None, commit=False)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر حفظ إعدادات الواجهة")
    invalidate_settings_cache()
    return {"ok": True, "settings": get_settings_cached(db)}
