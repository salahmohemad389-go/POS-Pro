"""PDF generation for POS Pro v2.5.0 - Arabic + RTL support via ReportLab.

Uses the bundled Amiri font (free, OFL licensed) for Arabic glyphs.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("pospro.pdf")


# ═══════════════════════════════════════════════════
# Arabic text shaping (fixes disconnected/reversed letters)
# ═══════════════════════════════════════════════════
# ReportLab does NOT perform Arabic contextual letter-shaping or bidi
# reordering on its own. Any string that may contain Arabic characters
# MUST be passed through `ar(...)` below before being handed to a
# Paragraph or Table cell, otherwise letters render disconnected (each
# in its isolated form) and/or in the wrong visual order.
try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    _SHAPING_AVAILABLE = True
except Exception as exc:  # pragma: no cover - only if deps missing
    arabic_reshaper = None  # type: ignore
    get_display = None  # type: ignore
    _SHAPING_AVAILABLE = False
    log.warning("arabic_reshaper/python-bidi not available: %s", exc)


def ar(text: Any) -> str:
    """Reshape + bidi-reorder a string for correct Arabic rendering in ReportLab.

    Safe to call on any value (numbers, None, mixed Arabic/Latin/digits) -
    non-Arabic text passes through unchanged. Use this for every piece of
    text (labels, names, footer, etc.) that ends up in a Paragraph or
    Table cell anywhere in this module or in services.py.
    """
    if text is None:
        return ""
    s = str(text)
    if not s or not _SHAPING_AVAILABLE:
        return s
    try:
        if "\n" in s:
            return "\n".join(ar(line) for line in s.split("\n"))
        reshaped = arabic_reshaper.reshape(s)
        return get_display(reshaped)
    except Exception:
        return s


# ═══════════════════════════════════════════════════
# Font helpers
# ═══════════════════════════════════════════════════
_ARABIC_FONT = "Amiri"
_ARABIC_FONT_BOLD = "Amiri-Bold"
_FALLBACK_FONT = "Helvetica"
_FALLBACK_FONT_BOLD = "Helvetica-Bold"


def _register_arabic_fonts(font_dir: Path) -> tuple[str, str]:
    """Register Arabic-supporting fonts with ReportLab.

    Returns (normal_font, bold_font). Falls back to Helvetica if Amiri is
    not available.
    """
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        regular = font_dir / "Amiri-Regular.ttf"
        bold = font_dir / "Amiri-Bold.ttf"
        if regular.exists():
            pdfmetrics.registerFont(TTFont(_ARABIC_FONT, str(regular)))
        else:
            log.warning("Amiri-Regular.ttf not found at %s", regular)
            return _FALLBACK_FONT, _FALLBACK_FONT_BOLD
        if bold.exists():
            pdfmetrics.registerFont(TTFont(_ARABIC_FONT_BOLD, str(bold)))
            pdfmetrics.registerFontFamily(
                _ARABIC_FONT, normal=_ARABIC_FONT, bold=_ARABIC_FONT_BOLD
            )
            return _ARABIC_FONT, _ARABIC_FONT_BOLD
        log.warning("Amiri-Bold.ttf not found at %s", bold)
        return _ARABIC_FONT, _ARABIC_FONT
    except Exception as exc:
        log.warning("Could not register Arabic fonts: %s", exc)
        return _FALLBACK_FONT, _FALLBACK_FONT_BOLD


def _logo_image(logo_data_url: Optional[str], max_width: float = 40 * 6):
    """Decode a data: URL logo and return a ReportLab Image, or None."""
    if not logo_data_url or not logo_data_url.startswith("data:image"):
        return None
    try:
        from reportlab.platypus import Image

        # data:image/png;base64,XXXX
        if "," not in logo_data_url:
            return None
        b64 = logo_data_url.split(",", 1)[1]
        img_bytes = base64.b64decode(b64)
        buf = io.BytesIO(img_bytes)
        img = Image(buf, width=max_width, height=max_width)
        return img
    except Exception as exc:
        log.warning("Could not embed logo: %s", exc)
        return None


# ═══════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════
def generate_invoice_pdf(
    invoice: Any,
    settings: dict[str, Any],
    font_dir: Path,
    *,
    page_size: str = "a4",
    items_per_page: int = 17,
) -> bytes:
    """Render an invoice to PDF bytes using ReportLab.

    Args:
        invoice: An Invoice ORM instance (must have `.items`, `.number`,
                 `.total`, `.subtotal`, etc.).
        settings: Settings dict (store_name, tagline, slogan, footer, ...).
        font_dir: Directory containing Amiri-Regular.ttf / Amiri-Bold.ttf.
        page_size: "a4" (default) or "thermal" (80mm roll).
        items_per_page: Number of item rows per page (default 17 for A4).

    Returns:
        Raw PDF bytes.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    arabic_font, arabic_font_bold = _register_arabic_fonts(font_dir)

    if page_size == "thermal":
        # 80mm thermal roll (~3.15 in × variable)
        page_w = 80 * mm
        page_h = 297 * mm  # long page; reportlab will paginate as needed
        pagesize = (page_w, page_h)
    else:
        pagesize = A4
        page_w, page_h = A4

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=pagesize,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=f"Invoice-{invoice.invoice_number or invoice.number}",
        author=settings.get("store_name", "POS Pro"),
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Heading1"],
        fontName=arabic_font_bold,
        fontSize=18,
        alignment=TA_CENTER,
        spaceAfter=4,
        textColor=colors.HexColor("#8B0000"),
        leading=22,
    )
    sub_style = ParagraphStyle(
        "SubStyle",
        parent=styles["Normal"],
        fontName=arabic_font,
        fontSize=10,
        alignment=TA_CENTER,
        spaceAfter=2,
        textColor=colors.HexColor("#B45309"),
        leading=14,
    )
    normal_style = ParagraphStyle(
        "NormalStyle",
        parent=styles["Normal"],
        fontName=arabic_font,
        fontSize=10,
        alignment=TA_RIGHT,
        spaceAfter=2,
        leading=13,
    )
    small_style = ParagraphStyle(
        "SmallStyle",
        parent=styles["Normal"],
        fontName=arabic_font,
        fontSize=8,
        alignment=TA_RIGHT,
        spaceAfter=1,
        leading=10,
        textColor=colors.HexColor("#555555"),
    )
    footer_style = ParagraphStyle(
        "FooterStyle",
        parent=styles["Normal"],
        fontName=arabic_font,
        fontSize=11,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1e3a5f"),
        leading=14,
    )

    story: list[Any] = []

    # ── Header ────────────────────────────────────────────────────────────
    logo_img = _logo_image(settings.get("logo"))
    if logo_img:
        # Logo centered above the title
        story.append(logo_img)
        story.append(Spacer(1, 3 * mm))
    if settings.get("store_name"):
        story.append(Paragraph(ar(settings["store_name"]), title_style))
    if settings.get("tagline"):
        story.append(Paragraph(ar(settings["tagline"]), sub_style))
    if settings.get("slogan"):
        story.append(Paragraph(ar(settings["slogan"]), sub_style))
    if settings.get("branch") and settings["branch"] != settings.get("slogan"):
        story.append(Paragraph(ar(settings["branch"]), small_style))
    story.append(Spacer(1, 4 * mm))

    # ── Invoice meta ──────────────────────────────────────────────────────
    inv_type_ar = {"sale": "فاتورة بيع", "return": "فاتورة مرتجع", "combined": "فاتورة مجمعة"}.get(invoice.type, "فاتورة")
    payment_ar = {"cash": "نقدي", "credit": "آجل", "partial": "جزئي", "mixed": "مختلط"}.get(
        invoice.payment_method, invoice.payment_method or ""
    )
    status_ar = {"paid": "مدفوعة", "unpaid": "آجل", "partial": "جزئي"}.get(
        invoice.status, invoice.status or ""
    )
    created = (
        invoice.created_at.strftime("%Y-%m-%d %H:%M") if invoice.created_at else "-"
    )
    inv_no = invoice.invoice_number or f"#{invoice.number}"

    meta_data = [
        [ar("رقم الفاتورة:"), ar(inv_no)],
        [ar("التاريخ:"), ar(created)],
        [ar("النوع:"), ar(inv_type_ar)],
        [ar("طريقة الدفع:"), ar(payment_ar or "-")],
        [ar("الحالة:"), ar(status_ar or "-")],
        [ar("الكاشير:"), ar(invoice.user_name or "-")],
        [ar("العميل:"), ar(invoice.customer_name or "عميل نقدي")],
        [ar("الموبايل:"), ar(invoice.customer_phone or "-")],
    ]
    if getattr(invoice, "type", None) == "combined" and getattr(invoice, "notes", None):
        meta_data.append([ar("مصدر التجميع:"), ar(invoice.notes)])
    meta_table = Table(meta_data, colWidths=[42 * mm, page_w - 24 * mm - 42 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), arabic_font),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555555")),
                ("FONTNAME", (1, 0), (1, -1), arabic_font_bold),
                ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#8B0000")),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 4 * mm))

    # ── Items table (auto page-break: items_per_page per page) ─────────────
    items = invoice.items or []
    currency = settings.get("currency", "ج.م")
    # Build pages of items
    pages_items: list[list[Any]] = []
    for i in range(0, max(1, len(items)), items_per_page):
        pages_items.append(items[i : i + items_per_page])

    for page_idx, page_items in enumerate(pages_items):
        items_data = [
            [ar("م"), ar("الصنف"), ar("الكمية"), ar("الوحدة"), ar("السعر"), ar("القيمة")]
        ]
        for i, it in enumerate(page_items, 1):
            items_data.append(
                [
                    str(i),
                    ar(it.get("product_name", "-")),
                    f"{float(it.get('quantity', 0)):g}",
                    ar(it.get("unit", "قطعة")),
                    f"{float(it.get('unit_price', 0)):.2f}",
                    f"{float(it.get('total', 0)):.2f}",
                ]
            )
        # Pad to items_per_page rows for clean invoice form look
        for i in range(len(page_items) + 1, items_per_page + 1):
            items_data.append(["", "", "", "", "", ""])

        col_w = page_w - 24 * mm
        items_table = Table(
            items_data,
            colWidths=[
                10 * mm,  # م
                col_w * 0.38,  # الصنف
                18 * mm,  # الكمية
                18 * mm,  # الوحدة
                20 * mm,  # السعر
                20 * mm,  # القيمة
            ],
            repeatRows=1,
        )
        row_heights = [9 * mm] + [8 * mm] * items_per_page
        items_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), arabic_font_bold),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("FONTNAME", (0, 1), (-1, -1), arabic_font),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c8ddef")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, len(page_items)),
                        [colors.HexColor("#EFF6FF"), colors.HexColor("#DBEAFE")],
                    ),
                    (
                        "BACKGROUND",
                        (0, len(page_items) + 1),
                        (-1, -1),
                        colors.HexColor("#F8FAFC"),
                    ),
                    (
                        "TEXTCOLOR",
                        (0, len(page_items) + 1),
                        (-1, -1),
                        colors.HexColor("#9ca3af"),
                    ),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("ROWHEIGHTS", (0, 0), (-1, -1), 7 * mm),
                ]
            )
        )
        # Override row heights explicitly

        items_table._rowHeights = row_heights
        story.append(items_table)

        # Only on the last page, append totals + footer
        is_last = page_idx == len(pages_items) - 1
        if is_last:
            story.append(Spacer(1, 4 * mm))
            story.extend(
                _build_totals_table(
                    invoice, arabic_font, arabic_font_bold, currency, page_w
                )
            )
            story.append(Spacer(1, 4 * mm))
            custom_lines = settings.get("custom_lines") or ""
            if custom_lines.strip():
                for line in custom_lines.split("\n"):
                    if line.strip():
                        story.append(Paragraph(ar(line.strip()), normal_style))
            if settings.get("footer"):
                story.append(Spacer(1, 4 * mm))
                story.append(Paragraph(ar(settings["footer"]), footer_style))
        else:
            # Page break
            from reportlab.platypus import PageBreak

            story.append(PageBreak())

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def _build_totals_table(
    invoice, arabic_font: str, arabic_font_bold: str, currency: str, page_w: float
):
    """Build the totals table (used by generate_invoice_pdf)."""
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Table, TableStyle

    discount_pct = float(invoice.discount_pct or 0)
    discount_amt = float(invoice.discount or 0)
    paid_amt = float(invoice.paid or 0)
    remaining_amt = float(invoice.remaining or 0)
    subtotal_amt = float(invoice.subtotal or 0)
    total_amt = float(invoice.total or 0)
    tax_rate = float(getattr(invoice, "tax_rate", 0) or 0)
    tax_amt = float(getattr(invoice, "tax", 0) or 0)

    # Return invoices show as negative amounts, matching the combined
    # invoice's totals (sales positive, returns negative).
    is_return = getattr(invoice, "type", None) == "return"
    if is_return:
        subtotal_amt = -abs(subtotal_amt)
        total_amt = -abs(total_amt)

    col_w = page_w - 24 * mm
    first_row = [
        ar(f"الخصم\n{discount_pct:g}%"),
        ar(f"المبلغ المخصوم\n{discount_amt:.2f}"),
    ]
    if tax_rate > 0 or abs(tax_amt) > 0.0001:
        first_row.append(ar(f"الضريبة {tax_rate:g}%\n{tax_amt:.2f}"))
    first_row.extend([
        ar(f"المبلغ المدفوع\n{paid_amt:.2f}"),
        ar(f"الباقي\n{remaining_amt:.2f}"),
    ])
    ncols = len(first_row)
    each = col_w / float(ncols)
    second_row = [""] * ncols
    second_row[0] = ar(f"الإجمالي\n{subtotal_amt:.2f} {currency}")
    second_row[-2 if ncols > 1 else 0] = ar(f"المبلغ النهائي\n{total_amt:.2f} {currency}")
    totals_data = [first_row, second_row]
    totals_table = Table(
        totals_data,
        colWidths=[each] * ncols,
        rowHeights=[18 * mm, 20 * mm],
    )
    totals_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), arabic_font),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("FONTSIZE", (0, 1), (-1, 1), 11),
                ("FONTNAME", (0, 1), (-1, 1), arabic_font_bold),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DBEAFE")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#BFDBFE")),
                ("BACKGROUND", (2, 1), (2, 1), colors.HexColor("#FCD34D")),
                ("BACKGROUND", (3, 1), (3, 1), colors.HexColor("#FCD34D")),
                ("SPAN", (0, 1), (1, 1)),
                ("SPAN", (2, 1), (3, 1)),
                ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#1e3a5f")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return [totals_table]
