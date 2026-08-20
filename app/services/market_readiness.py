"""Pre-market accounting and deletion safeguards for POS Pro.

The UI may say "delete", but products/customers that participate in financial
history are archived instead of being physically removed.  This preserves
invoice snapshots, future returns, stock history and customer ledger integrity.
Financial invoices are genuinely deleted only after their live accounting
impact is reversed transactionally and an audit snapshot is retained.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import Boolean, Column, case, func, or_, true
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.core.permissions import has_permission
from app.db.models import Customer, CustomerLedger, Invoice, Product, StockMovement, User
from app.db.session import get_db
from app.schemas.requests import CustomerSave, ProductFind, ProductSave
from app.services.audit_service import log_audit
from app.utils.helpers import money_n, r2, r3

_INSTALLED = False


def _install_archive_columns() -> None:
    """Add mapped archive flags and migrate old databases without a manual step."""
    # SQLAlchemy declarative models support adding mapped columns after class
    # declaration. This keeps the schema change isolated from the stable models.
    if not hasattr(Product, "active"):
        Product.active = Column(Boolean, default=True, nullable=False, server_default=true())
    if not hasattr(Customer, "active"):
        Customer.active = Column(Boolean, default=True, nullable=False, server_default=true())

    from app.db import bootstrap

    if getattr(bootstrap, "_market_archive_migration_v5", False):
        return
    original = bootstrap._auto_migrate

    def auto_migrate_with_archive():
        original()
        dialect = bootstrap.engine.dialect.name
        default_true = "1" if dialect == "sqlite" else "TRUE"
        migrations: list[str] = []
        if bootstrap._table_exists("products") and not bootstrap._table_has_column("products", "active"):
            migrations.append(f"ALTER TABLE products ADD COLUMN active BOOLEAN DEFAULT {default_true} NOT NULL")
        if bootstrap._table_exists("customers") and not bootstrap._table_has_column("customers", "active"):
            migrations.append(f"ALTER TABLE customers ADD COLUMN active BOOLEAN DEFAULT {default_true} NOT NULL")
        if migrations:
            with bootstrap.engine.begin() as conn:
                for sql in migrations:
                    conn.exec_driver_sql(sql)
        # Defensive normalization for databases upgraded from unusual legacy
        # schemas where a nullable boolean may have existed.
        with bootstrap.engine.begin() as conn:
            if bootstrap._table_exists("products"):
                conn.exec_driver_sql(f"UPDATE products SET active = {default_true} WHERE active IS NULL")
            if bootstrap._table_exists("customers"):
                conn.exec_driver_sql(f"UPDATE customers SET active = {default_true} WHERE active IS NULL")

    bootstrap._auto_migrate = auto_migrate_with_archive
    bootstrap._market_archive_migration_v5 = True


def _replace_router_endpoint(router, path: str, method: str, endpoint) -> None:
    """Replace an APIRouter handler before main includes the router."""
    method = method.upper()
    for route in router.routes:
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", set()) or set()):
            route.endpoint = endpoint
            if getattr(route, "dependant", None) is not None:
                route.dependant.call = endpoint
            return
    raise RuntimeError(f"Route not found for market patch: {method} {path}")


def _active_product_query(db: Session):
    return db.query(Product).filter(Product.active.is_(True))


def _active_customer_query(db: Session):
    return db.query(Customer).filter(Customer.active.is_(True))


def _archive_product(db: Session, product: Product) -> dict[str, Any]:
    """Hide a product while preserving its ID for historical returns."""
    old_name = (product.name or "").strip() or f"منتج #{product.id}"
    old_barcode = (product.barcode or "").strip()
    old_code = (product.code or "").strip()
    product.active = False
    # Release unique identifiers so a replacement SKU may legitimately reuse
    # the same barcode/code. Historical invoices keep their own snapshots.
    product.barcode = None
    product.code = None
    if not old_name.startswith("[محذوف #"):
        product.name = f"[محذوف #{product.id}] {old_name}"[:300]
    return {
        "name": old_name,
        "barcode": old_barcode,
        "code": old_code,
        "stock": r3(product.stock),
    }


def _archive_customer(db: Session, customer: Customer) -> dict[str, Any]:
    """Hide a customer while retaining invoices, ledger and any outstanding debt."""
    old_name = (customer.name or "").strip() or f"عميل #{customer.id}"
    customer.active = False
    return {"name": old_name, "balance": money_n(customer.balance)}


def _install_product_routes() -> None:
    from app.api.routes import products as routes

    original_save = routes.save_product

    async def list_products_market(
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=500),
        q: Optional[str] = None,
        category_id: Optional[int] = None,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if not has_permission(user, "product_view"):
            raise HTTPException(403, "لا تملك صلاحية عرض المنتجات")
        query = _active_product_query(db)
        if category_id:
            query = query.filter(Product.category_id == category_id)
        search_rank = None
        if q:
            raw = q.strip()[:200]
            like = f"%{raw}%"
            starts = f"{raw}%"
            query = query.filter(or_(Product.name.ilike(like), Product.barcode.ilike(like), Product.code.ilike(like)))
            search_rank = case(
                (or_(Product.barcode == raw, Product.code == raw), 0),
                (Product.name.ilike(raw), 1),
                (Product.name.ilike(starts), 2),
                else_=3,
            )
        total = query.count()
        query = query.order_by(search_rank, Product.name, Product.id) if search_rank is not None else query.order_by(Product.name, Product.id)
        items = query.offset((page - 1) * limit).limit(limit).all()
        return {"total": total, "page": page, "limit": limit, "items": [p.to_dict() for p in items]}

    async def product_by_barcode_market(
        barcode: str,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if not has_permission(user, "product_view"):
            raise HTTPException(403, "لا تملك صلاحية عرض المنتجات")
        raw = "".join(ch for ch in str(barcode or "").strip() if ord(ch) >= 32 or ch == "\t").strip()
        if not raw:
            return None
        p = _active_product_query(db).filter(or_(Product.barcode == raw, Product.code == raw)).first()
        if not p:
            p = _active_product_query(db).filter(or_(func.trim(Product.barcode) == raw, func.trim(Product.code) == raw)).first()
        return p.to_dict() if p else None

    async def product_find_market(
        payload: ProductFind,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if not has_permission(user, "product_view"):
            raise HTTPException(403, "لا تملك صلاحية عرض المنتجات")
        raw = "".join(ch for ch in payload.q.strip() if ord(ch) >= 32 or ch == "\t").strip()
        if not raw:
            return {"matches": [], "exact": None}
        base = _active_product_query(db)
        exact = base.filter(or_(Product.barcode == raw, Product.code == raw)).first()
        if not exact:
            exact = _active_product_query(db).filter(or_(func.trim(Product.barcode) == raw, func.trim(Product.code) == raw)).first()
        if exact:
            data = exact.to_dict()
            return {"matches": [data], "exact": data}
        if raw.isdigit():
            p = _active_product_query(db).filter(Product.id == int(raw)).first()
            if p:
                data = p.to_dict()
                return {"matches": [data], "exact": data}
        like = f"%{raw}%"
        matches = _active_product_query(db).filter(or_(Product.barcode.ilike(like), Product.code.ilike(like), Product.name.ilike(like))).limit(10).all()
        return {"matches": [p.to_dict() for p in matches], "exact": None}

    async def save_product_market(
        payload: ProductSave,
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        pid = payload.id
        if pid and not _active_product_query(db).filter(Product.id == int(pid)).first():
            raise HTTPException(404, "المنتج محذوف أو غير موجود")
        return await original_save(payload, request, user, db)

    async def get_product_market(
        pid: int,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if not has_permission(user, "product_view"):
            raise HTTPException(403, "لا تملك صلاحية عرض المنتجات")
        product = _active_product_query(db).filter(Product.id == pid).first()
        if not product:
            raise HTTPException(404, "منتج غير موجود")
        return product.to_dict()

    async def delete_product_market(
        pid: int,
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        routes._rate_limit_or_403(f"product_delete:{user.id}", "delete")
        if not has_permission(user, "product_delete"):
            raise HTTPException(403, "لا تملك صلاحية")
        product = _active_product_query(db).filter(Product.id == pid).with_for_update().first()
        if not product:
            raise HTTPException(404, "منتج غير موجود")
        history_count = db.query(StockMovement).filter(StockMovement.product_id == pid).count()
        snap = _archive_product(db, product)
        try:
            log_audit(
                db, user, "product_delete",
                f"حذف/أرشفة منتج: {snap['name']} | كود={snap['code'] or '-'} | باركود={snap['barcode'] or '-'} | الحركات المحفوظة={history_count}",
                request.client.host if request else None, commit=False,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(500, "تعذر حذف المنتج بأمان")
        return {"ok": True, "archived": True, "history_preserved": history_count > 0}

    def export_products_active(db: Session, format: str = "xlsx") -> dict[str, Any]:
        from app.db.models import Category, Supplier
        cat_map = {c.id: c.name for c in db.query(Category).all()}
        sup_map = {s.id: s.name for s in db.query(Supplier).all()}
        headers = ["الباركود", "الكود", "الاسم", "القسم", "المورد", "الوحدة", "التكلفة", "السعر", "المخزون", "الحد الأدنى"]
        rows = [[
            p.barcode or "", p.code or "", p.name, cat_map.get(p.category_id, ""),
            sup_map.get(p.supplier_id, ""), p.unit or "", money_n(p.cost), money_n(p.price),
            r3(p.stock), r3(p.min_stock),
        ] for p in _active_product_query(db).order_by(Product.name).all()]
        return {"headers": headers, "rows": rows, "count": len(rows)}

    routes.export_products = export_products_active
    _replace_router_endpoint(routes.router, "/api/products", "GET", list_products_market)
    _replace_router_endpoint(routes.router, "/api/products/by-barcode/{barcode}", "GET", product_by_barcode_market)
    _replace_router_endpoint(routes.router, "/api/products/find", "POST", product_find_market)
    _replace_router_endpoint(routes.router, "/api/products", "POST", save_product_market)
    _replace_router_endpoint(routes.router, "/api/products/{pid}", "GET", get_product_market)
    _replace_router_endpoint(routes.router, "/api/products/{pid}", "DELETE", delete_product_market)


def _install_customer_routes() -> None:
    from app.api.routes import customers as routes

    original_save = routes.save_customer

    async def list_customers_market(
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=500),
        q: Optional[str] = None,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if not has_permission(user, "customer_view"):
            raise HTTPException(403, "لا تملك صلاحية عرض العملاء")
        query = _active_customer_query(db)
        if q:
            like = f"%{q.strip()}%"
            query = query.filter(or_(Customer.name.ilike(like), Customer.phone.ilike(like)))
        total = query.count()
        items = query.order_by(Customer.name, Customer.id).offset((page - 1) * limit).limit(limit).all()
        return {"total": total, "page": page, "limit": limit, "items": [c.to_dict() for c in items]}

    async def save_customer_market(
        payload: CustomerSave,
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        cid = payload.id
        if cid and not _active_customer_query(db).filter(Customer.id == int(cid)).first():
            raise HTTPException(404, "العميل محذوف أو غير موجود")
        return await original_save(payload, request, user, db)

    async def get_customer_market(
        cid: int,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if not has_permission(user, "customer_view"):
            raise HTTPException(403, "لا تملك صلاحية")
        customer = _active_customer_query(db).filter(Customer.id == cid).first()
        if not customer:
            raise HTTPException(404, "عميل غير موجود")
        return customer.to_dict()

    async def delete_customer_market(
        cid: int,
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        routes._rate_limit_or_403(f"customer_delete:{user.id}", "delete")
        if not has_permission(user, "customer_delete"):
            raise HTTPException(403, "لا تملك صلاحية")
        customer = _active_customer_query(db).filter(Customer.id == cid).with_for_update().first()
        if not customer:
            raise HTTPException(404, "عميل غير موجود")
        invoice_count = db.query(Invoice).filter(Invoice.customer_id == cid).count()
        ledger_count = db.query(CustomerLedger).filter(CustomerLedger.customer_id == cid).count()
        snap = _archive_customer(db, customer)
        try:
            log_audit(
                db, user, "customer_delete",
                f"حذف/أرشفة عميل: {snap['name']} | الرصيد المحفوظ={snap['balance']:.2f} | الفواتير={invoice_count} | حركات الحساب={ledger_count}",
                request.client.host if request else None, commit=False,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(500, "تعذر حذف العميل بأمان")
        return {
            "ok": True, "archived": True,
            "financial_history_preserved": bool(invoice_count or ledger_count or abs(snap["balance"]) > .0001),
        }

    def export_customers_active(db: Session) -> dict[str, Any]:
        headers = ["الاسم", "الهاتف", "الملاحظات", "الرصيد"]
        rows = [[c.name or "", c.phone or "", c.notes or "", money_n(c.balance)] for c in _active_customer_query(db).order_by(Customer.name).all()]
        return {"headers": headers, "rows": rows, "count": len(rows)}

    routes.export_customers = export_customers_active
    _replace_router_endpoint(routes.router, "/api/customers", "GET", list_customers_market)
    _replace_router_endpoint(routes.router, "/api/customers", "POST", save_customer_market)
    _replace_router_endpoint(routes.router, "/api/customers/{cid:int}", "GET", get_customer_market)
    _replace_router_endpoint(routes.router, "/api/customers/{cid}", "DELETE", delete_customer_market)


def _ensure_invoice_product(db: Session, item: dict[str, Any]) -> Product:
    """Return the historical product row, recreating an archived tombstone if needed."""
    pid = int(item.get("product_id") or 0)
    if pid <= 0:
        raise ValueError("عنصر فاتورة بدون رقم منتج صالح")
    product = db.query(Product).filter(Product.id == pid).with_for_update().first()
    if product:
        return product
    product = Product(
        id=pid,
        name=f"[محذوف #{pid}] {(item.get('product_name') or 'منتج تاريخي')}"[:300],
        barcode=None,
        code=None,
        unit=item.get("unit") or "قطعة",
        cost=r2(item.get("cost") or 0),
        price=r2(item.get("unit_price") or 0),
        stock=0,
        min_stock=0,
        active=False,
    )
    db.add(product)
    db.flush()
    return product


def _install_invoice_accounting_guards() -> None:
    from app.api.routes import invoices as routes
    from app.services.live_customizations import _AUDIT_SNAPSHOT_KEY, _invoice_snapshot

    original_create = routes.create_sale_invoice

    def create_sale_active_only(db: Session, *, payload: dict, user_id: int, user_name: str):
        for raw in payload.get("items") or []:
            try:
                pid = int((raw or {}).get("product_id") or 0)
            except (TypeError, ValueError):
                continue
            if pid > 0 and not _active_product_query(db).filter(Product.id == pid).first():
                raise ValueError(f"المنتج رقم {pid} محذوف وغير متاح للبيع")
        cid = payload.get("customer_id")
        if cid:
            try:
                customer_id = int(cid)
            except (TypeError, ValueError):
                raise ValueError("رقم العميل غير صالح")
            if not _active_customer_query(db).filter(Customer.id == customer_id).first():
                raise ValueError("العميل محذوف؛ اختر عميلاً نشطاً للفاتورة الجديدة")
        return original_create(db, payload=payload, user_id=user_id, user_name=user_name)

    def reverse_delete_invoice(db: Session, *, invoice_id: int) -> None:
        """Delete any invoice and exactly reverse its live stock/debt effect.

        Linked returns are reversed automatically before their source sale. A
        return deletion is allowed to make an archived/current stock negative;
        that is mathematically correct when those returned units were sold again.
        """
        invoice = db.query(Invoice).filter(Invoice.id == int(invoice_id)).with_for_update().first()
        if not invoice:
            raise ValueError("فاتورة غير موجودة")

        snapshots: list[str] = []
        removed_ids: set[int] = set()

        def remove_one(inv: Invoice) -> None:
            snapshots.append(_invoice_snapshot(inv))
            removed_ids.add(int(inv.id))
            if inv.type == "sale":
                for item in inv.items or []:
                    qty = r3(item.get("quantity") or 0)
                    if qty <= 0 or not item.get("product_id"):
                        continue
                    product = _ensure_invoice_product(db, item)
                    product.stock = r3(float(product.stock or 0) + qty)
                if inv.customer_id:
                    customer = db.query(Customer).filter(Customer.id == inv.customer_id).with_for_update().first()
                    if customer:
                        customer.balance = r2(float(customer.balance or 0) - float(inv.remaining or 0))
            elif inv.type == "return":
                for item in inv.items or []:
                    qty = r3(item.get("quantity") or 0)
                    if qty <= 0 or not item.get("product_id"):
                        continue
                    product = _ensure_invoice_product(db, item)
                    product.stock = r3(float(product.stock or 0) - qty)
                if inv.customer_id:
                    customer = db.query(Customer).filter(Customer.id == inv.customer_id).with_for_update().first()
                    if customer:
                        # Only the non-cash portion of a return reduced debt.
                        customer.balance = r2(float(customer.balance or 0) + float(inv.remaining or 0))

            db.query(CustomerLedger).filter(CustomerLedger.invoice_id == inv.id).delete(synchronize_session=False)
            db.query(StockMovement).filter(StockMovement.invoice_id == inv.id).delete(synchronize_session=False)
            db.delete(inv)
            db.flush()

        if invoice.type == "sale":
            linked = db.query(Invoice).filter(
                Invoice.original_invoice_id == invoice.id,
                Invoice.type == "return",
            ).order_by(Invoice.id.desc()).with_for_update().all()
            for ret in linked:
                remove_one(ret)
            remove_one(invoice)
        else:
            remove_one(invoice)

        # Combined invoices are document snapshots with no accounting effect.
        # If any of their source documents disappears, removing the stale
        # snapshot is safer than presenting a combined document that can no
        # longer be reconciled to its sources.
        combined = db.query(Invoice).filter(Invoice.type == "combined").with_for_update().all()
        for doc in combined:
            source_ids = set()
            for raw in doc.combined_source_ids or []:
                try:
                    source_ids.add(int(raw))
                except (TypeError, ValueError):
                    pass
            opts = doc.combined_options if isinstance(doc.combined_options, dict) else {}
            for raw in opts.get("applied_return_ids", []) or []:
                try:
                    source_ids.add(int(raw))
                except (TypeError, ValueError):
                    pass
            if source_ids.intersection(removed_ids):
                snapshots.append(_invoice_snapshot(doc))
                db.delete(doc)

        db.info[_AUDIT_SNAPSHOT_KEY] = " | ".join(snapshots)

    routes.create_sale_invoice = create_sale_active_only
    routes.delete_sale_invoice = reverse_delete_invoice


def _install_report_filters() -> None:
    """Operational counts ignore archived rows; debt never disappears by archive."""
    from app.api.routes import reports as routes

    original_dashboard = routes.get_dashboard
    original_profit = routes.get_profit_report

    def dashboard_active(db: Session, *, user_role: str = "admin", user_id: Optional[int] = None):
        data = original_dashboard(db, user_role=user_role, user_id=user_id)
        data["products_count"] = _active_product_query(db).count()
        data["customers_count"] = _active_customer_query(db).count()
        # Keep all positive balances (including archived clients) because an
        # archive must never make a real receivable disappear from accounting.
        if user_role != "cashier":
            data["total_debts"] = money_n(db.query(func.sum(Customer.balance)).filter(Customer.balance > 0).scalar() or 0)
        return data

    def low_stock_active(db: Session, threshold: float = 5):
        items = _active_product_query(db).filter(Product.stock <= threshold).order_by(Product.stock).limit(50).all()
        return [{
            "id": p.id, "name": p.name, "stock": r3(p.stock),
            "price": money_n(p.price), "barcode": p.barcode or "",
        } for p in items]

    def debts_with_archive_flag(db: Session):
        items = db.query(Customer).filter(Customer.balance > 0).order_by(Customer.balance.desc()).all()
        return [{
            "id": c.id,
            "name": c.name,
            "phone": c.phone or "",
            "balance": money_n(c.balance),
            "archived": not bool(getattr(c, "active", True)),
        } for c in items]

    routes.get_dashboard = dashboard_active
    routes.get_low_stock = low_stock_active
    routes.get_customer_debts = debts_with_archive_flag
    routes.get_profit_report = original_profit


def install_market_readiness() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_archive_columns()
    _install_product_routes()
    _install_customer_routes()
    _install_invoice_accounting_guards()
    _install_report_filters()
    _INSTALLED = True
