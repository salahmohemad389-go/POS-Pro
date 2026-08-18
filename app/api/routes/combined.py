"""Combined invoice routes for POS Pro."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.permissions import has_permission
from app.db.models import Invoice
from app.db.session import get_db
from app.core.security import get_current_user
from app.db.models import User
from app.services.audit_service import log_audit
from app.services.setting_service import get_settings_cached
from app.schemas.requests import CombinedCreate

router = APIRouter(prefix="/api/combined-invoice", tags=["combined"])


def _rate_limit_or_403(key: str, limit_type: str):
    from app.core.ratelimit import consume_attempt
    from fastapi import status
    allowed, remaining = consume_attempt(key, limit_type)
    if not allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"تجاوزت الحد المسموح. حاول بعد {remaining // 60 + 1} دقيقة")


@router.get("/pdf")
async def combined_invoice_pdf(
    request: Request,
    ids: str = Query(..., description="Comma-separated invoice IDs"),
    include_details: bool = Query(True),
    print_summary: bool = Query(True),
    deduct_returns: bool = Query(True),
    show_paid_remaining: bool = Query(True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not has_permission(user, "invoice_view"):
        raise HTTPException(403, "لا تملك صلاحية")
    _rate_limit_or_403(f"export:{user.id}", "export")
    try:
        invoice_ids = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, "معرفات الفواتير يجب أن تكون أرقام")
    if not invoice_ids:
        raise HTTPException(400, "حدد فواتير للدمج")
    if len(invoice_ids) > 50:
        raise HTTPException(400, "الحد الأقصى 50 فاتورة")
    if user.role == "cashier":
        owned = db.query(Invoice.id).filter(Invoice.id.in_(invoice_ids), Invoice.user_id == user.id).count()
        if owned != len(set(invoice_ids)):
            raise HTTPException(403, "لا يمكنك دمج فواتير تخص مستخدماً آخر")

    settings = get_settings_cached(db)
    options = {"include_details": include_details, "print_summary": print_summary, "deduct_returns": deduct_returns, "show_paid_remaining": show_paid_remaining}
    try:
        from app.services.combined_invoice_service import build_combined_invoice_pdf
        pdf_bytes = build_combined_invoice_pdf(db, settings, invoice_ids, options=options)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        raise HTTPException(500, "فشل إنشاء الفاتورة المجمعة بسبب خطأ داخلي")

    log_audit(db, user, "combined_invoice_pdf", f"فاتورة مجمعة من {len(invoice_ids)} فاتورة", request.client.host if request else None)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="combined_invoice.pdf"', "Content-Length": str(len(pdf_bytes))},
    )


@router.post("")
async def create_combined_invoice_endpoint(payload: CombinedCreate, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "invoice_create"):
        raise HTTPException(403, "لا تملك صلاحية لإنشاء فاتورة")
    _rate_limit_or_403(f"invoice_create:{user.id}", "write")
    invoice_ids = payload.ids
    if user.role == "cashier":
        owned = db.query(Invoice.id).filter(Invoice.id.in_(invoice_ids), Invoice.user_id == user.id).count()
        if owned != len(invoice_ids):
            raise HTTPException(403, "لا يمكنك دمج فواتير تخص مستخدماً آخر")
    options = payload.options.model_dump()
    try:
        from app.services.combined_invoice_service import create_combined_invoice
        inv = create_combined_invoice(db, invoice_ids=invoice_ids, user=user, options=options)
        log_audit(db, user, "combined_invoice_create", f"فاتورة مجمعة {inv.invoice_number} من {len(invoice_ids)} فاتورة", request.client.host if request else None, commit=False)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    except Exception:
        db.rollback()
        raise HTTPException(500, "فشل إنشاء الفاتورة المجمعة بسبب خطأ داخلي")
    return {"invoice": inv.to_dict()}
