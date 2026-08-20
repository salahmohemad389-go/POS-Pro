from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.market_readiness import (
    _archive_customer,
    _archive_product,
    install_market_readiness,
)
from app.services.market_pdf_tuning import install_market_pdf_tuning
from app.services.owner_customizations_v4 import install_owner_customizations_v4

# Install before creating test databases so the dynamic archive columns are part
# of Base.metadata as they are in the real application startup.
install_market_readiness()
install_owner_customizations_v4()
install_market_pdf_tuning()

from app.db.session import Base
from app.db.models import Customer, CustomerLedger, Invoice, Product, Setting, StockMovement
from app.services.invoice_service import collect_payment, create_return_invoice, create_sale_invoice
from app.services.report_service import get_profit_report
from app.utils.helpers import r2


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_discount_vat_partial_collection_return_and_delete_reconcile_exactly():
    """Full accounting lifecycle must come back to the exact opening state."""
    db = _db()
    db.add(Setting(id=1, tax_rate=14, vat_enabled=True, currency="ج.م"))
    product = Product(name="P", barcode="B1", code="C1", price=12.35, cost=7.20, stock=20, min_stock=1, active=True)
    customer = Customer(name="C", phone="010", balance=0, active=True)
    db.add_all([product, customer])
    db.flush()

    created = create_sale_invoice(
        db,
        payload={
            "items": [{"product_id": product.id, "quantity": 3}],
            "customer_id": customer.id,
            "discount_pct": 10,
            "payment_method": "partial",
            "paid": 10,
        },
        user_id=1,
        user_name="Admin",
    )
    db.flush()
    sale = db.query(Invoice).filter(Invoice.id == created["id"]).one()

    # 3 * 12.35 = 37.05; 10% = 3.705 -> HALF_UP 3.71;
    # 33.34 * 14% = 4.6676 -> 4.67; final = 38.01.
    assert float(sale.subtotal) == pytest.approx(37.05)
    assert float(sale.discount) == pytest.approx(3.71)
    assert float(sale.tax) == pytest.approx(4.67)
    assert float(sale.total) == pytest.approx(38.01)
    assert float(sale.paid) == pytest.approx(10.00)
    assert float(sale.remaining) == pytest.approx(28.01)
    assert float(product.stock) == pytest.approx(17.0)
    assert float(customer.balance) == pytest.approx(28.01)

    collected = collect_payment(
        db,
        invoice_id=sale.id,
        amount=5,
        user_id=1,
        user_name="Admin",
    )
    db.flush()
    assert collected["remaining"] == pytest.approx(23.01)
    assert float(customer.balance) == pytest.approx(23.01)

    returned = create_return_invoice(
        db,
        customer_id=customer.id,
        original_invoice_id=sale.id,
        items=[{"product_id": product.id, "quantity": 1}],
        payment_method="credit",
        user_id=1,
        user_name="Admin",
    )
    db.flush()
    ret = db.query(Invoice).filter(Invoice.id == returned["id"]).one()
    assert float(ret.subtotal) == pytest.approx(12.35)
    assert float(ret.discount) == pytest.approx(1.24)
    assert float(ret.tax) == pytest.approx(1.56)
    assert float(ret.total) == pytest.approx(12.67)
    assert float(ret.remaining) == pytest.approx(12.67)
    assert float(product.stock) == pytest.approx(18.0)
    assert float(customer.balance) == pytest.approx(10.34)

    profit = get_profit_report(db)
    assert profit["total_revenue"] == pytest.approx(25.34)
    assert profit["total_cost"] == pytest.approx(14.40)
    assert profit["profit"] == pytest.approx(10.94)

    # The production route global is replaced by market_readiness. Deleting the
    # source sale must automatically reverse/delete its return, then reverse the
    # sale using the current remaining after collection.
    from app.api.routes import invoices as invoice_routes
    invoice_routes.delete_sale_invoice(db, invoice_id=sale.id)
    db.flush()

    assert db.query(Invoice).filter(Invoice.type.in_(["sale", "return"])).count() == 0
    assert float(product.stock) == pytest.approx(20.0)
    assert float(customer.balance) == pytest.approx(0.0)
    assert db.query(StockMovement).count() == 0
    assert db.query(CustomerLedger).count() == 0
    assert "INV-" in db.info.get("_pos_deleted_invoice_snapshot", "")


