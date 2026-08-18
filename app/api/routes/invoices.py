"""Invoice routes for POS Pro."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import desc, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.permissions import has_permission
from app.db.models import Customer, Invoice, Product
from app.db.session import get_db
from app.core.security import get_current_user
from app.db.models import User
from app.services.audit_service import log_audit
from app.services.invoice_service import (
    create_sale_invoice,
    delete_sale_invoice,
    collect_payment,
    get_original_for_return,
    ensure_invoice_access,
    create_return_invoice,
    effective_invoice_due,
)
from app.services.setting_service import get_settings_cached
from app.utils.helpers import money_n, r2
from app.schemas.requests import CollectPayment, ReturnCreate, InvoiceCreate

router = APIRouter(prefix="/api/invoices", tags=["invoices"])
log = logging.getLogger("pospro.invoices")


def _rate_limit_or_403(key: str, limit_type: str):
    from app.core.ratelimit import consume_attempt
    from fastapi import status
    allowed, remaining = consume_attempt(key, limit_type)
    if not allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"تجاوزت الحد المسموح. حاول بعد {remaining // 60 + 1} دقيقة")


@router.get("")
async def list_invoices(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    q: Optional[str] = None,
    filter: Optional[str] = "all",
    customer_id: Optional[int] = None,
    skip_total: bool = Query(False, description="Skip total count for faster pagination"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Invoice)
    if customer_id:
        query = query.filter(Invoice.customer_id == customer_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(Invoice.customer_name.ilike(like), Invoice.invoice_number.ilike(like)))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if filter == "today":
        query = query.filter(Invoice.created_at >= datetime(now.year, now.month, now.day))
    elif filter == "month":
        query = query.filter(Invoice.created_at >= datetime(now.year, now.month, 1))
    elif filter == "year":
        query = query.filter(Invoice.created_at >= datetime(now.year, 1, 1))
    if user.role == "cashier":
        query = query.filter(Invoice.user_id == user.id)
    items = query.order_by(desc(Invoice.created_at), desc(Invoice.id)).offset((page - 1) * limit).limit(limit).all()
    total = -1 if skip_total else query.count()
    return {"total": total, "page": page, "limit": limit, "items": [inv.to_dict() for inv in items]}


@router.get("/{iid}")
async def get_invoice(iid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == iid).first()
    if not inv:
        raise HTTPException(404, "فاتورة غير موجودة")
    try:
        ensure_invoice_access(user, inv)
    except ValueError as e:
        raise HTTPException(403, str(e))
    data = inv.to_dict()
    if inv.type == "sale":
        data["effective_remaining"] = effective_invoice_due(db, inv)
    else:
        data["effective_remaining"] = money_n(inv.remaining)
    return data


@router.get("/{iid}/pdf")
async def get_invoice_pdf(iid: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == iid).first()
    if not inv:
        raise HTTPException(404, "فاتورة غير موجودة")
    if not has_permission(user, "invoice_view"):
        raise HTTPException(403, "لا تملك صلاحية")
    try:
        ensure_invoice_access(user, inv)
    except ValueError as e:
        raise HTTPException(403, str(e))
    settings = get_settings_cached(db)
    _rate_limit_or_403(f"export:{user.id}", "export")
    try:
        items_per_page = int(settings.get("max_items_per_page") or 17)
    except (TypeError, ValueError):
        items_per_page = 17
    if items_per_page < 5:
        items_per_page = 17
    page_size = (settings.get("invoice_format") or "a4").lower()
    try:
        from app.services.pdf_service import generate_invoice_pdf
        pdf_bytes = generate_invoice_pdf(invoice=inv, settings=settings, page_size=page_size, items_per_page=items_per_page)
    except ImportError:
        raise HTTPException(503, "خدمة PDF غير متاحة حالياً")
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception:
        log.exception("Invoice PDF generation failed for invoice %s", iid)
        raise HTTPException(500, "فشل إنشاء PDF بسبب خطأ داخلي")
    if not pdf_bytes:
        raise HTTPException(500, "فشل إنشاء PDF")
    inv_no = inv.invoice_number or f"INV-{inv.number}"
    safe_name = inv_no.replace("/", "_").replace("\\", "_")
    log_audit(db, user, "invoice_pdf", f"PDF للفاتورة #{inv.number}", request.client.host if request else None)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="invoice_{safe_name}.pdf"', "Content-Length": str(len(pdf_bytes))},
    )


@router.post("")
async def create_invoice(payload: InvoiceCreate, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _rate_limit_or_403(f"invoice_create:{user.id}", "write")
    if not has_permission(user, "invoice_create"):
        raise HTTPException(403, "لا تملك صلاحية لإنشاء فاتورة")
    try:
        data = payload.model_dump()
        result = create_sale_invoice(db, payload=data, user_id=user.id, user_name=user.name)
        log_audit(db, user, "invoice_create", f"فاتورة {data.get('type', 'sale')} #{result['number']}", request.client.host if request else None, commit=False)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    except Exception:
        db.rollback()
        log.exception("Invoice creation failed")
        raise HTTPException(500, "تعذر إنشاء الفاتورة بسبب خطأ داخلي")


@router.delete("/{iid}")
async def delete_invoice(iid: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _rate_limit_or_403(f"invoice_delete:{user.id}", "delete")
    if not has_permission(user, "invoice_delete"):
        raise HTTPException(403, "لا تملك صلاحية")
    try:
        delete_sale_invoice(db, invoice_id=iid)
        log_audit(db, user, "invoice_delete", f"حذف فاتورة #{iid}", request.client.host if request else None, commit=False)
        db.commit()
        return {"ok": True}
    except ValueError as exc:
        db.rollback()
        msg = str(exc)
        status_code = 404 if "غير موجودة" in msg else 409 if "لا يمكن" in msg else 400
        raise HTTPException(status_code, msg)
    except Exception:
        db.rollback()
        log.exception("Invoice deletion failed for invoice %s", iid)
        raise HTTPException(500, "تعذر حذف المستند بسبب خطأ داخلي")


@router.post("/{iid}/collect")
async def collect_payment_endpoint(iid: int, payload: CollectPayment, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "invoice_collect"):
        raise HTTPException(403, "لا تملك صلاحية للتحصيل")
    try:
        inv = db.query(Invoice).filter(Invoice.id == iid).first()
        if not inv:
            raise HTTPException(404, "فاتورة غير موجودة")
        try:
            ensure_invoice_access(user, inv)
        except ValueError as exc:
            raise HTTPException(403, str(exc))
        amount = r2(payload.amount)
        result = collect_payment(db, invoice_id=iid, amount=amount, user_id=user.id, user_name=user.name)
        log_audit(db, user, "invoice_collect", f"تحصيل {amount} من فاتورة #{iid}", request.client.host if request else None, commit=False)
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    except Exception:
        db.rollback()
        log.exception("Invoice payment collection failed for invoice %s", iid)
        raise HTTPException(500, "تعذر تنفيذ التحصيل بسبب خطأ داخلي")


@router.post("/return")
async def create_return(payload: ReturnCreate, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _rate_limit_or_403(f"invoice_create:{user.id}", "write")
    if not has_permission(user, "invoice_create"):
        raise HTTPException(403, "لا تملك صلاحية")
    try:
        orig = db.query(Invoice).filter(Invoice.id == payload.original_invoice_id).first()
        if not orig:
            raise HTTPException(404, "الفاتورة الأصلية غير موجودة")
        try:
            ensure_invoice_access(user, orig)
        except ValueError as exc:
            raise HTTPException(403, str(exc))
        result = create_return_invoice(
            db,
            customer_id=payload.customer_id,
            original_invoice_id=payload.original_invoice_id,
            items=[item.model_dump() for item in payload.items],
            payment_method=payload.payment_method,
            paid=payload.paid,
            user_name=user.name,
            user_id=user.id,
            notes=payload.notes,
        )
        log_audit(db, user, "invoice_return", f"مرتجع #{result['number']} من فاتورة {result['original_invoice_number']}", request.client.host if request else None, commit=False)
        db.commit()
        return {"ok": True, **result}
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    except SQLAlchemyError:
        db.rollback()
        log.exception("Return invoice database error")
        raise HTTPException(500, "تعذر إنشاء المرتجع بسبب خطأ داخلي في قاعدة البيانات")


@router.get("/return-original-items/{original_id}")
async def get_original_invoice_for_return(original_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "invoice_create"):
        raise HTTPException(403, "لا تملك صلاحية")
    try:
        orig = db.query(Invoice).filter(Invoice.id == original_id).first()
        if not orig:
            raise HTTPException(404, "الفاتورة غير موجودة")
        try:
            ensure_invoice_access(user, orig)
        except ValueError as exc:
            raise HTTPException(403, str(exc))
        return get_original_for_return(db, original_id=original_id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(400, str(exc))

