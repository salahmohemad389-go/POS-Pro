"""Printable Arabic invoice renderer.

The renderer is data-driven: branding comes from settings and invoice/customer
fields come from the persisted invoice. A4 output follows the clean paper
invoice layout requested for POS Pro while thermal output remains supported.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("pospro.pdf")

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _SHAPING_AVAILABLE = True
except Exception as exc:
    arabic_reshaper = None
    get_display = None
    _SHAPING_AVAILABLE = False
    log.warning("arabic_reshaper/python-bidi not available: %s", exc)


def ar(text: Any) -> str:
    if text is None:
        return ""
    value = str(text)
    if not value or not _SHAPING_AVAILABLE:
        return value
    try:
        if "\n" in value:
            return "\n".join(ar(line) for line in value.split("\n"))
        return get_display(arabic_reshaper.reshape(value))
    except Exception:
        return value


_ARABIC_FONT = "Amiri"
_ARABIC_FONT_BOLD = "Amiri-Bold"
_FALLBACK_FONT = "Helvetica"
_FALLBACK_FONT_BOLD = "Helvetica-Bold"
_NAVY = "#173B60"
_NAVY_DARK = "#102F4D"
_PALE = "#EAF4FB"
_PALE_2 = "#F8FBFE"
_GOLD = "#D7AE4B"
_BORDER = "#214664"
_MUTED = "#5B6774"


def _register_arabic_fonts(font_dir: Path) -> tuple[str, str]:
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        regular = font_dir / "Amiri-Regular.ttf"
        bold = font_dir / "Amiri-Bold.ttf"
        if not regular.exists():
            return _FALLBACK_FONT, _FALLBACK_FONT_BOLD
        pdfmetrics.registerFont(TTFont(_ARABIC_FONT, str(regular)))
        if bold.exists():
            pdfmetrics.registerFont(TTFont(_ARABIC_FONT_BOLD, str(bold)))
            pdfmetrics.registerFontFamily(_ARABIC_FONT, normal=_ARABIC_FONT, bold=_ARABIC_FONT_BOLD)
            return _ARABIC_FONT, _ARABIC_FONT_BOLD
        return _ARABIC_FONT, _ARABIC_FONT
    except Exception as exc:
        log.warning("Could not register Arabic fonts: %s", exc)
        return _FALLBACK_FONT, _FALLBACK_FONT_BOLD


def _logo_image(logo_data_url: Optional[str], max_width: float, max_height: float):
    if not logo_data_url or not str(logo_data_url).startswith("data:image") or "," not in logo_data_url:
        return None
    try:
        from reportlab.lib.utils import ImageReader
        from reportlab.platypus import Image
        raw = base64.b64decode(str(logo_data_url).split(",", 1)[1], validate=True)
        buf = io.BytesIO(raw)
        reader = ImageReader(buf)
        width, height = reader.getSize()
        if not width or not height:
            return None
        scale = min(max_width / float(width), max_height / float(height))
        buf.seek(0)
        return Image(buf, width=max(1, width * scale), height=max(1, height * scale))
    except Exception as exc:
        log.warning("Could not embed logo: %s", exc)
        return None


def _money(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def _qty(value: Any) -> str:
    try:
        number = float(value or 0)
        return f"{number:g}"
    except Exception:
        return "0"


def _p(text: Any, style):
    from reportlab.platypus import Paragraph
    return Paragraph(ar(text), style)


def _invoice_type(invoice: Any) -> str:
    return {
        "sale": "فاتورة بيع",
        "return": "فاتورة مرتجع",
        "combined": "فاتورة مجمعة",
    }.get(getattr(invoice, "type", "sale"), "فاتورة")


def _created_text(invoice: Any) -> str:
    created = getattr(invoice, "created_at", None)
    if not created:
        return "-"
    try:
        return created.strftime("%Y-%m-%d  %H:%M")
    except Exception:
        return str(created)


def _header_block(invoice: Any, settings: dict[str, Any], page_w: float, content_w: float, regular: str, bold: str):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Spacer, Table, TableStyle

    store_name = (settings.get("store_name") or "POS").strip()
    tagline = (settings.get("tagline") or "").strip()
    branch = (settings.get("branch") or "").strip()
    address = (settings.get("address") or "").strip()
    phone = (settings.get("phone") or "").strip()
    logo = _logo_image(settings.get("logo"), 34 * mm, 27 * mm)

    name_style = ParagraphStyle("InvoiceStoreName", fontName=bold, fontSize=22, leading=27, alignment=TA_CENTER, textColor=colors.HexColor(_NAVY_DARK))
    tagline_style = ParagraphStyle("InvoiceTagline", fontName=bold, fontSize=12, leading=16, alignment=TA_CENTER, textColor=colors.HexColor(_GOLD))
    small_center = ParagraphStyle("InvoiceSmallCenter", fontName=regular, fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.HexColor(_NAVY_DARK))
    type_style = ParagraphStyle("InvoiceType", fontName=bold, fontSize=10, leading=13, alignment=TA_CENTER, textColor=colors.HexColor(_NAVY))
    field_style = ParagraphStyle("InvoiceField", fontName=regular, fontSize=10, leading=14, alignment=TA_RIGHT, textColor=colors.HexColor("#111827"))
    field_bold = ParagraphStyle("InvoiceFieldBold", fontName=bold, fontSize=10, leading=14, alignment=TA_RIGHT, textColor=colors.HexColor(_NAVY_DARK))

    title_flow = [_p(store_name, name_style)]
    if tagline:
        title_flow.append(_p(tagline, tagline_style))
    address_line = "، ".join(x for x in (branch, address) if x)
    if address_line:
        title_flow.append(_p(address_line, small_center))
    if phone:
        title_flow.append(_p(f"هاتف: {phone}", small_center))
    title_flow.append(Spacer(1, 1 * mm))
    title_flow.append(_p(_invoice_type(invoice), type_style))

    if logo:
        brand = Table([[title_flow, logo]], colWidths=[content_w - 40 * mm, 40 * mm])
        brand.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
    else:
        brand = Table([[title_flow]], colWidths=[content_w])
        brand.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))

    inv_no = getattr(invoice, "invoice_number", None) or f"#{getattr(invoice, 'number', '-') or '-'}"
    customer_id = getattr(invoice, "customer_id", None)
    customer_no = str(customer_id) if customer_id else "-"
    customer_name = getattr(invoice, "customer_name", None) or "عميل نقدي"
    customer_phone = getattr(invoice, "customer_phone", None) or "-"

    left_fields = Table([
        [_p(_created_text(invoice), field_style), _p("التاريخ:", field_bold)],
        [_p(inv_no, field_style), _p("رقم الفاتورة:", field_bold)],
    ], colWidths=[content_w * .26, content_w * .16])
    right_fields = Table([
        [_p(customer_name, field_style), _p("اسم العميل:", field_bold)],
        [_p(customer_phone, field_style), _p("رقم تليفون العميل:", field_bold)],
        [_p(customer_no, field_style), _p("رقم العميل:", field_bold)],
    ], colWidths=[content_w * .36, content_w * .22])
    for tbl in (left_fields, right_fields):
        tbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (0, -1), .45, colors.HexColor("#6B7280")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
    info = Table([[left_fields, right_fields]], colWidths=[content_w * .42, content_w * .58])
    info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [brand, Spacer(1, 5 * mm), info, Spacer(1, 5 * mm)]


def _items_table(invoice: Any, content_w: float, regular: str, bold: str, *, thermal: bool, items_per_page: int):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Table, TableStyle

    items = list(getattr(invoice, "items", None) or [])
    if thermal:
        headers = [ar("القيمة"), ar("السعر"), ar("الكمية"), ar("الصنف"), ar("م")]
        data = [headers]
        for idx, item in enumerate(items, 1):
            data.append([
                f"{_money(item.get('total')):.2f}",
                f"{_money(item.get('unit_price')):.2f}",
                _qty(item.get("quantity")),
                ar(item.get("product_name") or "-"),
                str(idx),
            ])
        widths = [content_w * .21, content_w * .20, content_w * .14, content_w * .37, content_w * .08]
    else:
        headers = [ar("القيمة"), ar("السعر"), ar("الوحدة"), ar("الكمية"), ar("اسم الصنف"), ar("كود الصنف"), ar("م")]
        data = [headers]
        for idx, item in enumerate(items, 1):
            code = item.get("code") or item.get("barcode") or "-"
            data.append([
                f"{_money(item.get('total')):.2f}",
                f"{_money(item.get('unit_price')):.2f}",
                ar(item.get("unit") or "قطعة"),
                _qty(item.get("quantity")),
                ar(item.get("product_name") or "-"),
                ar(code),
                str(idx),
            ])
        target_rows = max(len(items), max(8, items_per_page))
        while len(data) - 1 < target_rows:
            data.append(["", "", "", "", "", "", ""])
        widths = [content_w * .13, content_w * .13, content_w * .12, content_w * .12, content_w * .28, content_w * .17, content_w * .05]

    row_heights = [9 * mm] + ([7.5 * mm] * (len(data) - 1) if not thermal else [7 * mm] * (len(data) - 1))
    table = Table(data, colWidths=widths, rowHeights=row_heights, repeatRows=1)
    body_end = max(1, min(len(items), len(data) - 1))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_NAVY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), bold),
        ("FONTSIZE", (0, 0), (-1, 0), 9.5 if not thermal else 8),
        ("FONTNAME", (0, 1), (-1, -1), regular),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5 if not thermal else 7.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (4 if not thermal else 3, 1), (4 if not thermal else 3, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), .7, colors.HexColor(_BORDER)),
        ("ROWBACKGROUNDS", (0, 1), (-1, body_end), [colors.white, colors.HexColor(_PALE)]),
        ("BACKGROUND", (0, body_end + 1), (-1, -1), colors.HexColor(_PALE_2)),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def _totals(invoice: Any, currency: str, content_w: float, regular: str, bold: str, *, thermal: bool):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Spacer, Table, TableStyle

    subtotal = _money(getattr(invoice, "subtotal", 0))
    discount = _money(getattr(invoice, "discount", 0))
    discount_pct = _money(getattr(invoice, "discount_pct", 0))
    tax = _money(getattr(invoice, "tax", 0))
    tax_rate = _money(getattr(invoice, "tax_rate", 0))
    paid = _money(getattr(invoice, "paid", 0))
    remaining = _money(getattr(invoice, "remaining", 0))
    total = _money(getattr(invoice, "total", 0))
    is_return = getattr(invoice, "type", None) == "return"
    sign = -1 if is_return else 1

    label = ParagraphStyle("TotalLabel", fontName=bold, fontSize=10 if not thermal else 8, leading=13, alignment=TA_CENTER, textColor=colors.HexColor(_NAVY_DARK))
    value = ParagraphStyle("TotalValue", fontName=bold, fontSize=13 if not thermal else 10, leading=16, alignment=TA_CENTER, textColor=colors.HexColor("#111827"))
    total_label = ParagraphStyle("GrandLabel", fontName=bold, fontSize=13 if not thermal else 9, leading=16, alignment=TA_RIGHT, textColor=colors.HexColor(_NAVY_DARK))
    total_value = ParagraphStyle("GrandValue", fontName=bold, fontSize=15 if not thermal else 11, leading=18, alignment=TA_CENTER, textColor=colors.HexColor(_NAVY_DARK))

    grand = Table([[_p(f"{sign * subtotal:.2f} {currency}", total_value), _p("الإجمالي", total_label)]], colWidths=[content_w * .28, content_w * .72], rowHeights=[12 * mm if not thermal else 9 * mm])
    grand.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_PALE)),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(_BORDER)),
        ("INNERGRID", (0, 0), (-1, -1), .7, colors.HexColor(_BORDER)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))

    cells: list[tuple[str, float, bool]] = [("المبلغ النهائي", sign * total, True)]
    if remaining > .004:
        cells.append(("المبلغ المتبقي", sign * remaining, False))
    paid_label = "المبلغ المُعاد نقداً" if is_return else "المبلغ المدفوع"
    cells.append((paid_label, sign * paid, False))
    if discount > .004 or discount_pct > .004:
        suffix = f" ({discount_pct:g}%)" if discount_pct else ""
        cells.append((f"الخصم{suffix}", sign * discount, False))
    if tax > .004 or tax_rate > .004:
        suffix = f" ({tax_rate:g}%)" if tax_rate else ""
        cells.append((f"الضريبة{suffix}", sign * tax, False))

    row = []
    for cell_label, amount, highlighted in cells:
        inner = Table([[_p(cell_label, label)], [_p(f"{amount:.2f}", value)]], colWidths=[1])
        inner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_GOLD if highlighted else _PALE_2)),
            ("BOX", (0, 0), (-1, -1), .8, colors.HexColor(_BORDER)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        row.append(inner)
    summary = Table([row], colWidths=[content_w / len(row)] * len(row))
    summary.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [grand, summary]


def generate_invoice_pdf(invoice: Any, settings: dict[str, Any], font_dir: Path, *, page_size: str = "a4", items_per_page: int = 17) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    regular, bold = _register_arabic_fonts(font_dir)
    thermal = str(page_size or "a4").lower() == "thermal"
    pagesize = (80 * mm, 297 * mm) if thermal else A4
    page_w, _page_h = pagesize
    margin = 5 * mm if thermal else 10 * mm
    content_w = page_w - (2 * margin)

    buf = io.BytesIO()
    inv_no = getattr(invoice, "invoice_number", None) or getattr(invoice, "number", "") or "invoice"
    doc = SimpleDocTemplate(
        buf,
        pagesize=pagesize,
        rightMargin=margin,
        leftMargin=margin,
        topMargin=7 * mm if thermal else 9 * mm,
        bottomMargin=8 * mm,
        title=f"Invoice-{inv_no}",
        author=(settings.get("store_name") or "POS"),
    )

    story: list[Any] = []
    story.extend(_header_block(invoice, settings, page_w, content_w, regular, bold))
    story.append(_items_table(invoice, content_w, regular, bold, thermal=thermal, items_per_page=items_per_page))
    story.append(Spacer(1, 3 * mm))
    story.extend(_totals(invoice, settings.get("currency") or "ج.م", content_w, regular, bold, thermal=thermal))

    note_style = ParagraphStyle("InvoiceNote", fontName=regular, fontSize=8.5 if not thermal else 7.5, leading=12, alignment=TA_RIGHT, textColor=colors.HexColor(_MUTED))
    footer_style = ParagraphStyle("InvoiceFooter", fontName=regular, fontSize=9 if not thermal else 7.5, leading=12, alignment=TA_CENTER, textColor=colors.HexColor(_NAVY))
    custom_lines = (settings.get("custom_lines") or "").strip()
    if custom_lines:
        story.append(Spacer(1, 3 * mm))
        for line in custom_lines.splitlines():
            if line.strip():
                story.append(Paragraph(ar(line.strip()), note_style))
    footer = (settings.get("footer") or "").strip()
    if footer:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(ar(footer), footer_style))
    if not thermal:
        story.append(Spacer(1, 6 * mm))
        signature = ParagraphStyle("InvoiceSignature", fontName=bold, fontSize=10, leading=14, alignment=TA_RIGHT, textColor=colors.HexColor(_NAVY_DARK))
        story.append(Paragraph(ar("توقيع المستلم:  ................................................"), signature))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
