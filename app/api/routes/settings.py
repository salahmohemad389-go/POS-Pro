"""Settings routes for POS Pro."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.permissions import has_permission
from app.db.models import Setting, User
from app.db.session import get_db
from app.core.security import get_current_user
from app.services.audit_service import log_audit
from app.services.setting_service import get_settings_cached, invalidate_settings_cache, save_ui_config
from app.schemas.requests import SettingsSave

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_settings_cached(db)


@router.post("")
async def save_settings(payload: SettingsSave, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "settings_save"):
        raise HTTPException(403, "لا تملك صلاحية")
    data = payload.model_dump(exclude_unset=True)
    ui_config = data.pop("ui_config", None)
    s = db.query(Setting).first()
    if not s:
        s = Setting()
        db.add(s)
        db.flush()
    for k, value in data.items():
        setattr(s, k, value)
    try:
        save_ui_config(db, ui_config)
        log_audit(db, user, "settings_save", "حفظ الإعدادات", request.client.host if request else None, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر حفظ الإعدادات")
    invalidate_settings_cache()
    return {"ok": True}
