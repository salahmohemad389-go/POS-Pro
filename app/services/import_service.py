"""Import/Export service for POS Pro.

Public import/export service used by API routes.
Parsing and file-writing helpers live in app.services.import_export_engine.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

log = logging.getLogger("pospro.services.import_export")

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_ROWS = 10_000


def import_products(db: Session, raw: bytes, filename: str) -> dict[str, Any]:
    """Import products from a file."""
    from app.services.import_export_engine import import_products as _import
    return _import(db, raw, filename)


def import_customers(db: Session, raw: bytes, filename: str) -> dict[str, Any]:
    """Import customers from a file."""
    from app.services.import_export_engine import import_customers as _import
    return _import(db, raw, filename)


def export_products(db: Session, format: str = "xlsx") -> dict[str, Any]:
    """Export all products to headers + rows."""
    from app.db.models import Product, Category, Supplier
    from app.utils.helpers import money_n, r3

    cat_map = {c.id: c.name for c in db.query(Category).all()}
    sup_map = {s.id: s.name for s in db.query(Supplier).all()}
    headers = ["الباركود", "الكود", "الاسم", "القسم", "المورد", "الوحدة", "التكلفة", "السعر", "المخزون", "الحد الأدنى"]
    rows = [
        [
            p.barcode or "",
            p.code or "",
            p.name,
            cat_map.get(p.category_id, ""),
            sup_map.get(p.supplier_id, ""),
            p.unit or "",
            money_n(p.cost),
            money_n(p.price),
            r3(p.stock),
            r3(p.min_stock),
        ]
        for p in db.query(Product).order_by(Product.name).all()
    ]
    return {"headers": headers, "rows": rows, "count": len(rows)}


def export_customers(db: Session) -> dict[str, Any]:
    """Export all customers to headers + rows."""
    from app.db.models import Customer
    from app.utils.helpers import money_n, r3

    headers = ["الاسم", "الهاتف", "الملاحظات", "الرصيد"]
    rows = [
        [c.name or "", c.phone or "", c.notes or "", money_n(c.balance)]
        for c in db.query(Customer).order_by(Customer.name).all()
    ]
    return {"headers": headers, "rows": rows, "count": len(rows)}


def export_suppliers(db: Session) -> dict[str, Any]:
    """Export all suppliers to headers + rows."""
    from app.db.models import Supplier
    from app.utils.helpers import money_n, r3

    headers = ["الاسم", "الهاتف", "البريد", "العنوان", "الملاحظات", "المستحق"]
    rows = [
        [
            s.name or "",
            s.phone or "",
            s.email or "",
            s.address or "",
            s.notes or "",
            money_n(s.balance),
        ]
        for s in db.query(Supplier).order_by(Supplier.name).all()
    ]
    return {"headers": headers, "rows": rows, "count": len(rows)}


def write_csv(headers: list[str], rows: list[list[Any]], name: str) -> Path:
    from app.services.import_export_engine import export_csv
    return export_csv(headers, rows, name)


def write_xlsx(headers: list[str], rows: list[list[Any]], name: str) -> Path:
    from app.services.import_export_engine import export_xlsx
    return export_xlsx(headers, rows, name)
