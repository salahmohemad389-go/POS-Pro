"""Invoice service layer for POS Pro.

Extracted from old main.py + services.py. Contains all business logic for:
- Creating sale invoices (with stock validation, ledger, movements)
- Creating return invoices (atomic refund with stock/ledger)
- Combined invoices (merge multiple invoices)
- Collecting payments
- Customer statements
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text, func, desc
from sqlalchemy.orm import Session

from app.db.models import Customer, Invoice, Product, StockMovement, Setting
from app.utils.helpers import r2, r3, money_n, record_ledger_entry, record_stock_movement

log = logging.getLogger("pospro.services.invoice")


def _next_invoice_number(db: Session, prefix: str = "INV") -> tuple[int, str]:
    """Allocate a unique invoice number without MAX()+1 races.

    SQLite keeps the counter update in the invoice transaction. Because SQLite has
    a single writer, this also serializes the critical write section safely.
    PostgreSQL allocates the counter in a short independent transaction so the
    global sequence row is not locked for the lifetime of the invoice transaction.
    Gaps are acceptable on PostgreSQL if an invoice later rolls back.
    """
    today_str = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y%m%d")
    bind = db.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        # Seed once from historical data. INSERT OR IGNORE is concurrency-safe.
        db.execute(text(
            "INSERT OR IGNORE INTO app_counters(name, value) "
            "SELECT 'invoice', COALESCE(MAX(number), 0) FROM invoices"
        ))
        row = db.execute(
            text("UPDATE app_counters SET value = value + 1 WHERE name='invoice' RETURNING value")
        ).first()
        if not row:
            raise RuntimeError("Invoice counter is unavailable")
        new_number = int(row[0])
    else:
        # PostgreSQL/other production DB: keep the sequence lock very short.
        with bind.begin() as conn:
            if dialect == "postgresql":
                row = conn.execute(text(
                    "INSERT INTO app_counters(name, value) "
                    "VALUES ('invoice', (SELECT COALESCE(MAX(number), 0) + 1 FROM invoices)) "
                    "ON CONFLICT (name) DO UPDATE SET value = app_counters.value + 1 "
                    "RETURNING value"
                )).first()
            else:
                # Conservative fallback for other SQLAlchemy dialects.
                conn.execute(text(
                    "INSERT INTO app_counters(name, value) "
                    "SELECT 'invoice', COALESCE(MAX(number), 0) FROM invoices "
                    "WHERE NOT EXISTS (SELECT 1 FROM app_counters WHERE name='invoice')"
                ))
                row = conn.execute(text(
                    "UPDATE app_counters SET value = value + 1 WHERE name='invoice' RETURNING value"
                )).first()
            if not row:
                raise RuntimeError("Invoice counter is unavailable")
            new_number = int(row[0])

    return new_number, f"{prefix}-{today_str}-{new_number:04d}"


def create_sale_invoice(
    db: Session,
    *,
    payload: dict,
    user_id: int,
    user_name: str,
) -> dict[str, Any]:
    """Create a sale invoice atomically.

    Validates stock, calculates totals, records stock movements + ledger entries.
    Returns dict with ok, id, number.
    """
    items = payload.get("items") or []
    if not items:
        raise ValueError("الفاتورة فارغة")
    if not isinstance(items, list) or len(items) > 1000:
        raise ValueError("عدد أصناف الفاتورة غير صالح")
    # Aggregate duplicate product rows before stock checks. This prevents a crafted
    # payload from checking each duplicate against the same pre-sale stock.
    aggregated: dict[int, float] = {}
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("صيغة عنصر الفاتورة غير صالحة")
        try:
            pid = int(raw.get("product_id") or 0)
            qty = r3(raw.get("quantity") or 0)
        except (TypeError, ValueError, ArithmeticError):
            raise ValueError("كمية أو منتج غير صالح")
        if pid <= 0 or qty <= 0 or not math.isfinite(qty):
            raise ValueError("كمية أو منتج غير صالح")
        aggregated[pid] = r3(aggregated.get(pid, 0.0) + qty)
        if aggregated[pid] > 999999999.999:
            raise ValueError("الكمية أكبر من الحد المسموح")
    items = [{"product_id": pid, "quantity": aggregated[pid]} for pid in sorted(aggregated)]

    inv_type = (payload.get("type") or "sale").strip().lower()
    if inv_type != "sale":
        raise ValueError("إنشاء المرتجعات يجب أن يتم من شاشة المرتجع المخصصة")

    # Allocate before any product reads. On SQLite this is the first write in the
    # transaction and acquires the single-writer lock before stock is inspected,
    # preventing stale read -> write upgrade races.
    new_number, inv_no = _next_invoice_number(db)

    subtotal = 0.0
    validated_items = []
    product_updates = []

    for it in items:
        pid = it.get("product_id")
        if not pid:
            raise ValueError("منتج غير محدد")
        p = (
            db.query(Product)
            .filter(Product.id == int(pid))
            .with_for_update()
            .first()
        )
        if not p:
            raise ValueError(f"منتج غير موجود: {pid}")
        qty = r3(it.get("quantity") or 0)
        if qty <= 0:
            continue
        unit_price = r2(p.price or 0)
        if unit_price < 0:
            raise ValueError(f"سعر غير صالح للمنتج: {p.name}")
        line_total = r2(qty * unit_price)
        subtotal += line_total
        validated_items.append({
            "product_id": p.id,
            "product_name": p.name,
            "barcode": p.barcode or "",
            "quantity": qty,
            "unit": p.unit or "قطعة",
            "unit_price": unit_price,
            "cost": money_n(p.cost),
            "total": line_total,
        })
        if (p.stock or 0) < qty:
            raise ValueError(f"المخزون غير كافٍ لـ {p.name} (متاح: {p.stock})")
        product_updates.append((p, float(p.stock or 0) - qty))

    if not validated_items:
        raise ValueError("لا توجد عناصر صالحة")

    try:
        discount_pct = float(payload.get("discount_pct") or 0)
    except (TypeError, ValueError):
        raise ValueError("الخصم غير صالح")
    settings_row = db.query(Setting).first()
    tax_rate = (
        float(settings_row.tax_rate or 0)
        if settings_row is not None and bool(getattr(settings_row, "vat_enabled", False))
        else 0.0
    )
    if not math.isfinite(discount_pct) or not 0 <= discount_pct <= 100:
        raise ValueError("نسبة الخصم يجب أن تكون بين 0 و100")
    if not 0 <= tax_rate <= 100:
        raise ValueError("نسبة الضريبة يجب أن تكون بين 0 و100")

    discount = r2(subtotal * discount_pct / 100)
    after_disc = r2(subtotal - discount)
    tax = r2(after_disc * tax_rate / 100)
    total = r2(after_disc + tax)

    payment_method = (payload.get("payment_method") or "cash").strip().lower()
    if payment_method not in {"cash", "credit", "partial"}:
        raise ValueError("طريقة الدفع غير صالحة")
    if payment_method == "cash":
        paid, remaining = total, 0.0
    elif payment_method == "credit":
        paid, remaining = 0.0, total
    else:
        try:
            paid_requested = float(payload.get("paid"))
        except (TypeError, ValueError):
            raise ValueError("أدخل قيمة المدفوع الجزئي")
        if (
            not math.isfinite(paid_requested)
            or paid_requested <= 0
            or paid_requested >= total - 0.001
        ):
            raise ValueError("الدفع الجزئي يجب أن يكون أكبر من صفر وأقل من إجمالي الفاتورة")
        paid = r2(paid_requested)
        remaining = r2(total - paid)

    if remaining == 0 and paid >= total:
        status_v = "paid"
    elif paid <= 0:
        status_v = "unpaid"
    else:
        status_v = "partial"

    cust_id = payload.get("customer_id")
    customer = None
    if cust_id:
        customer = (
            db.query(Customer)
            .filter(Customer.id == int(cust_id))
            .with_for_update()
            .first()
        )

    if remaining > 0 and customer is None:
        raise ValueError("البيع الآجل أو الجزئي يتطلب عميلاً مسجلاً")

    if customer:
        db_name = (customer.name or "").strip()
        db_phone = (customer.phone or "").strip()
        payload_name = (payload.get("customer_name") or "").strip()
        payload_phone = (payload.get("customer_phone") or "").strip()
        customer_name = db_name or payload_name or "عميل نقدي"
        customer_phone = db_phone or payload_phone
    else:
        customer_name = (payload.get("customer_name") or "").strip() or "عميل نقدي"
        customer_phone = (payload.get("customer_phone") or "").strip()

    inv = Invoice(
        number=new_number,
        invoice_number=inv_no,
        customer_id=customer.id if customer else None,
        customer_name=customer_name,
        customer_phone=customer_phone,
        type=inv_type,
        items=validated_items,
        subtotal=subtotal,
        discount_pct=discount_pct,
        discount=discount,
        tax_rate=tax_rate,
        tax=tax,
        total=total,
        paid=paid,
        remaining=remaining,
        status=status_v,
        payment_method=payment_method,
        user_id=user_id,
        user_name=user_name,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(inv)
    db.flush()

    for p, new_stock in product_updates:
        p.stock = r3(new_stock)

    for it in validated_items:
        record_stock_movement(
            db,
            product_id=it["product_id"],
            product_name=it["product_name"],
            quantity_delta=-float(it["quantity"]),
            unit_cost=float(it.get("cost", 0)),
            movement_type="sale",
            invoice_id=inv.id,
            invoice_number=inv.invoice_number,
            user_name=user_name,
            user_id=user_id,
        )

    if customer:
        customer.balance = r2(float(customer.balance or 0) + remaining)
        record_ledger_entry(
            db,
            customer_id=customer.id,
            customer_name=customer.name,
            invoice_id=inv.id,
            invoice_number=inv.invoice_number,
            movement_type="sale",
            description=f"فاتورة بيع {inv.invoice_number}",
            debit=float(total),
            credit=0.0,
            user_name=user_name,
            user_id=user_id,
        )
        if paid > 0:
            record_ledger_entry(
                db,
                customer_id=customer.id,
                customer_name=customer.name,
                invoice_id=inv.id,
                invoice_number=inv.invoice_number,
                movement_type="payment",
                description=f"دفع فاتورة {inv.invoice_number} ({inv.payment_method})",
                debit=0.0,
                credit=float(paid),
                user_name=user_name,
                user_id=user_id,
            )

    return {"ok": True, "id": inv.id, "number": inv.number}


def delete_sale_invoice(
    db: Session,
    *,
    invoice_id: int,
) -> None:
    """Delete only non-financial document snapshots (e.g. combined invoices)."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).with_for_update().first()
    if not inv:
        raise ValueError("فاتورة غير موجودة")
    if inv.type in ("sale", "return"):
        raise ValueError("لا يمكن حذف فاتورة بيع أو مرتجع بعد إصدارها")
    # Combined invoices are document snapshots only; deleting them must never
    # mutate stock, customer balances, ledger, or source invoices.
    db.delete(inv)


