"""Customer routes for POS Pro."""

from __future__ import annotations

from pathlib import Path

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.core.permissions import has_permission
from app.db.models import Customer, Invoice, CustomerLedger
from app.db.session import get_db
from app.core.security import get_current_user
from app.db.models import User
from app.services.audit_service import log_audit
from app.services.import_service import export_customers, import_customers as do_import, write_csv, write_xlsx
from app.utils.helpers import money_n, r2, record_ledger_entry
from app.schemas.requests import CustomerSave, CollectPayment

router = APIRouter(prefix="/api/customers", tags=["customers"])


def _rate_limit_or_403(key: str, limit_type: str):
    from app.core.ratelimit import consume_attempt
    from fastapi import status
    allowed, remaining = consume_attempt(key, limit_type)
    if not allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"تجاوزت الحد المسموح. حاول بعد {remaining // 60 + 1} دقيقة")


@router.get("")
async def list_customers(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    q: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Customer)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(Customer.name.ilike(like), Customer.phone.ilike(like)))
    total = query.count()
    items = query.order_by(Customer.name).offset((page - 1) * limit).limit(limit).all()
    return {"total": total, "page": page, "limit": limit, "items": [c.to_dict() for c in items]}


@router.post("")
async def save_customer(payload: CustomerSave, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _rate_limit_or_403(f"customer_write:{user.id}", "write")
    data = payload.model_dump()
    cid = data.get("id")
    needed_perm = "customer_save" if cid else "customer_create"
    if not has_permission(user, needed_perm):
        raise HTTPException(403, "لا تملك صلاحية")
    name = data["name"].strip()
    if not name:
        raise HTTPException(400, "أدخل اسم العميل")
    if cid:
        c = db.query(Customer).filter(Customer.id == cid).first()
        if not c:
            raise HTTPException(404, "عميل غير موجود")
    else:
        c = Customer(balance=0)
        db.add(c)
    c.name = name
    c.phone = data.get("phone", "").strip()
    c.notes = data.get("notes", "").strip()
    try:
        log_audit(db, user, "customer_save", f"{'تعديل' if cid else 'إضافة'} عميل: {name}", request.client.host if request else None, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر حفظ العميل")
    return {"ok": True, "id": c.id}



@router.get("/{cid:int}")
async def get_customer(cid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "customer_view"):
        raise HTTPException(403, "لا تملك صلاحية")
    c = db.query(Customer).filter(Customer.id == cid).first()
    if not c:
        raise HTTPException(404, "عميل غير موجود")
    return c.to_dict()

@router.delete("/{cid}")
async def delete_customer(cid: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _rate_limit_or_403(f"customer_delete:{user.id}", "delete")
    if not has_permission(user, "customer_delete"):
        raise HTTPException(403, "لا تملك صلاحية")
    c = db.query(Customer).filter(Customer.id == cid).first()
    if not c:
        raise HTTPException(404, "عميل غير موجود")
    name = c.name
    inv_count = db.query(Invoice).filter(Invoice.customer_id == cid).count()
    ledger_count = db.query(CustomerLedger).filter(CustomerLedger.customer_id == cid).count()
    if inv_count or ledger_count or abs(float(c.balance or 0)) > 0.0001:
        raise HTTPException(409, "لا يمكن حذف العميل لوجود تاريخ مالي أو رصيد مرتبط به.")
    db.delete(c)
    try:
        log_audit(db, user, "customer_delete", f"حذف عميل بدون فواتير: {name}", request.client.host if request else None, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر حذف العميل")
    return {"ok": True}


@router.post("/{cid}/collect")
async def collect_customer_debt(cid: int, payload: CollectPayment, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "invoice_collect") or user.role == "cashier":
        raise HTTPException(403, "التحصيل من إجمالي حساب العميل متاح للمدير فقط؛ الكاشير يحصّل من فواتيره الفردية")
    try:
        amount = r2(payload.amount)
        if amount <= 0:
            raise HTTPException(400, "قيمة غير صحيحة")
        c_preview = db.query(Customer).filter(Customer.id == cid).first()
        if not c_preview:
            raise HTTPException(404, "عميل غير موجود")
        remaining_amount = amount
        invoices = db.query(Invoice).filter(
            Invoice.customer_id == cid, Invoice.type == "sale"
        ).order_by(Invoice.created_at.asc(), Invoice.id.asc()).with_for_update().all()
        c = db.query(Customer).filter(Customer.id == cid).with_for_update().first()
        if not c:
            raise HTTPException(404, "عميل غير موجود")
        if amount > r2(c.balance or 0):
            raise HTTPException(400, f"المبلغ أكبر من الديون ({c.balance})")
        invoice_ids = [inv.id for inv in invoices]
        return_credits = {}
        if invoice_ids:
            rows = db.query(Invoice.original_invoice_id, func.coalesce(func.sum(Invoice.remaining), 0)).filter(
                Invoice.type == "return", Invoice.original_invoice_id.in_(invoice_ids)
            ).group_by(Invoice.original_invoice_id).all()
            return_credits = {int(iid): r2(total or 0) for iid, total in rows if iid}
        for inv in invoices:
            if remaining_amount <= 0:
                break
            due = r2(max(0.0, float(inv.remaining or 0) - return_credits.get(inv.id, 0.0)))
            if due <= 0:
                continue
            applied = r2(min(remaining_amount, due))
            inv.paid = r2(float(inv.paid or 0) + applied)
            inv.remaining = r2(max(0.0, float(inv.remaining or 0) - applied))
            due_after = r2(max(0.0, due - applied))
            inv.status = "paid" if due_after <= 0 else "partial"
            record_ledger_entry(
                db, customer_id=c.id, customer_name=c.name, invoice_id=inv.id,
                invoice_number=inv.invoice_number, movement_type="collect",
                description=f"تحصيل من فاتورة {inv.invoice_number}", debit=0.0, credit=applied,
                user_name=user.name, user_id=user.id,
            )
            remaining_amount = r2(remaining_amount - applied)

        if remaining_amount > 0.001:
            raise HTTPException(409, "تعذر توزيع كامل مبلغ التحصيل على الفواتير المستحقة")
        c.balance = r2(float(c.balance or 0) - amount)
        log_audit(db, user, "debt_collect", f"تحصيل {amount} من العميل: {c.name}", request.client.host if request else None, commit=False)
        db.commit()
        return {"ok": True, "balance": r2(c.balance)}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر تنفيذ التحصيل")


@router.get("/export")
async def export_customers_endpoint(request: Request, format: str = "xlsx", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    from datetime import datetime as dt
    if not has_permission(user, "customer_export"):
        raise HTTPException(403, "لا تملك صلاحية")
    _rate_limit_or_403(f"export:{user.id}", "export")
    result = export_customers(db)
    ts = dt.now().strftime('%Y%m%d_%H%M%S')
    if format == "csv":
        path = write_csv(result["headers"], result["rows"], "customers")
        filename = f"customers_{ts}.csv"
        media_type = "text/csv; charset=utf-8"
    else:
        path = write_xlsx(result["headers"], result["rows"], "customers")
        filename = f"customers_{ts}.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    log_audit(db, user, "customers_export", f"تصدير {format.upper()}: {result['count']} سجل", request.client.host if request else None)
    from starlette.background import BackgroundTask
    cleanup = BackgroundTask(lambda p=str(path): Path(p).unlink(missing_ok=True))
    return FileResponse(str(path), media_type=media_type, filename=filename, headers={"Content-Disposition": f'attachment; filename="{filename}"'}, background=cleanup)


@router.post("/import")
async def import_customers_endpoint(request: Request, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "customer_save"):
        raise HTTPException(403, "لا تملك صلاحية")
    _rate_limit_or_403(f"customer_import:{user.id}", "write")
    filename = (file.filename or "").lower()
    raw = await file.read()
    result = do_import(db, raw, filename)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "فشل"))
    log_audit(db, user, "customers_import", f"استيراد {result['added']} عميل من {filename}", request.client.host if request else None)
    return result


@router.get("/{cid}/statement")
async def customer_statement(cid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.invoice_service import get_customer_statement
    if not has_permission(user, "customer_view") or user.role == "cashier":
        raise HTTPException(403, "كشف الحساب الكامل متاح للمدير فقط")
    try:
        return get_customer_statement(db, int(cid))
    except ValueError as exc:
        raise HTTPException(404, str(exc))
