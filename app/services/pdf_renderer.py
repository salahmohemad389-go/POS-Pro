"""Professional Arabic invoice PDF renderer for POS Pro.

The PDF is rendered from the persisted invoice snapshot plus store settings.
It never depends on a printer being connected and uses only bundled fonts/assets.
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
    log.warning("Arabic shaping unavailable: %s", exc)


def ar(text: Any) -> str:
    if text is None:
        return ""
    s = str(text)
    if not s or not _SHAPING_AVAILABLE:
        return s
    try:
        return "\n".join(get_display(arabic_reshaper.reshape(line)) for line in s.split("\n"))
    except Exception:
        return s


_ARABIC_FONT = "Amiri"
_ARABIC_FONT_BOLD = "Amiri-Bold"
_FALLBACK_FONT = "Helvetica"
_FALLBACK_FONT_BOLD = "Helvetica-Bold"


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
    if not logo_data_url or not str(logo_data_url).startswith("data:image") or "," not in str(logo_data_url):
        return None
    try:
        from reportlab.lib.utils import ImageReader
        from reportlab.platypus import Image
        raw = base64.b64decode(str(logo_data_url).split(",", 1)[1])
        bio = io.BytesIO(raw)
        iw, ih = ImageReader(bio).getSize()
        if not iw or not ih:
            return None
        scale = min(max_width / iw, max_height / ih)
        bio.seek(0)
        return Image(bio, width=iw * scale, height=ih * scale)
    except Exception as exc:
        log.warning("Could not embed logo: %s", exc)
        return None


def _money(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _display_amount(invoice: Any, value: Any) -> float:
    amount = _money(value)
    return -abs(amount) if getattr(invoice, "type", "") == "return" else amount


def generate_invoice_pdf(invoice: Any, settings: dict[str, Any], font_dir: Path, *, page_size: str = "a4", items_per_page: int = 17) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font, bold = _register_arabic_fonts(font_dir)
    thermal = page_size == "thermal"
    pagesize = (80 * mm, 297 * mm) if thermal else A4
    page_w, _ = pagesize
    margin = 5 * mm if thermal else 10 * mm
    content_w = page_w - 2 * margin
    navy = colors.HexColor("#163B63")
    pale = colors.HexColor("#EAF4FB")
    pale2 = colors.HexColor("#F8FBFD")
    gold = colors.HexColor("#C99A35")
    line = colors.HexColor("#163B63")
    text = colors.HexColor("#142033")

    buf = io.BytesIO()
    inv_no = getattr(invoice, "invoice_number", None) or f"#{getattr(invoice, 'number', '')}"
    doc = SimpleDocTemplate(buf, pagesize=pagesize, rightMargin=margin, leftMargin=margin, topMargin=7 * mm, bottomMargin=8 * mm, title=f"Invoice-{inv_no}", author=settings.get("store_name") or "POS")
    styles = getSampleStyleSheet()
    store_style = ParagraphStyle("store", parent=styles["Normal"], fontName=bold, fontSize=18 if not thermal else 12, leading=22 if not thermal else 15, alignment=TA_CENTER, textColor=navy)
    small_center = ParagraphStyle("small-center", parent=styles["Normal"], fontName=font, fontSize=8.5 if not thermal else 6.7, leading=11, alignment=TA_CENTER, textColor=text)
    meta_label = ParagraphStyle("meta-label", parent=styles["Normal"], fontName=bold, fontSize=9 if not thermal else 6.7, leading=11, alignment=TA_RIGHT, textColor=navy)
    meta_value = ParagraphStyle("meta-value", parent=styles["Normal"], fontName=font, fontSize=9 if not thermal else 6.7, leading=11, alignment=TA_RIGHT, textColor=text)
    footer_style = ParagraphStyle("footer", parent=styles["Normal"], fontName=font, fontSize=8, leading=11, alignment=TA_CENTER, textColor=text)
    story: list[Any] = []

    logo = _logo_image(settings.get("logo"), 48 * mm if not thermal else 28 * mm, 25 * mm if not thermal else 15 * mm)
    if logo:
        logo.hAlign = "CENTER"
        story.append(logo)
        story.append(Spacer(1, 2 * mm))
    store_name = (settings.get("store_name") or "").strip()
    if store_name:
        story.append(Paragraph(ar(store_name), store_style))
    secondary = [x.strip() for x in [settings.get("tagline") or "", settings.get("branch") or "", settings.get("address") or "", settings.get("phone") or ""] if x and str(x).strip()]
    if secondary:
        story.append(Paragraph(ar(" • ".join(secondary)), small_center))
    story.append(Spacer(1, 4 * mm if not thermal else 2 * mm))

    created = getattr(invoice, "created_at", None)
    created_text = created.strftime("%Y-%m-%d %H:%M") if created else "-"
    customer_name = getattr(invoice, "customer_name", None) or "عميل نقدي"
    customer_phone = getattr(invoice, "customer_phone", None) or "-"
    customer_id = getattr(invoice, "customer_id", None)
    customer_no = str(customer_id) if customer_id else "-"
    inv_type = getattr(invoice, "type", "sale")
    type_label = {"sale":"فاتورة بيع", "return":"مرتجع", "combined":"فاتورة مجمعة"}.get(inv_type, "فاتورة")

    if not thermal:
        meta = [
            [Paragraph(ar("اسم العميل:"), meta_label), Paragraph(ar(customer_name), meta_value), Paragraph(ar("التاريخ:"), meta_label), Paragraph(ar(created_text), meta_value)],
            [Paragraph(ar("رقم تليفون العميل:"), meta_label), Paragraph(ar(customer_phone), meta_value), Paragraph(ar("رقم الفاتورة:"), meta_label), Paragraph(ar(inv_no), meta_value)],
            [Paragraph(ar("رقم العميل:"), meta_label), Paragraph(ar(customer_no), meta_value), Paragraph(ar("نوع الفاتورة:"), meta_label), Paragraph(ar(type_label), meta_value)],
        ]
        mt = Table(meta, colWidths=[30*mm, 58*mm, 28*mm, content_w-116*mm], rowHeights=[9*mm]*3)
        mt.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ALIGN",(0,0),(-1,-1),"RIGHT"),("BOTTOMPADDING",(0,0),(-1,-1),2),("TOPPADDING",(0,0),(-1,-1),2),("LINEBELOW",(1,0),(1,-1),.45,colors.HexColor("#66788A")),("LINEBELOW",(3,0),(3,-1),.45,colors.HexColor("#66788A"))]))
        story.append(mt)
    else:
        rows = [("اسم العميل",customer_name),("الهاتف",customer_phone),("رقم العميل",customer_no),("التاريخ",created_text),("رقم الفاتورة",inv_no),("النوع",type_label)]
        mt = Table([[Paragraph(ar(k+":"), meta_label), Paragraph(ar(v), meta_value)] for k,v in rows], colWidths=[22*mm, content_w-22*mm])
        mt.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ALIGN",(0,0),(-1,-1),"RIGHT"),("BOTTOMPADDING",(0,0),(-1,-1),1),("TOPPADDING",(0,0),(-1,-1),1)]))
        story.append(mt)
    story.append(Spacer(1, 4 * mm if not thermal else 2 * mm))

    items = list(getattr(invoice, "items", None) or [])
    per_page = max(5, int(items_per_page or 17)) if not thermal else max(12, len(items) or 12)
    chunks = [items[i:i+per_page] for i in range(0, len(items), per_page)] or [[]]
    currency = settings.get("currency") or "ج.م"
    for page_index, chunk in enumerate(chunks):
        if thermal:
            headers = [ar("القيمة"), ar("السعر"), ar("ك"), ar("الصنف")]
            data = [headers]
            for it in chunk:
                data.append([f"{_money(it.get('total')):.2f}", f"{_money(it.get('unit_price')):.2f}", f"{_money(it.get('quantity')):g}", ar(it.get("product_name") or "-")])
            widths = [15*mm,15*mm,9*mm,content_w-39*mm]
        else:
            headers = [ar("القيمة"), ar("السعر"), ar("الوحدة"), ar("الكمية"), ar("اسم الصنف"), ar("كود الصنف"), ar("م")]
            data = [headers]
            start_no = page_index * per_page
            for idx, it in enumerate(chunk, start_no + 1):
                code = it.get("code") or it.get("barcode") or (str(it.get("product_id")) if it.get("product_id") else "")
                data.append([f"{_money(it.get('total')):.2f}", f"{_money(it.get('unit_price')):.2f}", ar(it.get("unit") or "قطعة"), f"{_money(it.get('quantity')):g}", ar(it.get("product_name") or "-"), ar(code), str(idx)])
            while len(data) < per_page + 1:
                data.append(["","","","","","",""])
            widths = [24*mm,22*mm,20*mm,20*mm,content_w-116*mm,25*mm,5*mm]
        row_heights = ([8*mm] + [7.5*mm]*(len(data)-1)) if not thermal else None
        table = Table(data, colWidths=widths, rowHeights=row_heights, repeatRows=1)
        style = [
            ("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),bold),
            ("FONTNAME",(0,1),(-1,-1),font),("FONTSIZE",(0,0),(-1,-1),9 if not thermal else 6.5),("ALIGN",(0,0),(-1,-1),"CENTER"),
            ("ALIGN",(4 if not thermal else 3,1),(4 if not thermal else 3,-1),"RIGHT"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("GRID",(0,0),(-1,-1),.65,line),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,pale]),("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2),
        ]
        table.setStyle(TableStyle(style))
        story.append(table)
        if page_index < len(chunks)-1:
            story.append(PageBreak())

    story.append(Spacer(1, 3 * mm))
    subtotal = _display_amount(invoice, getattr(invoice, "subtotal", 0))
    discount = abs(_money(getattr(invoice, "discount", 0)))
    paid = _display_amount(invoice, getattr(invoice, "paid", 0))
    remaining = _display_amount(invoice, getattr(invoice, "remaining", 0))
    total = _display_amount(invoice, getattr(invoice, "total", 0))
    tax = _display_amount(invoice, getattr(invoice, "tax", 0))
    tax_rate = _money(getattr(invoice, "tax_rate", 0))

    if not thermal:
        total_bar = Table([[Paragraph(ar("الإجمالي"), ParagraphStyle("tb", fontName=bold, fontSize=13, alignment=TA_RIGHT, textColor=navy)), Paragraph(f"{subtotal:.2f} {ar(currency)}", ParagraphStyle("tv", fontName=bold, fontSize=13, alignment=TA_CENTER, textColor=navy))]], colWidths=[content_w-45*mm,45*mm], rowHeights=[13*mm])
        total_bar.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),pale),("BOX",(0,0),(-1,-1),.8,line),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("RIGHTPADDING",(0,0),(0,0),8)]))
        story.append(total_bar)
        cells: list[tuple[str,float,bool]] = []
        if discount > .004: cells.append(("الخصم", -discount, False))
        if abs(tax) > .004: cells.append((f"الضريبة {tax_rate:g}%", tax, False))
        if abs(paid) > .004: cells.append(("المبلغ المدفوع", paid, False))
        if abs(remaining) > .004: cells.append(("المبلغ المتبقي", remaining, False))
        cells.append(("المبلغ النهائي", total, True))
        cell_w = content_w / len(cells)
        labels = [[ar(label) for label,_,_ in cells],[f"{value:.2f}" for _,value,_ in cells]]
        st = Table(labels, colWidths=[cell_w]*len(cells), rowHeights=[10*mm,13*mm])
        cmds=[("FONTNAME",(0,0),(-1,0),bold),("FONTNAME",(0,1),(-1,1),bold),("FONTSIZE",(0,0),(-1,0),9),("FONTSIZE",(0,1),(-1,1),12),("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("GRID",(0,0),(-1,-1),.65,line),("BACKGROUND",(0,0),(-1,-1),pale2)]
        for i,(_,_,final) in enumerate(cells):
            if final: cmds.extend([("BACKGROUND",(i,0),(i,-1),gold),("TEXTCOLOR",(i,0),(i,0),colors.white)])
        st.setStyle(TableStyle(cmds)); story.append(st)
        story.append(Spacer(1, 6*mm))
        sig = Table([[Paragraph(ar("توقيع المستلم:"), meta_label), "........................................................"]], colWidths=[35*mm,content_w-35*mm])
        sig.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"RIGHT"),("FONTNAME",(1,0),(1,0),font),("FONTSIZE",(1,0),(1,0),10)])); story.append(sig)
    else:
        summary = [("الإجمالي",subtotal)]
        if discount > .004: summary.append(("الخصم",-discount))
        if abs(tax) > .004: summary.append(("الضريبة",tax))
        if abs(paid) > .004: summary.append(("المدفوع",paid))
        if abs(remaining) > .004: summary.append(("المتبقي",remaining))
        summary.append(("النهائي",total))
        t=Table([[Paragraph(ar(k),meta_label),f"{v:.2f} {ar(currency)}"] for k,v in summary],colWidths=[content_w*.45,content_w*.55]); t.setStyle(TableStyle([("FONTNAME",(0,0),(-1,-1),font),("ALIGN",(0,0),(-1,-1),"RIGHT"),("LINEABOVE",(0,-1),(-1,-1),.8,navy)])); story.append(t)

    extra = settings.get("custom_lines") or ""
    if extra.strip():
        story.append(Spacer(1,3*mm))
        for line_text in extra.splitlines():
            if line_text.strip(): story.append(Paragraph(ar(line_text.strip()), footer_style))
    footer = settings.get("footer") or ""
    if footer.strip(): story.append(Spacer(1,3*mm)); story.append(Paragraph(ar(footer.strip()), footer_style))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
