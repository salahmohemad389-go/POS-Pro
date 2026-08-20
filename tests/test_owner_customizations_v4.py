from pathlib import Path
from types import SimpleNamespace

from app.services.owner_customizations_v4 import install_owner_customizations_v4
from app.services import setting_service
from app.services.pdf_service import generate_invoice_pdf


def _invoice(phone="", address=""):
    return SimpleNamespace(
        id=1,
        number=7,
        invoice_number="INV-0007",
        customer_id=None,
        customer_name="عميل اختبار",
        customer_phone=phone,
        type="sale",
        notes=address,
        items=[{
            "product_id": 1,
            "product_name": "صنف تجريبي طويل للاختبار",
            "code": "P-001",
            "barcode": "6220001",
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
        user_name="Admin",
        created_at=None,
    )


def _settings(show_code=True):
    return {
        "store_name": "الصالح",
        "tagline": "",
        "branch": "",
        "address": "",
        "phone": "",
        "currency": "ج.م",
        "logo": "",
        "custom_lines": "",
        "footer": "",
        "invoice_show_product_code": show_code,
    }


def test_owner_setting_default_is_available():
    install_owner_customizations_v4()
    assert setting_service.UI_DEFAULTS["invoice_show_product_code"] is True
    assert "invoice_show_product_code" in setting_service.UI_SETTINGS_KEYS


def test_a4_invoice_renders_with_optional_meta_and_code_toggle():
    install_owner_customizations_v4()
    with_code = generate_invoice_pdf(_invoice("01000000000", "الإسماعيلية"), _settings(True), page_size="a4")
    without_code = generate_invoice_pdf(_invoice(), _settings(False), page_size="a4")
    assert with_code.startswith(b"%PDF")
    assert without_code.startswith(b"%PDF")
    assert len(with_code) > 1500
    assert len(without_code) > 1500


def test_thermal_invoice_uses_same_layout_system():
    install_owner_customizations_v4()
    pdf = generate_invoice_pdf(_invoice("01000000000", "الإسماعيلية"), _settings(False), page_size="thermal")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1200
