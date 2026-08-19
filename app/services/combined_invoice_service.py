"""Combined invoice service for POS Pro.

A combined invoice is deliberately rendered by the exact same invoice renderer
as a normal sale. The only differences are the ``combined`` label and the fact
that source items are netted/merged into one ordered item list.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.db.models import Invoice
from app.utils.helpers import money_n, r2, r3

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
        for key in DEFAULT_COMBINED_OPTIONS:
            if key in options and options[key] is not None:
                opts[key] = bool(options[key])
    return opts


def _fetch_invoices_for_combine(db: Session, invoice_ids: list[int]) -> list[Invoice]:
    """Fetch selected invoices while preserving the exact user selection order."""
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
        raise ValueError("لا يمكن دمج فاتورة مجمعة داخل فاتورة مجمعة أخرى: " + ", ".join(unsupported))
    return [by_id[iid] for iid in unique_ids]


def _expand_with_linked_returns(db: Session, selected: list[Invoice], opts: dict[str, bool]) -> tuple[list[Invoice], list[Invoice]]:
    """Add returns tied to selected sale invoices automatically.

    The cashier should select the sales they want to combine; they do not need
    to hunt for and select every return document separately. Explicitly selected
    return invoices remain supported and are de-duplicated.
    """
    if not opts["deduct_returns"]:
        return [inv for inv in selected if inv.type != "return"], []

    selected_ids = {inv.id for inv in selected}
    sale_ids = [inv.id for inv in selected if inv.type == "sale"]
    linked: list[Invoice] = []
    if sale_ids:
        linked = (
            db.query(Invoice)
            .filter(Invoice.type == "return", Invoice.original_invoice_id.in_(sale_ids))
            .order_by(Invoice.created_at.asc(), Invoice.id.asc())
            .all()
        )

    effective = list(selected)
    for ret in linked:
        if ret.id not in selected_ids:
            effective.append(ret)
            selected_ids.add(ret.id)
    return effective, linked


def _item_key(item: dict[str, Any]) -> tuple[Any, str]:
    identity: Any = item.get("product_id")
    if not identity:
        identity = str(item.get("product_name") or "-").strip().casefold()
    return identity, str(item.get("unit") or "قطعة").strip().casefold()


def _merge_items(invoices: list[Invoice], opts: dict[str, bool]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge products by identity and preserve first-sale appearance order.

    Price differences do not create duplicate rows. The displayed unit price is
    the weighted historical net price so ``quantity × unit_price`` stays aligned
    with the merged historical line value.
    """
    merged: dict[tuple[Any, str], dict[str, Any]] = {}
    order: list[tuple[Any, str]] = []

    # Establish visual order from sale invoices first: invoice 1 products, then
    # new products first seen in invoice 2, and so on.
    for inv in invoices:
        if inv.type == "return":
            continue
        for item in inv.items or []:
            key = _item_key(item)
            if key not in merged:
                merged[key] = {
                    "product_id": item.get("product_id"),
                    "product_name": item.get("product_name", "-"),
                    "barcode": item.get("barcode") or "",
                    "unit": item.get("unit", "قطعة"),
                    "quantity": 0.0,
                    "total": 0.0,
                    "unit_price": 0.0,
                }
                order.append(key)

    for inv in invoices:
        if inv.type == "return" and not opts["deduct_returns"]:
            continue
        sign = -1 if inv.type == "return" else 1
        for item in inv.items or []:
            key = _item_key(item)
            if key not in merged:
                # Handles an explicitly selected standalone return without its
                # source sale while keeping deterministic order.
                merged[key] = {
                    "product_id": item.get("product_id"),
                    "product_name": item.get("product_name", "-"),
                    "barcode": item.get("barcode") or "",
                    "unit": item.get("unit", "قطعة"),
                    "quantity": 0.0,
                    "total": 0.0,
                    "unit_price": 0.0,
                }
                order.append(key)
            merged[key]["quantity"] += float(item.get("quantity") or 0) * sign
            merged[key]["total"] += float(item.get("total") or 0) * sign

    merged_items: list[dict[str, Any]] = []
    for key in order:
        item = merged[key]
        qty = r3(item["quantity"])
        total = r2(item["total"])
        # A fully returned product disappears from the combined invoice.
        if qty <= 0.0001:
            continue
        item["quantity"] = qty
        item["total"] = total
        item["unit_price"] = r2(total / qty) if qty else 0.0
        merged_items.append(item)

    def signed_sum(field: str) -> float:
        value = 0.0
        for inv in invoices:
            if inv.type == "return" and not opts["deduct_returns"]:
                continue
            sign = -1 if inv.type == "return" else 1
            value += sign * money_n(getattr(inv, field, 0))
        return r2(value)

    subtotal = max(0.0, signed_sum("subtotal"))
    discount = max(0.0, signed_sum("discount"))
    tax = max(0.0, signed_sum("tax"))
    total = max(0.0, signed_sum("total"))
    paid = max(0.0, signed_sum("paid"))
    paid = r2(min(paid, total))
    remaining = r2(max(0.0, total - paid))

    totals = {
        "subtotal": r2(subtotal),
        "total_discount": r2(discount),
        "tax": r2(tax),
        "paid": paid,
        "remaining": remaining,
        "total": r2(total),
    }
    return merged_items, totals


