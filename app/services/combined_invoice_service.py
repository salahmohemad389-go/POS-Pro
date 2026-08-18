"""Combined invoice service for POS Pro.

Handles:
- Building combined PDFs from multiple invoices
- Persisting combined invoice records
- Merging items across invoices
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.db.models import Invoice
from app.utils.helpers import r2, r3, money_n

log = logging.getLogger("pospro.services.combined")

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
FONT_DIR = STATIC_DIR / "assets" / "fonts"

DEFAULT_COMBINED_OPTIONS: dict[str, bool] = {
    "include_details": True,
    "print_summary": True,
    "deduct_returns": True,
    "show_paid_remaining": True,
    "save_to_customer": True,
    "auto_print": False,
}


def _resolve_combined_options(options: Optional[dict[str, Any]]) -> dict[str, bool]:
    opts = dict(DEFAULT_COMBINED_OPTIONS)
    if options:
        for k in DEFAULT_COMBINED_OPTIONS:
            if k in options and options[k] is not None:
                opts[k] = bool(options[k])
    return opts


def _fetch_invoices_for_combine(db: Session, invoice_ids: list[int]):
    unique_ids = list(dict.fromkeys(int(x) for x in invoice_ids))
    if not unique_ids:
        raise ValueError("لا توجد فواتير للدمج")
    if len(unique_ids) > 50:
        raise ValueError("الحد الأقصى 50 فاتورة في الفاتورة المجمعة")

    rows = db.query(Invoice).filter(Invoice.id.in_(unique_ids)).all()
    by_id = {row.id: row for row in rows}

    missing = [iid for iid in unique_ids if iid not in by_id]
    if missing:
        raise ValueError(f"بعض الفواتير المختارة غير موجودة: {', '.join(map(str, missing))}")

    unsupported = [
        by_id[iid].invoice_number or f"#{by_id[iid].number}"
        for iid in unique_ids
        if by_id[iid].type not in ("sale", "return")
    ]
    if unsupported:
        raise ValueError(
            "لا يمكن دمج فاتورة مجمعة داخل فاتورة مجمعة أخرى: "
            + ", ".join(unsupported)
        )

    return [by_id[iid] for iid in unique_ids]


def _merge_items(
    invoices: list, opts: dict[str, bool]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge items across multiple invoices. Returns (merged_items, totals_dict)."""
    merged: dict[tuple, dict[str, Any]] = {}
    order: list[tuple] = []

    for inv in invoices:
        sign = -1 if inv.type == "return" and opts["deduct_returns"] else 1
        if inv.type == "return" and not opts["deduct_returns"]:
            continue
        for it in inv.items or []:
            key = (
                it.get("product_id") or it.get("product_name") or "-",
                r2(it.get("unit_price") or 0),
                it.get("unit") or "قطعة",
            )
            if key not in merged:
                merged[key] = {
                    "product_id": it.get("product_id"),
                    "product_name": it.get("product_name", "-"),
                    "unit": it.get("unit", "قطعة"),
                    "unit_price": float(it.get("unit_price") or 0),
                    "quantity": 0.0,
                    "total": 0.0,
                }
                order.append(key)
            merged[key]["quantity"] += float(it.get("quantity") or 0) * sign
            merged[key]["total"] += float(it.get("total") or 0) * sign

    merged_items = []
    for key in order:
        item = merged[key]
        item["quantity"] = r3(item["quantity"])
        item["total"] = r2(item["total"])
        if abs(item["quantity"]) > 0.0001 or abs(item["total"]) > 0.009:
            merged_items.append(item)

    sales_total = r2(sum(money_n(i.total) for i in invoices if i.type == "sale"))
    returns_total = r2(sum(money_n(i.total) for i in invoices if i.type == "return"))
    sales_paid = r2(sum(money_n(i.paid) for i in invoices if i.type == "sale"))
    returns_paid = r2(sum(money_n(i.paid) for i in invoices if i.type == "return"))
    if opts["deduct_returns"]:
        total = r2(max(0.0, sales_total - returns_total))
        paid = r2(max(0.0, sales_paid - returns_paid))
    else:
        total = sales_total
        paid = sales_paid
    paid = r2(min(paid, total))
    remaining = r2(max(0.0, total - paid))

    totals = {
        "sales_total": sales_total,
        "returns_total": returns_total,
        "total_discount": r2(sum(((-1 if i.type == "return" and opts["deduct_returns"] else 1) * money_n(i.discount)) for i in invoices if i.type != "return" or opts["deduct_returns"])),
        "paid": paid,
        "remaining": remaining,
        "total": total,
    }
    return merged_items, totals