def _return_credit_for_sale(db: Session, sale_id: int) -> float:
    """Credit applied to a sale by non-cash portions of linked returns."""
    returns = db.query(Invoice).filter(
        Invoice.original_invoice_id == int(sale_id), Invoice.type == "return"
    ).all()
    return r2(sum(float(r.remaining or 0) for r in returns))


def effective_invoice_due(db: Session, inv: Invoice) -> float:
    if inv.type != "sale":
        return money_n(inv.remaining)
    return r2(max(0.0, float(inv.remaining or 0) - _return_credit_for_sale(db, inv.id)))


def collect_payment(
    db: Session,
    *,
    invoice_id: int,
    amount: float,
    user_id: int,
    user_name: str,
) -> dict[str, Any]:
    """Collect a partial/full payment on a sale invoice."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).with_for_update().first()
    if not inv:
        raise ValueError("فاتورة غير موجودة")
    if inv.type != "sale":
        raise ValueError("لا يمكن تحصيل دفعة من مرتجع")
    due_before = effective_invoice_due(db, inv)
    if due_before <= 0:
        raise ValueError("الفاتورة مسددة بالكامل بعد احتساب المرتجعات")
    amount = r2(amount)
    if amount <= 0:
        raise ValueError("قيمة غير صحيحة")
    if amount > due_before:
        raise ValueError(f"المبلغ أكبر من المتبقي الفعلي ({due_before})")

    inv.paid = r2(float(inv.paid or 0) + amount)
    inv.remaining = r2(max(0.0, float(inv.remaining or 0) - amount))
    due_after = r2(max(0.0, due_before - amount))
    inv.status = "paid" if due_after <= 0 else "partial"

    if inv.customer_id:
        c = (
            db.query(Customer)
            .filter(Customer.id == inv.customer_id)
            .with_for_update()
            .first()
        )
        if c:
            c.balance = r2(float(c.balance or 0) - amount)
            record_ledger_entry(
                db,
                customer_id=c.id,
                customer_name=c.name,
                invoice_id=inv.id,
                invoice_number=inv.invoice_number,
                movement_type="collect",
                description=f"تحصيل من فاتورة {inv.invoice_number}",
                debit=0.0,
                credit=float(amount),
                user_name=user_name,
                user_id=user_id,
            )

    return {
        "ok": True,
        "paid": money_n(inv.paid),
        "remaining": due_after,
        "status": inv.status,
    }


def get_original_for_return(
    db: Session,
    *,
    original_id: int,
) -> dict[str, Any]:
    """Return the original sale invoice + remaining returnable qty per product."""
    orig = db.query(Invoice).filter(Invoice.id == int(original_id)).first()
    if not orig:
        raise ValueError("الفاتورة غير موجودة")
    if orig.type != "sale":
        raise ValueError("الفاتورة يجب أن تكون فاتورة بيع")

    already_returned_qty: dict[int, float] = {}
    prior_returns = (
        db.query(Invoice)
        .filter(Invoice.original_invoice_id == int(original_id), Invoice.type == "return")
        .all()
    )
    prior_cash_refunds = 0.0
    for ret in prior_returns:
        prior_cash_refunds += float(ret.paid or 0)
        for it in ret.items or []:
            pid = int(it.get("product_id") or 0)
            already_returned_qty[pid] = already_returned_qty.get(pid, 0) + float(it.get("quantity", 0))

    items_with_remaining = []
    for it in orig.items or []:
        pid = int(it.get("product_id") or 0)
        sold = float(it.get("quantity", 0))
        already = already_returned_qty.get(pid, 0)
        remaining = max(0.0, sold - already)
        items_with_remaining.append({
            "product_id": pid,
            "product_name": it.get("product_name", ""),
            "barcode": it.get("barcode", ""),
            "unit": it.get("unit", "قطعة"),
            "quantity_sold": sold,
            "already_returned": already,
            "quantity_returnable": remaining,
            "unit_price": money_n(it.get("unit_price", 0)),
            "line_total": money_n(it.get("total", 0)),
        })

    return {
        "invoice": orig.to_dict(),
        "items": items_with_remaining,
        "cash_refundable": r2(max(0.0, float(orig.paid or 0) - prior_cash_refunds)),
    }


def ensure_invoice_access(user, inv: Invoice) -> None:
    """Cashiers may only access their own invoices."""
    if user.role == "cashier" and inv.user_id != user.id:
        raise ValueError("لا تملك صلاحية لعرض هذه الفاتورة")
    if user.role not in ("admin", "manager", "cashier"):
        raise ValueError("لا تملك صلاحية")


# ═══════════════════════════════════════════════════
# Return invoice (refund) - from old services.py
# ═══════════════════════════════════════════════════
def create_return_invoice(
    db: Session,
    *,
    customer_id: int,
    original_invoice_id: int,
    items: list[dict[str, Any]],
    payment_method: str = "cash",
    paid: Optional[float] = None,
    user_name: str = "",
    user_id: Optional[int] = None,
    notes: str = "",
) -> dict[str, Any]:
    """Create a return invoice that references the original sale.

    Uses the ORIGINAL unit_price for each item (NOT current product price).
    Validates quantities not exceeding originally sold quantity.
    Adds stock back to inventory and records CustomerLedger entries.
    """
    if not customer_id:
        raise ValueError("يجب اختيار العميل")
    if not original_invoice_id:
        raise ValueError("يجب اختيار الفاتورة الأصلية")
    if not items:
        raise ValueError("لا توجد أصناف للإرجاع")

    orig = db.query(Invoice).filter(Invoice.id == int(original_invoice_id)).with_for_update().first()
    if not orig:
        raise ValueError("الفاتورة الأصلية غير موجودة")
    if orig.type != "sale":
        raise ValueError("الفاتورة الأصلية يجب أن تكون فاتورة بيع")
    if orig.customer_id != int(customer_id):
        raise ValueError("العميل لا يطابق فاتورة البيع الأصلية")

    customer = db.query(Customer).filter(Customer.id == int(customer_id)).first()
    if not customer:
        raise ValueError("العميل غير موجود")

    orig_items_by_pid: dict[int, dict[str, Any]] = {}
    for it in orig.items or []:
        pid = int(it.get("product_id") or 0)
        if not pid:
            continue
        orig_items_by_pid[pid] = {
            "product_id": pid, "product_name": it.get("product_name", ""),
            "barcode": it.get("barcode", ""), "unit": it.get("unit", "قطعة"),
            "quantity_sold": float(it.get("quantity", 0)),
            "unit_price": float(it.get("unit_price", 0)),
            "cost": float(it.get("cost", 0)),
        }

    already_returned_qty: dict[int, float] = {}
    prior_returns = db.query(Invoice).filter(
        Invoice.original_invoice_id == int(original_invoice_id), Invoice.type == "return"
    ).all()
    prior_cash_refunds = 0.0
    for ret in prior_returns:
        prior_cash_refunds += float(ret.paid or 0)
        for it in ret.items or []:
            pid = int(it.get("product_id") or 0)
            already_returned_qty[pid] = already_returned_qty.get(pid, 0) + float(it.get("quantity", 0))

    aggregated_return: dict[int, float] = {}
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("صيغة عنصر المرتجع غير صالحة")
        try:
            pid = int(raw.get("product_id") or 0)
            qty = r3(raw.get("quantity") or 0)
        except (TypeError, ValueError, ArithmeticError):
            raise ValueError("عنصر مرتجع غير صالح")
        if pid <= 0 or qty <= 0 or not math.isfinite(qty):
            raise ValueError("عنصر مرتجع غير صالح")
        aggregated_return[pid] = r3(aggregated_return.get(pid, 0.0) + qty)
    items = [{"product_id": pid, "quantity": aggregated_return[pid]} for pid in sorted(aggregated_return)]

    validated_items: list[dict[str, Any]] = []
    subtotal = 0.0
    for item in items:
        pid = int(item.get("product_id") or 0)
        if not pid:
            raise ValueError("منتج غير محدد في عنصر الإرجاع")
        if pid not in orig_items_by_pid:
            raise ValueError(f"المنتج {pid} غير موجود في الفاتورة الأصلية")
        orig_item = orig_items_by_pid[pid]
        qty = r3(item.get("quantity") or 0)
        if qty <= 0:
            continue
        sold = orig_item["quantity_sold"]
        ret_already = already_returned_qty.get(pid, 0)
        if ret_already + qty > sold + 0.0001:
            raise ValueError(f"لا يمكن إرجاع {qty} من {orig_item['product_name']} - تم بيع {sold} وتم إرجاع {ret_already}")

        unit_price = float(orig_item["unit_price"])
        line_total = r2(qty * unit_price)
        subtotal += line_total
        validated_items.append({
            "product_id": pid, "product_name": orig_item["product_name"],
            "barcode": orig_item["barcode"], "unit": orig_item["unit"],
            "quantity": qty, "unit_price": unit_price, "cost": float(orig_item["cost"]),
            "total": line_total, "original_quantity": sold, "already_returned": ret_already,
        })

    if not validated_items:
        raise ValueError("لا توجد عناصر صالحة للإرجاع")

    discount_pct = r2(orig.discount_pct or 0)
    tax_rate = r2(orig.tax_rate or 0)
    discount = r2(subtotal * discount_pct / 100)
    taxable = r2(subtotal - discount)
    tax = r2(taxable * tax_rate / 100)
    total = r2(taxable + tax)
    method = (payment_method or "cash").strip().lower()
    if method not in {"cash", "credit", "partial"}:
        raise ValueError("طريقة رد المرتجع غير صالحة")
    # Refund method semantics are explicit and server-authoritative:
    # cash = full cash refund, credit = no cash (reduce account debt),
    # partial = a strictly partial cash refund with the rest credited to account.
    available_cash = r2(max(0.0, float(orig.paid or 0) - prior_cash_refunds))
    if method == "credit":
        refund_now = 0.0
    elif method == "cash":
        if available_cash + 0.001 < total:
            raise ValueError(
                f"لا يمكن رد المرتجع بالكامل نقداً؛ المتاح من المدفوع نقداً {available_cash:.2f}. "
                "استخدم مرتجع على الحساب أو جزئي"
            )
        if paid is not None and abs(r2(paid) - total) > 0.001:
            raise ValueError("المرتجع النقدي يجب أن يرد قيمة المرتجع كاملة")
        refund_now = total
    else:
        if paid is None:
            raise ValueError("أدخل قيمة الرد النقدي الجزئي")
        refund_now = r2(paid)
        if not math.isfinite(refund_now) or refund_now <= 0 or refund_now >= total - 0.001:
            raise ValueError("الرد الجزئي يجب أن يكون أكبر من صفر وأقل من قيمة المرتجع")
        if refund_now > available_cash + 0.001:
            raise ValueError(f"المبلغ النقدي القابل للرد لا يتجاوز {available_cash:.2f}")
    remaining_to_refund = r2(total - refund_now)

    if refund_now >= total:
        status_v = "paid"
    elif refund_now > 0:
        status_v = "partial"
    else:
        status_v = "unpaid"

    new_number, inv_no = _next_invoice_number(db)
    inv = Invoice(
        number=new_number, invoice_number=inv_no,
        customer_id=customer.id,
        customer_name=(customer.name or "").strip() or "عميل نقدي",
        customer_phone=(customer.phone or "").strip(),
        type="return", items=validated_items,
        subtotal=subtotal, discount_pct=discount_pct, discount=discount, tax_rate=tax_rate, tax=tax,
        total=total, paid=refund_now, remaining=remaining_to_refund,
        status=status_v, payment_method=method,
        user_id=user_id, user_name=user_name,
        notes=notes or f"مرتجع من فاتورة {orig.invoice_number or orig.number}",
        original_invoice_id=orig.id,
        parent_number=orig.invoice_number or f"#{orig.number}",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(inv)
    db.flush()

    for it in validated_items:
        pid = it["product_id"]
        product = db.query(Product).filter(Product.id == pid).with_for_update().first()
        if product:
            product.stock = r3(float(product.stock or 0) + it["quantity"])
        record_stock_movement(
            db, product_id=pid, product_name=it["product_name"],
            quantity_delta=+float(it["quantity"]), unit_cost=float(it.get("cost", 0)),
            movement_type="return", invoice_id=inv.id, invoice_number=inv.invoice_number,
            user_name=user_name, user_id=user_id,
            notes=f"مرتجع من {orig.invoice_number or orig.number}",
        )

    customer = db.query(Customer).filter(Customer.id == int(customer_id)).with_for_update().first()
    if not customer:
        raise ValueError("العميل غير موجود")
    customer.balance = r2(float(customer.balance or 0) - float(total) + float(refund_now))
    record_ledger_entry(
        db, customer_id=customer.id, customer_name=customer.name,
        invoice_id=inv.id, invoice_number=inv.invoice_number,
        movement_type="return", description=f"مرتجع من {orig.invoice_number or orig.number}",
        debit=0.0, credit=float(total), user_name=user_name, user_id=user_id,
    )
    if refund_now > 0:
        record_ledger_entry(
            db, customer_id=customer.id, customer_name=customer.name,
            invoice_id=inv.id, invoice_number=inv.invoice_number,
            movement_type="refund",
            description=f"رد نقدي للمرتجع {inv.invoice_number} ({payment_method})",
            debit=float(refund_now), credit=0.0, user_name=user_name, user_id=user_id,
        )

    return {
        "id": inv.id, "number": inv.number, "invoice_number": inv.invoice_number,
        "total": money_n(inv.total), "paid": money_n(inv.paid),
        "remaining": money_n(inv.remaining), "status": inv.status,
        "original_invoice_id": orig.id,
        "original_invoice_number": orig.invoice_number or f"#{orig.number}",
    }


# ═══════════════════════════════════════════════════
# Customer account statement (كشف حساب العميل)
# ═══════════════════════════════════════════════════
def get_customer_statement(
    db: Session, customer_id: int, *, limit: int = 2000
) -> dict[str, Any]:
    """Return an account statement with full-history summary and bounded events.

    The financial summary always covers the customer's complete history. The
    event timeline is bounded for browser/server safety and explicitly marks
    truncation instead of silently hiding it.
    """
    from app.db.models import CustomerLedger

    customer = db.query(Customer).filter(Customer.id == int(customer_id)).first()
    if not customer:
        raise ValueError("العميل غير موجود")
    limit = max(100, min(int(limit or 2000), 5000))

    invoice_query = db.query(Invoice).filter(
        Invoice.customer_id == int(customer_id), Invoice.type.in_(["sale", "return"])
    )
    invoice_count = invoice_query.count()
    invoices = (
        invoice_query.order_by(desc(Invoice.created_at), desc(Invoice.id))
        .limit(limit).all()
    )
    invoices.reverse()

    ledger_query = db.query(CustomerLedger).filter(CustomerLedger.customer_id == int(customer_id))
    ledger_limit = min(limit * 2, 10000)
    ledger_count = ledger_query.count()
    ledger = (
        ledger_query.order_by(desc(CustomerLedger.created_at), desc(CustomerLedger.id))
        .limit(ledger_limit).all()
    )
    ledger.reverse()

    ledger_balance_by_invoice: dict[int, float] = {}
    for le in ledger:
        if le.invoice_id:
            ledger_balance_by_invoice[le.invoice_id] = money_n(le.balance_after)

    invoice_ids = {inv.id for inv in invoices}
    ledger_types_by_invoice: dict[int, set[str]] = {}
    for le in ledger:
        if le.invoice_id:
            ledger_types_by_invoice.setdefault(int(le.invoice_id), set()).add(le.movement_type or "")

    timeline: list[tuple] = []
    for inv in invoices:
        timeline.append((inv.created_at or datetime.min, 0, "invoice", inv))
    for le in ledger:
        if le.invoice_id in invoice_ids and le.movement_type in ("sale", "return"):
            continue
        timeline.append((le.created_at or datetime.min, 1, "ledger", le))
    timeline.sort(key=lambda t: (t[0], t[1]))

    events: list[dict[str, Any]] = []
    running_balance = 0.0
    for _date, _prio, kind, obj in timeline:
        if kind == "invoice":
            inv = obj
            is_return = inv.type == "return"
            sale_amt = 0.0 if is_return else money_n(inv.total)
            return_amt = money_n(inv.total) if is_return else 0.0
            related_types = ledger_types_by_invoice.get(inv.id, set())
            if is_return:
                paid_amt = 0.0 if "refund" in related_types else money_n(inv.paid)
            else:
                paid_amt = 0.0 if related_types.intersection({"payment", "collect"}) else money_n(inv.paid)
            balance = ledger_balance_by_invoice.get(inv.id)
            if balance is None:
                delta = money_n(inv.remaining) if not is_return else -money_n(inv.total)
                running_balance = r2(running_balance + delta)
                balance = running_balance
            else:
                running_balance = balance
            description = (
                f"فاتورة بيع {inv.invoice_number or ('#' + str(inv.number))}"
                if not is_return else f"مرتجع من {inv.parent_number or '-'}"
            )
            events.append({
                "date": inv.created_at.isoformat() if inv.created_at else "",
                "type": "invoice", "movement_type": inv.type, "id": inv.id,
                "number": inv.number,
                "invoice_number": inv.invoice_number or f"#{inv.number}",
                "description": description,
                "subtotal": money_n(inv.subtotal), "discount": money_n(inv.discount),
                "tax": money_n(inv.tax), "total": money_n(inv.total),
                "paid": paid_amt, "remaining": money_n(inv.remaining),
                "sale": sale_amt, "return": return_amt, "balance": balance,
                "status": inv.status, "payment_method": inv.payment_method,
                "notes": inv.notes or "",
                "original_invoice_id": inv.original_invoice_id,
                "parent_number": inv.parent_number,
            })
        else:
            le = obj
            running_balance = money_n(le.balance_after)
            is_payment = le.movement_type in ("payment", "collect")
            description = le.description or ("دفعة من العميل" if is_payment else "تسوية حساب")
            events.append({
                "date": le.created_at.isoformat() if le.created_at else "",
                "type": "ledger", "movement_type": le.movement_type, "id": le.id,
                "description": description, "invoice_number": le.invoice_number or "",
                "debit": money_n(le.debit), "credit": money_n(le.credit),
                "sale": 0.0, "return": 0.0,
                "paid": money_n(le.credit) if is_payment else 0.0,
                "balance": running_balance, "balance_after": running_balance,
            })

    # Full-history totals, independent of the bounded timeline window.
    grouped = db.query(
        Invoice.type,
        func.coalesce(func.sum(Invoice.total), 0),
        func.coalesce(func.sum(Invoice.paid), 0),
    ).filter(
        Invoice.customer_id == int(customer_id), Invoice.type.in_(["sale", "return"])
    ).group_by(Invoice.type).all()
    totals_by_type = {str(t): (float(total or 0), float(paid or 0)) for t, total, paid in grouped}
    sale_total, sale_paid = totals_by_type.get("sale", (0.0, 0.0))
    return_total, return_paid = totals_by_type.get("return", (0.0, 0.0))
    total_sales = r2(sale_total)
    total_returns = r2(return_total)
    net_sales = r2(total_sales - total_returns)
    total_paid = r2(sale_paid - return_paid)
    current_balance = money_n(customer.balance)
    total_remaining = current_balance if current_balance > 0 else 0.0
    truncated = invoice_count > len(invoices) or ledger_count > len(ledger)

    return {
        "customer": {
            "id": customer.id, "name": customer.name,
            "phone": customer.phone or "", "notes": customer.notes or "",
            "balance": current_balance,
        },
        "columns": ["date", "description", "invoice_number", "sale", "return", "paid", "balance"],
        "truncated": truncated,
        "event_limit": limit,
        "total_invoices": invoice_count,
        "total_ledger_entries": ledger_count,
        "summary": {
            "total_sales": total_sales, "total_returns": total_returns,
            "net_sales": net_sales, "total_paid": total_paid,
            "total_remaining": total_remaining, "total_debts": total_remaining,
            "current_balance": current_balance,
            "invoice_count": invoice_count, "transaction_count": ledger_count,
        },
        "events": events,
    }

