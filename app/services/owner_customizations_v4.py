"""Owner-facing POS customizations layered on top of the stable core.

This module keeps the accounting/security service code untouched while adding:
- persistent invoice product-code visibility
- compact/symmetric A4 and thermal invoice rendering
- optional customer phone/address printing
- configured branding as the real store identity (POS stays the product label)
- preservation of owner branding across legacy bootstrap cleanup
"""
from __future__ import annotations

from typing import Any

_INSTALLED = False


def _install_setting_defaults() -> None:
    from app.services import setting_service as ss

    ss.UI_DEFAULTS.setdefault("invoice_show_product_code", True)
    ss.UI_SETTINGS_KEYS = frozenset(ss.UI_DEFAULTS)

    def branding_values(setting) -> dict[str, str]:
        return {
            "store_name": (setting.store_name or "").strip() or "POS",
            "tagline": (setting.tagline or "").strip(),
            "slogan": (setting.slogan or "").strip(),
            "branch": (setting.branch or "").strip(),
            "logo": setting.logo or "",
        }

    ss._branding_values = branding_values


def _install_bootstrap_branding_guard() -> None:
    """Do not let the old demo-brand cleanup overwrite owner-entered branding."""
    from app.db import bootstrap
    from app.db.models import Setting
    from app.db.session import SessionLocal

    if getattr(bootstrap, "_owner_branding_guard_v4", False):
        return
    original = bootstrap._init_db_unlocked

    def guarded_init():
        preserved = None
        try:
            if bootstrap._table_exists("settings"):
                db = SessionLocal()
                try:
                    row = db.query(Setting).first()
                    if row:
                        preserved = {
                            "store_name": row.store_name,
                            "tagline": row.tagline,
                            "slogan": row.slogan,
                            "branch": row.branch,
                            "logo": row.logo,
                        }
                finally:
                    db.close()
        except Exception:
            preserved = None

        result = original()

        if preserved is not None:
            db = SessionLocal()
            try:
                row = db.query(Setting).first()
                if row:
                    for key, value in preserved.items():
                        setattr(row, key, value)
                    db.commit()
            finally:
                db.close()
        return result

    bootstrap._init_db_unlocked = guarded_init
    bootstrap._owner_branding_guard_v4 = True


def _install_invoice_item_code_capture() -> None:
    """Persist the real product code into new invoice item snapshots."""
    from app.api.routes import invoices as invoice_routes
    from app.db.models import Invoice, Product

    if getattr(invoice_routes, "_owner_item_code_v4", False):
        return
    original = invoice_routes.create_sale_invoice

    def create_with_code(db, *, payload, user_id, user_name):
        result = original(db, payload=payload, user_id=user_id, user_name=user_name)
        invoice = db.query(Invoice).filter(Invoice.id == int(result["id"])).first()
        if invoice:
            enriched = []
            changed = False
            for raw in list(invoice.items or []):
                item = dict(raw)
                pid = int(item.get("product_id") or 0)
                if pid > 0:
                    product = db.query(Product).filter(Product.id == pid).first()
                    if product:
                        code = (product.code or "").strip()
                        if item.get("code") != code:
                            item["code"] = code
                            changed = True
                enriched.append(item)
            if changed:
                invoice.items = enriched
        return result

    invoice_routes.create_sale_invoice = create_with_code
    invoice_routes._owner_item_code_v4 = True