def test_product_and_customer_delete_is_archive_not_history_destruction():
    db = _db()
    product = Product(name="Historical product", barcode="622", code="SKU", price=20, cost=10, stock=4, active=True)
    customer = Customer(name="Historical customer", phone="010", balance=20, active=True)
    db.add_all([product, customer])
    db.flush()
    invoice = Invoice(
        number=1,
        invoice_number="INV-1",
        customer_id=customer.id,
        customer_name=customer.name,
        type="sale",
        items=[{"product_id": product.id, "product_name": product.name, "quantity": 1, "unit_price": 20, "total": 20}],
        subtotal=20,
        total=20,
        paid=0,
        remaining=20,
        status="unpaid",
        payment_method="credit",
    )
    db.add(invoice)
    db.flush()
    db.add(StockMovement(product_id=product.id, product_name=product.name, quantity=-1, movement_type="sale", invoice_id=invoice.id))
    db.add(CustomerLedger(customer_id=customer.id, customer_name=customer.name, invoice_id=invoice.id, movement_type="sale", debit=20, credit=0))
    db.flush()

    product_id = product.id
    customer_id = customer.id
    _archive_product(db, product)
    _archive_customer(db, customer)
    db.flush()

    archived_product = db.query(Product).filter(Product.id == product_id).one()
    archived_customer = db.query(Customer).filter(Customer.id == customer_id).one()
    assert archived_product.active is False
    assert archived_product.barcode is None
    assert archived_product.code is None
    assert archived_product.name.startswith("[محذوف #")
    assert archived_customer.active is False
    assert float(archived_customer.balance) == pytest.approx(20.0)
    assert db.query(Invoice).filter(Invoice.id == invoice.id).count() == 1
    assert db.query(StockMovement).filter(StockMovement.invoice_id == invoice.id).count() == 1
    assert db.query(CustomerLedger).filter(CustomerLedger.invoice_id == invoice.id).count() == 1


def test_market_ui_is_last_and_does_not_double_negate_returns():
    app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    market_js = (ROOT / "static" / "js" / "market_methods.js").read_text(encoding="utf-8")
    assert "...upgradeMethods,\n  ...marketMethods," in app_js
    assert "financial.reduce((sum, inv) => sum + (parseFloat(inv.total) || 0), 0)" in market_js
    assert "const sign = inv.type === 'return' ? -1 : 1" not in market_js
    assert "رقم التليفون على الفاتورة (اختياري)" not in market_js
    assert "العنوان على الفاتورة (اختياري)" not in market_js


def test_a4_uses_at_least_eighteen_item_boxes_and_thermal_stays_compact():
    from app.services import pdf_renderer as pr
    from reportlab.lib.units import mm

    invoice = SimpleNamespace(items=[{
        "product_id": 1,
        "product_name": "صنف",
        "code": "P1",
        "barcode": "B1",
        "quantity": 1,
        "unit": "قطعة",
        "unit_price": 10,
        "total": 10,
    }], _show_product_code_v4=True)

    a4 = pr._items_table(invoice, 180 * mm, "Helvetica", "Helvetica-Bold", thermal=False, items_per_page=15)
    thermal = pr._items_table(invoice, 70 * mm, "Helvetica", "Helvetica-Bold", thermal=True, items_per_page=15)
    assert a4._nrows >= 19  # header + at least 18 boxes
    assert thermal._nrows == 2  # header + actual item only
