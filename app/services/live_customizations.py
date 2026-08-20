"""Small runtime customizations for the live POS deployment.

Keeps the core service modules stable while applying the owner's current invoice
requirements: reversible invoice deletion with an admin audit snapshot and a
cleaner invoice header/logo layout.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Customer, CustomerLedger, Invoice, Product, StockMovement
from app.services.audit_service import log_audit as _base_log_audit
from app.utils.helpers import money_n, r2, r3

_AUDIT_SNAPSHOT_KEY = "_pos_deleted_invoice_snapshot"


def _invoice_snapshot(inv: Invoice) -> str:
    items = []
    for item in list(inv.items or [])[:100]:
        items.append({
            "product_id": item.get("product_id"),
            "name": item.get("product_name") or "",
            "code": item.get("code") or item.get("barcode") or "",
            "qty": item.get("quantity") or 0,
            "unit_price": item.get("unit_price") or 0,
            "total": item.get("total") or 0,
        })
    payload = {
        "id": inv.id,
        "number": inv.number,
        "invoice_number": inv.invoice_number or f"#{inv.number}",
        "type": inv.type,
        "customer_id": inv.customer_id,
        "customer_name": inv.customer_name or "",
        "customer_phone": inv.customer_phone or "",
        "total": money_n(inv.total),
        "paid": money_n(inv.paid),
        "remaining": money_n(inv.remaining),
        "status": inv.status,
        "payment_method": inv.payment_method,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "items": items,
        "items_truncated": max(0, len(inv.items or []) - len(items)),
    }
    return "نسخة الفاتورة المحذوفة=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _safe_delete_invoice(db: Session, *, invoice_id: int) -> None:
    """Delete an invoice while reversing its live stock/debt effects.

    Sale invoices with linked returns must have those return documents removed
    first so stock and customer debt cannot be left in an ambiguous state.
    """
    inv = db.query(Invoice).filter(Invoice.id == int(invoice_id)).with_for_update().first()
    if not inv:
        raise ValueError("فاتورة غير موجودة")

    snapshot = _invoice_snapshot(inv)

    if inv.type == "sale":
        linked_returns = db.query(Invoice).filter(
            Invoice.original_invoice_id == inv.id,
            Invoice.type == "return",
        ).count()
        if linked_returns:
            raise ValueError("احذف المرتجعات المرتبطة بهذه الفاتورة أولاً ثم احذف فاتورة البيع")

        stock_updates: list[tuple[Product, float]] = []
        for item in inv.items or []:
            pid = int(item.get("product_id") or 0)
            qty = r3(item.get("quantity") or 0)
            if pid <= 0 or qty <= 0:
                continue
            product = db.query(Product).filter(Product.id == pid).with_for_update().first()
            if not product:
                raise ValueError(f"لا يمكن حذف الفاتورة بأمان لأن المنتج رقم {pid} لم يعد موجوداً")
            stock_updates.append((product, qty))
        for product, qty in stock_updates:
            product.stock = r3(float(product.stock or 0) + qty)

        if inv.customer_id:
            customer = db.query(Customer).filter(Customer.id == inv.customer_id).with_for_update().first()
            if customer:
                # inv.remaining already reflects later collections. With linked
                # returns forbidden here, this is exactly the invoice's current
                # contribution to the customer's debt.
                customer.balance = r2(float(customer.balance or 0) - float(inv.remaining or 0))

    elif inv.type == "return":
        stock_updates: list[tuple[Product, float]] = []
        for item in inv.items or []:
            pid = int(item.get("product_id") or 0)
            qty = r3(item.get("quantity") or 0)
            if pid <= 0 or qty <= 0:
                continue
            product = db.query(Product).filter(Product.id == pid).with_for_update().first()
            if not product:
                raise ValueError(f"لا يمكن حذف المرتجع بأمان لأن المنتج رقم {pid} لم يعد موجوداً")
            if float(product.stock or 0) + 0.0001 < qty:
                raise ValueError(f"لا يمكن حذف المرتجع لأن مخزون {product.name} أقل من الكمية التي ستُسحب")
            stock_updates.append((product, qty))
        for product, qty in stock_updates:
            product.stock = r3(float(product.stock or 0) - qty)

        if inv.customer_id:
            customer = db.query(Customer).filter(Customer.id == inv.customer_id).with_for_update().first()
            if customer:
                # A return reduces debt only by the non-cash portion (remaining).
                customer.balance = r2(float(customer.balance or 0) + float(inv.remaining or 0))

    # Remove operational rows tied to the deleted document. The audit snapshot
    # is stored separately and intentionally remains visible to admins.
    db.query(CustomerLedger).filter(CustomerLedger.invoice_id == inv.id).delete(synchronize_session=False)
    db.query(StockMovement).filter(StockMovement.invoice_id == inv.id).delete(synchronize_session=False)
    db.delete(inv)
    db.info[_AUDIT_SNAPSHOT_KEY] = snapshot


def _audit_with_deleted_snapshot(
    db: Session,
    user,
    action: str,
    details: str,
    ip: str | None = None,
    *,
    commit: bool = True,
) -> None:
    if action == "invoice_delete":
        snapshot = db.info.pop(_AUDIT_SNAPSHOT_KEY, "")
        if snapshot:
            details = f"{details} | {snapshot}"
    _base_log_audit(db, user, action, details, ip, commit=commit)


def _fallback_logo_data_url() -> str:
    path = Path(__file__).resolve().parent.parent.parent / "static" / "assets" / "logo.png"
    if not path.exists():
        return ""
    try:
        return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception:
        return ""


def _invoice_logo(settings: dict[str, Any]) -> str:
    configured = str(settings.get("logo") or "").strip()
    if configured.startswith("data:image/"):
        return configured
    return _fallback_logo_data_url()


def _clean_invoice_header(invoice: Any, settings: dict[str, Any], content_w: float, regular: str, bold: str):
    """Large centered logo + plain metadata values with no underline rules."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Spacer, Table, TableStyle
    from app.services import pdf_renderer as pr

    store_name = str(settings.get("store_name") or "POS").strip() or "POS"
    tagline = str(settings.get("tagline") or "").strip()
    branch = str(settings.get("branch") or "").strip()
    address = str(settings.get("address") or "").strip()
    phone = str(settings.get("phone") or "").strip()

    logo = pr._logo_image(_invoice_logo(settings), 52 * mm, 34 * mm)
    if logo:
        logo.hAlign = "CENTER"

    name_style = ParagraphStyle("InvoiceStoreNameV3", fontName=bold, fontSize=22, leading=27, alignment=TA_CENTER, textColor=colors.HexColor(pr._NAVY_DARK))
    tagline_style = ParagraphStyle("InvoiceTaglineV3", fontName=bold, fontSize=12, leading=16, alignment=TA_CENTER, textColor=colors.HexColor(pr._GOLD))
    small_center = ParagraphStyle("InvoiceSmallCenterV3", fontName=regular, fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.HexColor(pr._NAVY_DARK))
    type_style = ParagraphStyle("InvoiceTypeV3", fontName=bold, fontSize=10, leading=13, alignment=TA_CENTER, textColor=colors.HexColor(pr._NAVY))
    field_style = ParagraphStyle("InvoiceFieldV3", fontName=regular, fontSize=10, leading=14, alignment=TA_RIGHT, textColor=colors.HexColor("#111827"))
    field_bold = ParagraphStyle("InvoiceFieldBoldV3", fontName=bold, fontSize=10, leading=14, alignment=TA_RIGHT, textColor=colors.HexColor(pr._NAVY_DARK))

    title_flow: list[Any] = []
    if logo:
        title_flow.extend([logo, Spacer(1, 2 * mm)])
    title_flow.append(pr._p(store_name, name_style))
    if tagline:
        title_flow.append(pr._p(tagline, tagline_style))
    address_line = "، ".join(x for x in (branch, address) if x)
    if address_line:
        title_flow.append(pr._p(address_line, small_center))
    if phone:
        title_flow.append(pr._p(f"هاتف: {phone}", small_center))
    title_flow.append(Spacer(1, 1 * mm))
    title_flow.append(pr._p(pr._invoice_type(invoice), type_style))

    brand = Table([[title_flow]], colWidths=[content_w])
    brand.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    inv_no = getattr(invoice, "invoice_number", None) or f"#{getattr(invoice, 'number', '-') or '-'}"
    raw_operation = getattr(invoice, "number", None)
    try:
        operation_no = f"{int(raw_operation):04d}"
    except Exception:
        operation_no = str(raw_operation or "-")
    customer_id = getattr(invoice, "customer_id", None)
    customer_no = str(customer_id) if customer_id else "-"
    customer_name = getattr(invoice, "customer_name", None) or "عميل نقدي"
    customer_phone = getattr(invoice, "customer_phone", None) or "-"

    left_fields = Table([
        [pr._p(pr._created_text(invoice), field_style), pr._p("التاريخ:", field_bold)],
        [pr._p(inv_no, field_style), pr._p("رقم الفاتورة:", field_bold)],
        [pr._p(operation_no, field_style), pr._p("رقم العملية:", field_bold)],
    ], colWidths=[content_w * .26, content_w * .16])
    right_fields = Table([
        [pr._p(customer_name, field_style), pr._p("اسم العميل:", field_bold)],
        [pr._p(customer_phone, field_style), pr._p("رقم تليفون العميل:", field_bold)],
        [pr._p(customer_no, field_style), pr._p("رقم العميل:", field_bold)],
    ], colWidths=[content_w * .36, content_w * .22])

    for table in (left_fields, right_fields):
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            # Intentionally no LINEBELOW: populated invoice metadata is printed
            # as normal text instead of looking like a blank form field.
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

    info = Table([[left_fields, right_fields]], colWidths=[content_w * .42, content_w * .58])
    info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [brand, Spacer(1, 4 * mm), info, Spacer(1, 5 * mm)]


def install_live_customizations() -> None:
    """Patch the already-imported route/renderer globals exactly once."""
    from app.api.routes import invoices as invoice_routes
    from app.services import pdf_renderer

    if getattr(invoice_routes, "_live_customizations_v3", False):
        return
    invoice_routes.delete_sale_invoice = _safe_delete_invoice
    invoice_routes.log_audit = _audit_with_deleted_snapshot
    pdf_renderer._header_block = _clean_invoice_header
    invoice_routes._live_customizations_v3 = True