def _clean_header_v4(invoice: Any, settings: dict[str, Any], content_w: float, regular: str, bold: str):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Spacer, Table, TableStyle
    from app.services import pdf_renderer as pr

    thermal = content_w < 100 * mm
    store_name = str(settings.get("store_name") or "POS").strip() or "POS"
    tagline = str(settings.get("tagline") or "").strip()
    branch = str(settings.get("branch") or "").strip()
    address = str(settings.get("address") or "").strip()
    phone = str(settings.get("phone") or "").strip()

    logo_source = settings.get("logo") or ""
    if not str(logo_source).startswith("data:image/"):
        try:
            from app.services.live_customizations import _fallback_logo_data_url
            logo_source = _fallback_logo_data_url()
        except Exception:
            logo_source = ""

    logo = pr._logo_image(logo_source, 42 * mm if thermal else 54 * mm, 25 * mm if thermal else 34 * mm)
    if logo:
        logo.hAlign = "CENTER"

    name_style = ParagraphStyle(
        "InvoiceStoreNameV4", fontName=bold, fontSize=15 if thermal else 23,
        leading=19 if thermal else 28, alignment=TA_CENTER,
        textColor=colors.HexColor(pr._NAVY_DARK),
    )
    tagline_style = ParagraphStyle(
        "InvoiceTaglineV4", fontName=bold, fontSize=9 if thermal else 12,
        leading=12 if thermal else 16, alignment=TA_CENTER,
        textColor=colors.HexColor(pr._GOLD),
    )
    small_center = ParagraphStyle(
        "InvoiceSmallCenterV4", fontName=regular, fontSize=7.8 if thermal else 9.5,
        leading=10 if thermal else 13, alignment=TA_CENTER,
        textColor=colors.HexColor(pr._NAVY_DARK),
    )
    type_style = ParagraphStyle(
        "InvoiceTypeV4", fontName=bold, fontSize=9 if thermal else 11,
        leading=12 if thermal else 14, alignment=TA_CENTER,
        textColor=colors.HexColor(pr._NAVY),
    )
    field_style = ParagraphStyle(
        "InvoiceFieldV4", fontName=regular, fontSize=8.6 if thermal else 11,
        leading=11.5 if thermal else 15, alignment=TA_RIGHT,
        textColor=colors.HexColor("#111827"),
    )
    field_bold = ParagraphStyle(
        "InvoiceFieldBoldV4", fontName=bold, fontSize=8.6 if thermal else 11,
        leading=11.5 if thermal else 15, alignment=TA_RIGHT,
        textColor=colors.HexColor(pr._NAVY_DARK),
    )

    title_flow: list[Any] = []
    if logo:
        title_flow.extend([logo, Spacer(1, 1 * mm)])
    title_flow.append(pr._p(store_name, name_style))
    if tagline:
        title_flow.append(pr._p(tagline, tagline_style))
    location_line = "، ".join(x for x in (branch, address) if x)
    if location_line:
        title_flow.append(pr._p(location_line, small_center))
    if phone:
        title_flow.append(pr._p(f"هاتف المحل: {phone}", small_center))
    title_flow.append(Spacer(1, .5 * mm))
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
    customer_name = (getattr(invoice, "customer_name", None) or "عميل نقدي").strip()
    customer_phone = (getattr(invoice, "customer_phone", None) or "").strip()
    customer_address = ""
    if getattr(invoice, "type", "sale") == "sale":
        customer_address = (getattr(invoice, "notes", None) or "").strip()
    customer_id = getattr(invoice, "customer_id", None)

    def row(label: str, value: Any):
        return [pr._p(str(value), field_style), pr._p(label, field_bold)]

    if thermal:
        rows = [
            row("اسم العميل:", customer_name),
            row("التاريخ:", pr._created_text(invoice)),
            row("رقم الفاتورة:", inv_no),
            row("رقم العملية:", operation_no),
        ]
        if customer_phone:
            rows.insert(1, row("رقم التليفون:", customer_phone))
        if customer_address:
            insert_at = 2 if customer_phone else 1
            rows.insert(insert_at, row("العنوان:", customer_address))
        meta = Table(rows, colWidths=[content_w * .64, content_w * .36])
        meta.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]))
        return [brand, Spacer(1, 2 * mm), meta, Spacer(1, 3 * mm)]

    left_rows = [
        row("التاريخ:", pr._created_text(invoice)),
        row("رقم الفاتورة:", inv_no),
        row("رقم العملية:", operation_no),
    ]
    right_rows = [row("اسم العميل:", customer_name)]
    if customer_phone:
        right_rows.append(row("رقم التليفون:", customer_phone))
    if customer_address:
        right_rows.append(row("العنوان:", customer_address))
    if customer_id:
        right_rows.append(row("رقم العميل:", customer_id))

    def field_table(rows, widths):
        table = Table(rows, colWidths=widths)
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return table

    left = field_table(left_rows, [content_w * .27, content_w * .17])
    right = field_table(right_rows, [content_w * .37, content_w * .19])
    info = Table([[left, right]], colWidths=[content_w * .44, content_w * .56])
    info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [brand, Spacer(1, 2.5 * mm), info, Spacer(1, 4 * mm)]


