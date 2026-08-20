from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import Base
from app.db.models import AuditLog, Customer, CustomerLedger, Invoice, Product, StockMovement, User
from app.services.live_customizations import (
    _AUDIT_SNAPSHOT_KEY,
    _audit_with_deleted_snapshot,
    _safe_delete_invoice,
    install_live_customizations,
)
from app.services.pdf_renderer import generate_invoice_pdf


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_sale_delete_reverses_stock_debt_and_keeps_audit_snapshot():
    db = _db()
    product = Product(name="P", stock=10, price=50, cost=20)
    customer = Customer(name="C", balance=50)
    db.add_all([product, customer]); db.flush()
    inv = Invoice(
        number=1, invoice_number="INV-1", customer_id=customer.id,
        customer_name="C", customer_phone="010", type="sale",
        items=[{"product_id": product.id, "product_name": "P", "quantity": 2, "unit_price": 50, "total": 100}],
        subtotal=100, total=100, paid=50, remaining=50, status="partial", payment_method="partial",
    )
    db.add(inv); db.flush()
    db.add(StockMovement(product_id=product.id, product_name="P", quantity=-2, movement_type="sale", invoice_id=inv.id, invoice_number=inv.invoice_number))
    db.add(CustomerLedger(customer_id=customer.id, customer_name="C", invoice_id=inv.id, invoice_number=inv.invoice_number, movement_type="sale", debit=100, credit=0))
    db.commit()

    _safe_delete_invoice(db, invoice_id=inv.id)
    db.flush()

    assert db.query(Invoice).count() == 0
    assert float(db.query(Product).first().stock) == pytest.approx(12)
    assert float(db.query(Customer).first().balance) == pytest.approx(0)
    assert db.query(StockMovement).count() == 0
    assert db.query(CustomerLedger).count() == 0
    assert "INV-1" in db.info[_AUDIT_SNAPSHOT_KEY]


def test_deleted_invoice_snapshot_is_written_to_admin_audit_log():
    db = _db()
    product = Product(name="P", stock=5, price=10, cost=4)
    admin = User(name="Admin", login="admin-v3", password_hash="x", role="admin", is_owner=True)
    db.add_all([product, admin]); db.flush()
    inv = Invoice(
        number=9, invoice_number="INV-0009", customer_name="Cash", type="sale",
        items=[{"product_id": product.id, "product_name": "P", "quantity": 1, "unit_price": 10, "total": 10}],
        subtotal=10, total=10, paid=10, remaining=0, status="paid", payment_method="cash",
    )
    db.add(inv); db.commit()

    _safe_delete_invoice(db, invoice_id=inv.id)
    _audit_with_deleted_snapshot(db, admin, "invoice_delete", "حذف فاتورة #9", "127.0.0.1", commit=False)
    db.commit()

    row = db.query(AuditLog).filter(AuditLog.action == "invoice_delete").one()
    assert "INV-0009" in row.details
    assert "نسخة الفاتورة المحذوفة=" in row.details
    assert row.user_id == admin.id


def test_sale_with_linked_return_must_delete_return_first():
    db = _db()
    product = Product(name="P", stock=10, price=50, cost=20)
    customer = Customer(name="C", balance=0)
    db.add_all([product, customer]); db.flush()
    sale = Invoice(number=1, invoice_number="INV-1", customer_id=customer.id, customer_name="C", type="sale", items=[], total=0, paid=0, remaining=0)
    db.add(sale); db.flush()
    ret = Invoice(number=2, invoice_number="INV-2", customer_id=customer.id, customer_name="C", type="return", items=[], total=0, paid=0, remaining=0, original_invoice_id=sale.id)
    db.add(ret); db.commit()

    with pytest.raises(ValueError, match="المرتجعات المرتبطة"):
        _safe_delete_invoice(db, invoice_id=sale.id)


def test_return_delete_reverses_stock_and_account_credit():
    db = _db()
    product = Product(name="P", stock=10, price=50, cost=20)
    customer = Customer(name="C", balance=30)
    db.add_all([product, customer]); db.flush()
    inv = Invoice(
        number=2, invoice_number="INV-2", customer_id=customer.id,
        customer_name="C", type="return",
        items=[{"product_id": product.id, "product_name": "P", "quantity": 2, "unit_price": 25, "total": 50}],
        subtotal=50, total=50, paid=30, remaining=20, status="partial", payment_method="partial",
    )
    db.add(inv); db.flush()
    db.add(StockMovement(product_id=product.id, product_name="P", quantity=2, movement_type="return", invoice_id=inv.id, invoice_number=inv.invoice_number))
    db.add(CustomerLedger(customer_id=customer.id, customer_name="C", invoice_id=inv.id, invoice_number=inv.invoice_number, movement_type="return", debit=0, credit=50))
    db.commit()

    _safe_delete_invoice(db, invoice_id=inv.id)
    db.flush()

    assert db.query(Invoice).count() == 0
    assert float(db.query(Product).first().stock) == pytest.approx(8)
    assert float(db.query(Customer).first().balance) == pytest.approx(50)


def test_invoice_pdf_clean_header_override_still_renders():
    install_live_customizations()
    invoice = SimpleNamespace(
        id=1, number=7, invoice_number="INV-0007", customer_id=3,
        customer_name="عميل", customer_phone="01000000000", type="sale",
        items=[{"product_id": 1, "product_name": "منتج", "barcode": "1", "quantity": 1, "unit": "قطعة", "unit_price": 10, "total": 10}],
        subtotal=10, discount_pct=0, discount=0, tax_rate=0, tax=0,
        total=10, paid=10, remaining=0, status="paid", payment_method="cash",
        user_name="Admin", created_at=None,
    )
    settings = {"store_name": "POS", "logo": "", "currency": "ج.م"}
    pdf = generate_invoice_pdf(invoice, settings, ROOT / "static" / "assets" / "fonts")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1500