def build_combined_invoice_pdf(
    db: Session,
    settings: dict[str, Any],
    invoice_ids: list[int],
    options: Optional[dict[str, Any]] = None,
) -> bytes:
    """Build ONE combined invoice PDF from the selected invoices."""
    from app.services.pdf_renderer import generate_invoice_pdf

    opts = _resolve_combined_options(options)
    invoices = _fetch_invoices_for_combine(db, invoice_ids)
    merged_items, totals = _merge_items(invoices, opts)

    if not merged_items:
        raise ValueError("الفواتير المختارة لا تنتج أصنافاً صافية للطباعة")

    customer_ids = {i.customer_id for i in invoices}
    customer_names = {str(i.customer_name or "").strip() for i in invoices}
    same_customer = len(customer_ids) == 1 and len(customer_names) == 1
    first = invoices[0]
    numbers = [i.invoice_number or f"#{i.number}" for i in invoices]

    combined = SimpleNamespace(
        id=None, number=0,
        invoice_number="مجمعة: " + " + ".join(numbers),
        customer_id=first.customer_id if same_customer else None,
        customer_name=(first.customer_name or "عميل نقدي") if same_customer else "فواتير مختارة",
        customer_phone=(first.customer_phone or "") if same_customer else "",
        type="combined", items=merged_items,
        subtotal=totals["total"], discount_pct=0,
        discount=totals["total_discount"],
        tax_rate=0, tax=0, total=totals["total"],
        paid=totals["paid"] if opts["show_paid_remaining"] else 0,
        remaining=totals["remaining"] if opts["show_paid_remaining"] else 0,
        status="paid" if totals["remaining"] <= 0.009 else ("partial" if totals["paid"] > 0 else "unpaid"),
        payment_method="mixed", user_name=first.user_name or "",
        notes="الفواتير المختارة: " + ", ".join(numbers),
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    try:
        items_per_page = int(settings.get("max_items_per_page") or 17)
    except (TypeError, ValueError):
        items_per_page = 17
    if items_per_page < 5:
        items_per_page = 17
    page_size = (settings.get("invoice_format") or "a4").lower()
    return generate_invoice_pdf(
        invoice=combined, settings=settings, font_dir=FONT_DIR,
        page_size=page_size, items_per_page=items_per_page,
    )


def create_combined_invoice(
    db: Session,
    *,
    invoice_ids: list[int],
    user,
    options: Optional[dict[str, Any]] = None,
) -> Invoice:
    """Create + persist a combined invoice record (type=\"combined\")."""
    from app.services.invoice_service import _next_invoice_number

    opts = _resolve_combined_options(options)
    invoices = _fetch_invoices_for_combine(db, invoice_ids)
    if len(invoices) > 50:
        raise ValueError("الحد الأقصى 50 فاتورة في الفاتورة المجمعة")

    merged_items, totals = _merge_items(invoices, opts)
    if not merged_items:
        raise ValueError("الفواتير المختارة لا تنتج أصنافاً صافية")

    customer_ids = {inv.customer_id for inv in invoices}
    if len(customer_ids) != 1 or None in customer_ids:
        raise ValueError("يجب أن تكون جميع الفواتير المجمعة لنفس العميل المسجل")
    if opts["save_to_customer"] and invoices[0].customer_id:
        customer_id = invoices[0].customer_id
        customer_name = invoices[0].customer_name or "-"
        customer_phone = invoices[0].customer_phone or "-"
    else:
        customer_id = None
        customer_name = (
            invoices[0].customer_name
            if len(customer_ids) == 1
            else "مجموعة فواتير متعددة العملاء"
        )
        customer_phone = invoices[0].customer_phone or "-"

    status = (
        "paid" if totals["remaining"] <= 0.009
        else ("partial" if totals["paid"] > 0 else "unpaid")
    )
    source_ids = [inv.id for inv in invoices]
    source_numbers = [inv.invoice_number or f"#{inv.number}" for inv in invoices]

    new_number, inv_no = _next_invoice_number(db, prefix="MRG")
    inv = Invoice(
        number=new_number,
        invoice_number=inv_no,
        customer_id=customer_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        type="combined",
        items=merged_items,
        subtotal=totals["total"],
        discount_pct=0,
        discount=totals["total_discount"],
        tax_rate=0,
        tax=0,
        total=totals["total"],
        paid=totals["paid"],
        remaining=totals["remaining"],
        status=status,
        payment_method="mixed",
        user_id=getattr(user, "id", None),
        user_name=getattr(user, "name", None) or "",
        notes=f"فاتورة مجمعة من {len(invoices)} فاتورة: {', '.join(source_numbers)}",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        combined_source_ids=source_ids,
        combined_options=opts,
    )
    db.add(inv)
    db.flush()
    return inv
