"""SQLAlchemy models for POS Pro.

All database table definitions live here. Models import Base from
app.db.session — this is the single place that defines the schema.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def Money():
    """Column factory: Numeric(12,2) for exact money storage."""
    return Column(Numeric(12, 2), default=0)


# ═══════════════════════════════════════════════════
# Models
# ═══════════════════════════════════════════════════


class AppCounter(Base):
    """Atomic application counters (invoice sequence, etc.)."""
    __tablename__ = "app_counters"
    name = Column(String(80), primary_key=True)
    value = Column(Integer, nullable=False, default=0)


class RateLimitBucket(Base):
    """Persistent rate-limit bucket used by multi-instance PostgreSQL deployments."""
    __tablename__ = "rate_limit_buckets"
    key = Column(String(255), primary_key=True)
    attempts = Column(JSON, nullable=False, default=list)
    locked_until = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    login = Column(String(80), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="cashier")
    active = Column(Boolean, default=True)
    token_version = Column(Integer, default=0, nullable=False)
    permissions = Column(JSON, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    is_owner = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_utcnow)


class Setting(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    store_name = Column(String(200))
    branch = Column(String(200))
    phone = Column(String(80))
    address = Column(String(300))
    currency = Column(String(20), default="ج.م")
    tax_rate = Column(Numeric(5, 2), default=0)
    vat_enabled = Column(Boolean, default=False)
    footer = Column(String(300), default="شكراً لزيارتكم")
    copies = Column(Integer, default=1)
    logo = Column(Text)
    header_position = Column(String(20), default="top")
    quick_qty = Column(String(200), default="1,5,10,20,30,50,100")
    printer_type = Column(String(20), default="browser")
    auto_print_after_sale = Column(Boolean, default=False)
    theme = Column(String(20), default="light")
    cached_at = Column(DateTime, default=_utcnow)
    tagline = Column(String(200), default="")
    slogan = Column(String(200), default="")
    custom_lines = Column(Text, default="")
    invoice_format = Column(String(20), default="a4")
    max_items_per_page = Column(Integer, default=15)
    header_note = Column(String(200), default="")
    terms_conditions = Column(Text, default="")
    warranty_text = Column(String(300), default="")
    feature_reports_enabled = Column(Boolean, default=True, nullable=False)
    feature_suppliers_enabled = Column(Boolean, default=True, nullable=False)


class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, index=True)
    phone = Column(String(40), index=True)
    email = Column(String(120))
    address = Column(Text)
    notes = Column(Text)
    balance = Money()
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, index=True)
    parent_id = Column(
        Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=True
    )
    children = relationship("Category", backref="parent", remote_side=[id])


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, autoincrement=True)
    barcode = Column(String(80), index=True)
    code = Column(String(80), index=True)
    name = Column(String(300), nullable=False, index=True)
    category_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supplier_id = Column(
        Integer,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    unit = Column(String(40), default="قطعة")
    cost = Money()
    price = Money()
    stock = Column(Numeric(12, 3), default=0)
    min_stock = Column(Numeric(12, 3), default=5)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    created_at = Column(DateTime, default=_utcnow)


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, index=True)
    phone = Column(String(40), index=True)
    notes = Column(Text)
    balance = Money()
    created_at = Column(DateTime, default=_utcnow)


class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, autoincrement=True)
    number = Column(Integer, nullable=False, unique=True, index=True)
    invoice_number = Column(String(50), unique=True, index=True)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_name = Column(String(200))
    customer_phone = Column(String(40))
    type = Column(String(20), default="sale")
    items = Column(JSON, nullable=False)
    subtotal = Money()
    discount_pct = Column(Numeric(5, 2), default=0)
    discount = Money()
    tax_rate = Column(Numeric(5, 2), default=0)
    tax = Money()
    total = Money()
    paid = Money()
    remaining = Money()
    status = Column(String(20), default="paid")
    payment_method = Column(String(20), default="cash")
    user_id = Column(Integer, ForeignKey("users.id"))
    user_name = Column(String(120))
    notes = Column(Text)
    created_at = Column(DateTime, default=_utcnow, index=True)
    original_invoice_id = Column(
        Integer,
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_number = Column(String(50), index=True)
    combined_source_ids = Column(JSON, nullable=True)
    combined_options = Column(JSON, nullable=True)


class StockMovement(Base):
    __tablename__ = "stock_movements"
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_name = Column(String(300))
    quantity = Column(Numeric(12, 3), nullable=False)
    unit_cost = Column(Numeric(12, 2), default=0)
    movement_type = Column(String(20), nullable=False, index=True)
    invoice_id = Column(
        Integer,
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_number = Column(String(50), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_name = Column(String(120))
    notes = Column(String(300))
    created_at = Column(DateTime, default=_utcnow, index=True)


class CustomerLedger(Base):
    __tablename__ = "customer_ledger"
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_name = Column(String(200))
    invoice_id = Column(
        Integer,
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_number = Column(String(50), index=True)
    movement_type = Column(String(20), nullable=False, index=True)
    description = Column(String(300))
    debit = Column(Numeric(12, 2), default=0)
    credit = Column(Numeric(12, 2), default=0)
    balance_after = Column(Numeric(12, 2), default=0)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_name = Column(String(120))
    created_at = Column(DateTime, default=_utcnow, index=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True)
    user_name = Column(String(120), index=True)
    action = Column(String(80), index=True)
    details = Column(Text)
    ip = Column(String(64))
    created_at = Column(DateTime, default=_utcnow, index=True)


# ═══════════════════════════════════════════════════
# Composite indexes
# ═══════════════════════════════════════════════════
Index("idx_products_search", Product.barcode, Product.name, Product.code)
Index("idx_products_cat_price", Product.category_id, Product.price)
Index("idx_invoices_date_type", Invoice.created_at, Invoice.type)
Index("idx_invoices_customer_date", Invoice.customer_id, Invoice.created_at)
Index("idx_audit_date_action", AuditLog.created_at, AuditLog.action)


# ═══════════════════════════════════════════════════
# Model serialization (to_dict methods)
# ═══════════════════════════════════════════════════
from app.utils.helpers import money_n, r3  # noqa: E402


def _product_to_dict(self):
    return {
        "id": self.id,
        "barcode": self.barcode or "",
        "code": self.code or "",
        "name": self.name,
        "category_id": self.category_id,
        "supplier_id": self.supplier_id,
        "unit": self.unit or "قطعة",
        "cost": money_n(self.cost),
        "price": money_n(self.price),
        "stock": r3(self.stock),
        "min_stock": r3(self.min_stock),
    }


def _category_to_dict(self):
    return {"id": self.id, "name": self.name, "parent_id": self.parent_id}


def _supplier_to_dict(self):
    return {
        "id": self.id,
        "name": self.name,
        "phone": self.phone or "",
        "email": self.email or "",
        "address": self.address or "",
        "notes": self.notes or "",
        "balance": money_n(self.balance),
        "active": self.active,
    }


def _customer_to_dict(self):
    return {
        "id": self.id,
        "name": self.name,
        "phone": self.phone or "",
        "notes": self.notes or "",
        "balance": money_n(self.balance),
    }


def _invoice_to_dict(self):
    sign = -1 if self.type == "return" else 1
    base_total = money_n(self.total)
    base_paid = money_n(self.paid)
    base_remaining = money_n(self.remaining)
    return {
        "id": self.id,
        "number": self.number,
        "invoice_number": self.invoice_number or f"#{self.number}",
        "customer_id": self.customer_id,
        "customer_name": self.customer_name or "",
        "customer_phone": self.customer_phone or "",
        "type": self.type,
        "items": self.items or [],
        "subtotal": money_n(self.subtotal) * sign,
        "discount_pct": money_n(self.discount_pct),
        "discount": money_n(self.discount) * sign,
        "tax_rate": money_n(self.tax_rate),
        "tax": money_n(self.tax) * sign,
        "total": base_total * sign,
        "paid": base_paid * sign,
        "remaining": base_remaining * sign,
        "absolute_total": base_total,
        "status": self.status,
        "payment_method": self.payment_method,
        "user_id": self.user_id,
        "user_name": self.user_name,
        "notes": self.notes or "",
        "original_invoice_id": self.original_invoice_id,
        "parent_number": self.parent_number,
        "created_at": self.created_at.isoformat() if self.created_at else None,
        "is_combined": self.type == "combined",
        "combined_source_ids": self.combined_source_ids or [],
        "combined_options": self.combined_options or {},
    }


Product.to_dict = _product_to_dict
Category.to_dict = _category_to_dict
Supplier.to_dict = _supplier_to_dict
Customer.to_dict = _customer_to_dict
Invoice.to_dict = _invoice_to_dict
