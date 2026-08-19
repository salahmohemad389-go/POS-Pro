from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api.routes.settings import _validate_ui_payload
from app.services.pdf_renderer import generate_invoice_pdf
from app.services.setting_service import UI_DEFAULTS


def _invoice(**overrides):
    base = dict(
        id=11,
        number=42,
        invoice_number="INV-20260819-0042",
        customer_id=7,
        customer_name="عميل اختبار",
        customer_phone="01000000000",
        type="sale",
        items=[{
            "product_id": 3,
            "product_name": "منتج اختبار",
            "code": "P-003",
            "barcode": "6220003",
            "quantity": 2,
            "unit": "قطعة",
            "unit_price": 25,
            "total": 50,
        }],
        subtotal=50,
        discount_pct=0,
        discount=0,
        tax_rate=0,
        tax=0,
        total=50,
        paid=50,
        remaining=0,
        status="paid",
        payment_method="cash",
        user_name="Tester",
        created_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_dynamic_invoice_pdf_is_real_pdf():
    font_dir = ROOT / "static" / "assets" / "fonts"
    settings = {
        "store_name": "متجر الاختبار",
        "tagline": "",
        "branch": "الفرع الأول",
        "address": "عنوان الاختبار",
        "phone": "0123456789",
        "logo": "",
        "currency": "ج.م",
        "footer": "",
        "custom_lines": "",
    }
    pdf = generate_invoice_pdf(_invoice(), settings, font_dir, page_size="a4", items_per_page=12)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1500


def test_dynamic_invoice_pdf_handles_optional_total_boxes():
    font_dir = ROOT / "static" / "assets" / "fonts"
    settings = {"store_name": "POS", "logo": "", "currency": "ج.م"}
    paid_pdf = generate_invoice_pdf(_invoice(discount=0, discount_pct=0, remaining=0), settings, font_dir)
    due_pdf = generate_invoice_pdf(_invoice(discount=5, discount_pct=10, total=45, paid=20, remaining=25), settings, font_dir)
    assert paid_pdf.startswith(b"%PDF") and due_pdf.startswith(b"%PDF")
    assert len(paid_pdf) > 1500 and len(due_pdf) > 1500


def test_ui_defaults_cover_visibility_colors_and_shortcuts():
    assert UI_DEFAULTS["feature_invoices_enabled"] is True
    assert UI_DEFAULTS["feature_customers_enabled"] is True
    assert UI_DEFAULTS["quick_qty_enabled"] is True
    assert UI_DEFAULTS["primary_color"].startswith("#")
    assert UI_DEFAULTS["shortcut_return"]
    assert UI_DEFAULTS["shortcut_sidebar"]


def test_ui_settings_validation_normalizes_shortcuts_and_colors():
    clean = _validate_ui_payload({
        "feature_invoices_enabled": False,
        "feature_customers_enabled": True,
        "quick_qty_enabled": False,
        "primary_color": "#ABCDEF",
        "accent_color": "#123456",
        "shortcut_return": "ctrl+shift+r",
        "shortcut_cash": "F2",
    })
    assert clean["primary_color"] == "#abcdef"
    assert clean["shortcut_return"] == "Ctrl+Shift+R"
    assert clean["shortcut_cash"] == "F2"


def test_ui_settings_validation_rejects_unknown_and_bad_values():
    with pytest.raises(HTTPException):
        _validate_ui_payload({"primary_color": "blue"})
    with pytest.raises(HTTPException):
        _validate_ui_payload({"feature_invoices_enabled": "yes"})
    with pytest.raises(HTTPException):
        _validate_ui_payload({"not_a_real_setting": True})