def _items_table_v4(invoice: Any, content_w: float, regular: str, bold: str, *, thermal: bool, items_per_page: int):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Table, TableStyle
    from app.services import pdf_renderer as pr

    items = list(getattr(invoice, "items", None) or [])
    show_code = bool(getattr(invoice, "_show_product_code_v4", True))

    if thermal:
        headers = [pr.ar("القيمة"), pr.ar("السعر"), pr.ar("الكمية"), pr.ar("الصنف"), pr.ar("م")]
        data = [headers]
        for idx, item in enumerate(items, 1):
            name = str(item.get("product_name") or "-")
            code = str(item.get("code") or item.get("barcode") or "").strip()
            product_text = name + (f"  •  {code}" if show_code and code else "")
            data.append([
                f"{pr._money(item.get('total')):.2f}",
                f"{pr._money(item.get('unit_price')):.2f}",
                pr._qty(item.get("quantity")),
                pr.ar(product_text),
                str(idx),
            ])
        widths = [content_w * .21, content_w * .19, content_w * .14, content_w * .38, content_w * .08]
        name_col = 3
    elif show_code:
        headers = [pr.ar("القيمة"), pr.ar("السعر"), pr.ar("الوحدة"), pr.ar("الكمية"), pr.ar("اسم الصنف"), pr.ar("كود الصنف"), pr.ar("م")]
        data = [headers]
        for idx, item in enumerate(items, 1):
            code = item.get("code") or item.get("barcode") or "-"
            data.append([
                f"{pr._money(item.get('total')):.2f}", f"{pr._money(item.get('unit_price')):.2f}",
                pr.ar(item.get("unit") or "قطعة"), pr._qty(item.get("quantity")),
                pr.ar(item.get("product_name") or "-"), pr.ar(code), str(idx),
            ])
        target_rows = max(len(items), max(8, int(items_per_page or 17)))
        while len(data) - 1 < target_rows:
            data.append(["", "", "", "", "", "", ""])
        widths = [content_w * .13, content_w * .13, content_w * .11, content_w * .11, content_w * .30, content_w * .17, content_w * .05]
        name_col = 4
    else:
        headers = [pr.ar("القيمة"), pr.ar("السعر"), pr.ar("الوحدة"), pr.ar("الكمية"), pr.ar("اسم الصنف"), pr.ar("م")]
        data = [headers]
        for idx, item in enumerate(items, 1):
            data.append([
                f"{pr._money(item.get('total')):.2f}", f"{pr._money(item.get('unit_price')):.2f}",
                pr.ar(item.get("unit") or "قطعة"), pr._qty(item.get("quantity")),
                pr.ar(item.get("product_name") or "-"), str(idx),
            ])
        target_rows = max(len(items), max(8, int(items_per_page or 17)))
        while len(data) - 1 < target_rows:
            data.append(["", "", "", "", "", ""])
        widths = [content_w * .15, content_w * .15, content_w * .12, content_w * .12, content_w * .40, content_w * .06]
        name_col = 4

    row_heights = [8.5 * mm if not thermal else 7 * mm] + ([7.2 * mm] * (len(data) - 1) if not thermal else [7.1 * mm] * (len(data) - 1))
    table = Table(data, colWidths=widths, rowHeights=row_heights, repeatRows=1)
    body_end = max(1, min(len(items), len(data) - 1))
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(pr._NAVY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), bold),
        ("FONTSIZE", (0, 0), (-1, 0), 10.2 if not thermal else 8.2),
        ("FONTNAME", (0, 1), (-1, -1), regular),
        ("FONTSIZE", (0, 1), (-1, -1), 9.4 if not thermal else 7.9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (name_col, 1), (name_col, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), .65, colors.HexColor(pr._BORDER)),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if items:
        style.append(("ROWBACKGROUNDS", (0, 1), (-1, body_end), [colors.white, colors.HexColor(pr._PALE)]))
    if body_end + 1 <= len(data) - 1:
        style.append(("ROWBACKGROUNDS", (0, body_end + 1), (-1, -1), [colors.HexColor(pr._PALE_2), colors.white]))
    table.setStyle(TableStyle(style))
    return table


def _install_pdf_layout() -> None:
    from app.services import pdf_renderer as pr

    if getattr(pr, "_owner_pdf_v4", False):
        return
    original_generate = pr.generate_invoice_pdf

    def generate_with_layout(invoice, settings, font_dir, *, page_size="a4", items_per_page=17):
        had_attr = hasattr(invoice, "_show_product_code_v4")
        previous = getattr(invoice, "_show_product_code_v4", None)
        invoice._show_product_code_v4 = settings.get("invoice_show_product_code", True) is not False
        try:
            return original_generate(invoice, settings, font_dir, page_size=page_size, items_per_page=items_per_page)
        finally:
            if had_attr:
                invoice._show_product_code_v4 = previous
            else:
                try:
                    delattr(invoice, "_show_product_code_v4")
                except Exception:
                    pass

    pr._header_block = _clean_header_v4
    pr._items_table = _items_table_v4
    pr.generate_invoice_pdf = generate_with_layout
    pr._owner_pdf_v4 = True


def install_owner_customizations_v4() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_setting_defaults()
    _install_bootstrap_branding_guard()
    _install_invoice_item_code_capture()
    _install_pdf_layout()
    _INSTALLED = True