def _combined_customer(invoices: list[Invoice]) -> tuple[int | None, str, str]:
    sales = [inv for inv in invoices if inv.type == "sale"] or invoices
    customer_ids = {inv.customer_id for inv in sales}
    customer_names = {str(inv.customer_name or "").strip() for inv in sales}
    same_customer = len(customer_ids) == 1 and len(customer_names) == 1
    first = sales[0]
    return (
        first.customer_id if same_customer else None,
        (first.customer_name or "عميل نقدي") if same_customer else "فواتير مختارة",
        (first.customer_phone or "") if same_customer else "",
    )


def _temporary_combined(invoices: list[Invoice], merged_items: list[dict[str, Any]], totals: dict[str, Any], opts: dict[str, bool]):
    first = next((inv for inv in invoices if inv.type == "sale"), invoices[0])
    customer_id, customer_name, customer_phone = _combined_customer(invoices)
    source_numbers = [inv.invoice_number or f"#{inv.number}" for inv in invoices if inv.type == "sale"]
    return SimpleNamespace(
        id=None,
        number=0,
        invoice_number="مجمعة",
        customer_id=customer_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        type="combined",
        items=merged_items,
        subtotal=totals["subtotal"],
        discount_pct=0,
        discount=totals["total_discount"],
        tax_rate=0,
        tax=totals["tax"],
        total=totals["total"],
        paid=totals["paid"] if opts["show_paid_remaining"] else 0,
        remaining=totals["remaining"] if opts["show_paid_remaining"] else 0,
        status="paid" if totals["remaining"] <= 0.009 else ("partial" if totals["paid"] > 0 else "unpaid"),
        payment_method="mixed",
        user_name=first.user_name or "",
        notes="الفواتير: " + ", ".join(source_numbers),
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )


def build_combined_invoice_pdf(
    db: Session,
    settings: dict[str, Any],
    invoice_ids: list[int],
    options: Optional[dict[str, Any]] = None,
) -> bytes:
    """Build one normal-looking PDF with merged/net items."""
    from app.services.pdf_renderer import generate_invoice_pdf

    opts = _resolve_combined_options(options)
    selected = _fetch_invoices_for_combine(db, invoice_ids)
    invoices, _linked = _expand_with_linked_returns(db, selected, opts)
    merged_items, totals = _merge_items(invoices, opts)
    if not merged_items:
        raise ValueError("الفواتير المختارة لا تنتج أصنافاً صافية للطباعة")
    combined = _temporary_combined(invoices, merged_items, totals, opts)

    try:
        items_per_page = int(settings.get("max_items_per_page") or 17)
    except (TypeError, ValueError):
        items_per_page = 17
    if items_per_page < 5:
        items_per_page = 17
    page_size = (settings.get("invoice_format") or "a4").lower()
    return generate_invoice_pdf(
        invoice=combined,
        settings=settings,
        font_dir=FONT_DIR,
        page_size=page_size,
        items_per_page=items_per_page,
    )


def create_combined_invoice(
    db: Session,
    *,
    invoice_ids: list[int],
    user,
    options: Optional[dict[str, Any]] = None,
) -> Invoice:
    """Persist a combined invoice snapshot without stock/debt side effects."""
    from app.services.invoice_service import _next_invoice_number

    opts = _resolve_combined_options(options)
    selected = _fetch_invoices_for_combine(db, invoice_ids)
    invoices, linked_returns = _expand_with_linked_returns(db, selected, opts)
    merged_items, totals = _merge_items(invoices, opts)
    if not merged_items:
        raise ValueError("الفواتير المختارة لا تنتج أصنافاً صافية")

    sales = [inv for inv in selected if inv.type == "sale"]
    customer_ids = {inv.customer_id for inv in sales}
    if not sales or len(customer_ids) != 1 or None in customer_ids:
        raise ValueError("يجب أن تكون فواتير البيع المختارة لنفس العميل المسجل")

    first = sales[0]
    customer_id = first.customer_id if opts["save_to_customer"] else None
    customer_name = first.customer_name or "-"
    customer_phone = first.customer_phone or "-"
    status = "paid" if totals["remaining"] <= 0.009 else ("partial" if totals["paid"] > 0 else "unpaid")
    source_numbers = [inv.invoice_number or f"#{inv.number}" for inv in sales]
    selected_ids = [inv.id for inv in selected]
    applied_return_ids = [inv.id for inv in invoices if inv.type == "return"]

    new_number, inv_no = _next_invoice_number(db, prefix="MRG")
    stored_options: dict[str, Any] = dict(opts)
    stored_options["applied_return_ids"] = applied_return_ids
    inv = Invoice(
        number=new_number,
        invoice_number=inv_no,
        customer_id=customer_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        type="combined",
        items=merged_items,
        subtotal=totals["subtotal"],
        discount_pct=0,
        discount=totals["total_discount"],
        tax_rate=0,
        tax=totals["tax"],
        total=totals["total"],
        paid=totals["paid"] if opts["show_paid_remaining"] else 0,
        remaining=totals["remaining"] if opts["show_paid_remaining"] else 0,
        status=status,
        payment_method="mixed",
        user_id=getattr(user, "id", None),
        user_name=getattr(user, "name", None) or "",
        notes=(
            f"فاتورة مجمعة من {len(sales)} فاتورة: {', '.join(source_numbers)}"
            + (f" • تم خصم {len(applied_return_ids)} مرتجع مرتبط" if applied_return_ids else "")
        ),
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        combined_source_ids=selected_ids,
        combined_options=stored_options,
    )
    db.add(inv)
    db.flush()
    return inv
