"""Final invoice density/layout tuning for the market build."""
from __future__ import annotations

from typing import Any

_INSTALLED = False


def _compact_a4_header(invoice: Any, settings: dict[str, Any], content_w: float, regular: str, bold: str):
    """A4 header with logo and store identity side-by-side instead of stacked."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Spacer, Table, TableStyle
    from app.services import pdf_renderer as pr

    def clean_text(value: Any) -> str:
        # Preserve normal Arabic word separation and remove accidental repeated
        # whitespace copied from the settings form.
        return " ".join(str(value or "").split())

    store_name = clean_text(settings.get("store_name")) or "POS"
    tagline = clean_text(settings.get("tagline"))
    branch = clean_text(settings.get("branch"))
    address = clean_text(settings.get("address"))
    phone = clean_text(settings.get("phone"))

    logo_source = settings.get("logo") or ""
    if not str(logo_source).startswith("data:image/"):
        try:
            from app.services.live_customizations import _fallback_logo_data_url
            logo_source = _fallback_logo_data_url()
        except Exception:
            logo_source = ""

    # Keep the logo visibly on the right without letting its source canvas force
    # a tall centered header. The text gets the majority of the horizontal room.
    logo = pr._logo_image(logo_source, 30 * mm, 20 * mm)
    if logo:
        logo.hAlign = "CENTER"

    name_style = ParagraphStyle(
        "InvoiceStoreNameMarket", fontName=bold, fontSize=20.5, leading=24,
        alignment=TA_CENTER, textColor=colors.HexColor(pr._NAVY_DARK),
        spaceAfter=2.5,
    )
    tagline_style = ParagraphStyle(
        "InvoiceTaglineMarket", fontName=bold, fontSize=11.3, leading=16,
        alignment=TA_CENTER, textColor=colors.HexColor(pr._GOLD),
        spaceBefore=2, spaceAfter=2.5,
    )
    small_style = ParagraphStyle(
        "InvoiceStoreSmallMarket", fontName=regular, fontSize=9.2, leading=12.5,
        alignment=TA_CENTER, textColor=colors.HexColor(pr._NAVY_DARK),
        spaceBefore=1.5,
    )
    type_style = ParagraphStyle(
        "InvoiceTypeMarket", fontName=bold, fontSize=10.5, leading=13,
        alignment=TA_CENTER, textColor=colors.HexColor(pr._NAVY),
        spaceBefore=2,
    )
    field_style = ParagraphStyle(
        "InvoiceFieldMarket", fontName=regular, fontSize=10.7, leading=14,
        alignment=TA_RIGHT, textColor=colors.HexColor("#111827"),
    )
    field_bold = ParagraphStyle(
        "InvoiceFieldBoldMarket", fontName=bold, fontSize=10.7, leading=14,
        alignment=TA_RIGHT, textColor=colors.HexColor(pr._NAVY_DARK),
    )

    identity: list[Any] = [pr._p(store_name, name_style)]
    if tagline:
        identity.append(pr._p(tagline, tagline_style))
    location_line = " - ".join(x for x in (branch, address) if x)
    if location_line:
        identity.append(pr._p(location_line, small_style))
    if phone:
        identity.append(pr._p(f"هاتف المحل: {phone}", small_style))
    identity.append(pr._p(pr._invoice_type(invoice), type_style))

    if logo:
        brand = Table([[identity, logo]], colWidths=[content_w - 35 * mm, 35 * mm], rowHeights=[22 * mm])
        brand_style = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, 0), "CENTER"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]
    else:
        brand = Table([[identity]], colWidths=[content_w])
        brand_style = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]
    brand.setStyle(TableStyle(brand_style))

    inv_no = getattr(invoice, "invoice_number", None) or f"#{getattr(invoice, 'number', '-') or '-'}"
    raw_operation = getattr(invoice, "number", None)
    try:
        operation_no = f"{int(raw_operation):04d}"
    except Exception:
        operation_no = str(raw_operation or "-")
    customer_name = clean_text(getattr(invoice, "customer_name", None)) or "عميل نقدي"
    customer_phone = clean_text(getattr(invoice, "customer_phone", None))
    customer_address = ""
    if getattr(invoice, "type", "sale") == "sale":
        customer_address = clean_text(getattr(invoice, "notes", None))
    customer_id = getattr(invoice, "customer_id", None)

    def row(label: str, value: Any):
        return [pr._p(str(value), field_style), pr._p(label, field_bold)]

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
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ]))
        return table

    left = field_table(left_rows, [content_w * .27, content_w * .16])
    right = field_table(right_rows, [content_w * .38, content_w * .19])
    info = Table([[left, right]], colWidths=[content_w * .43, content_w * .57])
    info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [brand, Spacer(1, 1.5 * mm), info, Spacer(1, 2.3 * mm)]


def install_market_pdf_tuning() -> None:
    """Use A4 space efficiently while keeping thermal receipts naturally compact."""
    global _INSTALLED
    if _INSTALLED:
        return
    from reportlab.lib.units import mm
    from app.services import pdf_renderer as pr

    original_items_table = pr._items_table
    original_header = pr._header_block

    def header_market(invoice, settings, content_w, regular, bold):
        # Thermal is intentionally kept on the narrow v4 layout. A4 gets the
        # side-by-side brand treatment to reclaim vertical space.
        if content_w < 100 * mm:
            return original_header(invoice, settings, content_w, regular, bold)
        return _compact_a4_header(invoice, settings, content_w, regular, bold)

    def items_table_market(invoice, content_w, regular, bold, *, thermal: bool, items_per_page: int):
        effective_rows = int(items_per_page or 0)
        if not thermal:
            # The compact header frees enough A4 height for more symmetric blank
            # item rows without forcing the totals/signature onto a second page.
            effective_rows = max(21, effective_rows)
        return original_items_table(
            invoice,
            content_w,
            regular,
            bold,
            thermal=thermal,
            items_per_page=effective_rows,
        )

    pr._header_block = header_market
    pr._items_table = items_table_market
    pr._market_pdf_density_v6 = True
    _INSTALLED = True
