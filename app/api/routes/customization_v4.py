"""Owner customization endpoints for invoice display metadata and app identity."""
from __future__ import annotations

import base64
import json
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.permissions import has_permission
from app.core.security import get_current_user
from app.db.models import Invoice, Setting, User
from app.db.session import get_db
from app.services.audit_service import log_audit
from app.services.setting_service import (
    UI_DEFAULTS,
    get_settings_cached,
    invalidate_settings_cache,
    save_ui_settings,
)

router = APIRouter(tags=["owner-customization-v4"])
STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "static"


def _clean_text(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


@router.post("/api/invoices/{invoice_id}/display-meta", include_in_schema=False)
async def save_invoice_display_meta(
    invoice_id: int,
    request: Request,
    payload: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist optional phone/address before the normal print flow continues."""
    if not has_permission(user, "invoice_create"):
        raise HTTPException(403, "لا تملك صلاحية")
    invoice = db.query(Invoice).filter(Invoice.id == int(invoice_id)).first()
    if not invoice:
        raise HTTPException(404, "فاتورة غير موجودة")
    if invoice.type != "sale":
        raise HTTPException(409, "بيانات العرض الإضافية متاحة لفاتورة البيع فقط")
    if invoice.user_id != user.id and not (bool(getattr(user, "is_owner", False)) or user.role in {"admin", "manager"}):
        raise HTTPException(403, "لا يمكنك تعديل فاتورة مستخدم آخر")

    phone = _clean_text(payload.get("phone"), 40)
    address = _clean_text(payload.get("address"), 300)
    invoice.customer_phone = phone
    # Sale notes were unused in the normal checkout path; in v4 they carry the
    # optional delivery/address line shown under customer identity.
    invoice.notes = address
    try:
        log_audit(
            db,
            user,
            "invoice_display_meta",
            f"تحديث بيانات عرض الفاتورة #{invoice.number}",
            request.client.host if request else None,
            commit=False,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر حفظ بيانات الفاتورة الاختيارية")
    return {"ok": True}


@router.post("/api/settings/invoice-layout", include_in_schema=False)
async def save_invoice_layout(
    request: Request,
    payload: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not has_permission(user, "settings_save"):
        raise HTTPException(403, "لا تملك صلاحية")
    value = payload.get("show_product_code")
    if not isinstance(value, bool):
        raise HTTPException(422, "قيمة إظهار كود الصنف غير صالحة")
    try:
        save_ui_settings(db, {"invoice_show_product_code": value})
        log_audit(
            db,
            user,
            "invoice_layout_save",
            "إظهار كود الصنف في الفاتورة" if value else "إخفاء كود الصنف من الفاتورة",
            request.client.host if request else None,
            commit=False,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر حفظ إعداد شكل الفاتورة")
    invalidate_settings_cache()
    return {"ok": True, "invoice_show_product_code": value}


@router.post("/api/settings/reset-site", include_in_schema=False)
async def reset_site_settings(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reset site/configuration only. Operational/accounting data is untouched."""
    if not has_permission(user, "settings_save"):
        raise HTTPException(403, "لا تملك صلاحية")
    setting = db.query(Setting).first()
    if not setting:
        setting = Setting(id=1)
        db.add(setting)

    defaults = {
        "store_name": "POS",
        "branch": "",
        "phone": "",
        "address": "",
        "currency": "ج.م",
        "tax_rate": 0,
        "vat_enabled": False,
        "footer": "شكراً لك على ثقتك",
        "copies": 1,
        "logo": "",
        "header_position": "top",
        "quick_qty": "1,5,10,20,30,50,100",
        "printer_type": "browser",
        "auto_print_after_sale": False,
        "theme": "light",
        "tagline": "",
        "slogan": "",
        "custom_lines": "",
        "invoice_format": "a4",
        "max_items_per_page": 15,
        "header_note": "",
        "terms_conditions": "",
        "warranty_text": "",
        "feature_reports_enabled": True,
        "feature_suppliers_enabled": True,
    }
    for key, value in defaults.items():
        setattr(setting, key, value)
    try:
        save_ui_settings(db, dict(UI_DEFAULTS))
        log_audit(
            db,
            user,
            "site_settings_reset",
            "إعادة إعدادات الموقع والهوية والطباعة للوضع الافتراضي بدون حذف البيانات التشغيلية",
            request.client.host if request else None,
            commit=False,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر تنفيذ Reset للموقع")
    invalidate_settings_cache()
    return {"ok": True, "settings": get_settings_cached(db)}


def _configured_icon(settings: dict) -> tuple[bytes, str]:
    logo = str(settings.get("logo") or "")
    prefixes = {
        "data:image/png;base64,": "image/png",
        "data:image/jpeg;base64,": "image/jpeg",
        "data:image/gif;base64,": "image/gif",
        "data:image/webp;base64,": "image/webp",
    }
    for prefix, media_type in prefixes.items():
        if logo.startswith(prefix):
            try:
                return base64.b64decode(logo[len(prefix):], validate=True), media_type
            except Exception:
                break
    path = STATIC_DIR / "assets" / "logo.png"
    if path.exists():
        return path.read_bytes(), "image/png"
    return b"", "image/png"


@router.get("/app-icon", include_in_schema=False)
async def app_icon(db: Session = Depends(get_db)):
    data, media_type = _configured_icon(get_settings_cached(db))
    return Response(content=data, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.get("/manifest.webmanifest", include_in_schema=False)
async def manifest(db: Session = Depends(get_db)):
    settings = get_settings_cached(db)
    name = _clean_text(settings.get("store_name") or "POS", 200) or "POS"
    payload = {
        "name": name,
        "short_name": name[:30],
        "description": f"{name} - POS",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": str(settings.get("primary_color") or "#2563eb"),
        "icons": [
            {"src": "/app-icon", "sizes": "192x192", "purpose": "any maskable"},
            {"src": "/app-icon", "sizes": "512x512", "purpose": "any maskable"},
        ],
    }
    return Response(
        content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-store"},
    )
