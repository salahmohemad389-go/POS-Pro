"""Report service for POS Pro.

Dashboard, low stock, profit, customer debts - all read-only queries.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.db.models import Customer, Invoice, Product
from app.utils.helpers import money_n, r3

log = logging.getLogger("pospro.services.report")


def get_dashboard(db: Session, *, user_role: str = "admin", user_id: Optional[int] = None) -> dict[str, Any]:
    """Net operational dashboard: sales minus returns, including product return impact."""
    today_start = datetime.now(timezone.utc).replace(tzinfo=None).replace(hour=0, minute=0, second=0, microsecond=0)

    def _net_total(start, end=None):
        q = db.query(Invoice.type, func.sum(Invoice.total)).filter(Invoice.created_at >= start, Invoice.type.in_(["sale", "return"]))
        if end is not None:
            q = q.filter(Invoice.created_at < end)
        if user_role == "cashier":
            q = q.filter(Invoice.user_id == user_id)
        rows = q.group_by(Invoice.type).all()
        vals = {kind: float(total or 0) for kind, total in rows}
        return money_n(vals.get("sale", 0) - vals.get("return", 0))

    today_sales = _net_total(today_start)
    chart = []
    for i in range(6, -1, -1):
        day = today_start - timedelta(days=i)
        next_day = day + timedelta(days=1)
        chart.append({"date": day.strftime("%Y-%m-%d"), "total": _net_total(day, next_day)})

    since = today_start - timedelta(days=30)
    inv_q = db.query(Invoice).filter(Invoice.created_at >= since, Invoice.type.in_(["sale", "return"]))
    if user_role == "cashier":
        inv_q = inv_q.filter(Invoice.user_id == user_id)

    prod_stats: dict[int, dict] = {}
    for inv in inv_q.yield_per(500):
        sign = -1.0 if inv.type == "return" else 1.0
        for it in inv.items or []:
            pid = it.get("product_id")
            if not pid:
                continue
            if pid not in prod_stats:
                prod_stats[pid] = {"name": it.get("product_name", ""), "qty": 0.0, "revenue": 0.0}
            prod_stats[pid]["qty"] += float(it.get("quantity") or 0) * sign
            prod_stats[pid]["revenue"] += float(it.get("total") or 0) * sign
    top = sorted(prod_stats.values(), key=lambda x: x["revenue"], reverse=True)[:10]

    products_count = db.query(Product).count()
    customers_count = db.query(Customer).count()
    total_debts = 0 if user_role == "cashier" else (db.query(func.sum(Customer.balance)).filter(Customer.balance > 0).scalar() or 0)
    q_recent = db.query(Invoice)
    if user_role == "cashier":
        q_recent = q_recent.filter(Invoice.user_id == user_id)
    q_recent = q_recent.order_by(desc(Invoice.created_at)).limit(10)
    return {
        "today_sales": today_sales,
        "products_count": products_count,
        "customers_count": customers_count,
        "total_debts": money_n(total_debts),
        "sales_chart": chart,
        "top_products": [{"product_name": t["name"], "revenue": money_n(t["revenue"]), "quantity": r3(t["qty"])} for t in top],
        "recent_invoices": [{
            "id": inv.id, "number": inv.number, "customer_name": inv.customer_name or "",
            "total": money_n(inv.total) * (-1 if inv.type == "return" else 1), "type": inv.type,
            "status": inv.status, "created_at": inv.created_at.isoformat() if inv.created_at else None,
        } for inv in q_recent.all()],
    }


def get_low_stock(db: Session, threshold: float = 5) -> list[dict[str, Any]]:
    items = (
        db.query(Product)
        .filter(Product.stock <= threshold)
        .order_by(Product.stock)
        .limit(50)
        .all()
    )
    return [
        {"id": p.id, "name": p.name, "stock": r3(p.stock), "price": money_n(p.price), "barcode": p.barcode or ""}
        for p in items
    ]


def get_profit_report(
    db: Session,
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict[str, Any]:
    q = db.query(Invoice).filter(Invoice.type.in_(["sale", "return"]))
    if date_from:
        try:
            q = q.filter(Invoice.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(Invoice.created_at <= datetime.fromisoformat(date_to))
        except ValueError:
            pass

    total_revenue = 0.0
    total_cost = 0.0
    sale_count = 0
    return_count = 0
    for inv in q.yield_per(500):
        sign = -1.0 if inv.type == "return" else 1.0
        if inv.type == "sale": sale_count += 1
        else: return_count += 1
        total_revenue += sign * money_n(inv.total)
        total_cost += sign * sum(
            float(it.get("cost") or 0) * float(it.get("quantity") or 0)
            for it in (inv.items or [])
        )
    profit = total_revenue - total_cost
    return {
        "total_revenue": money_n(total_revenue),
        "total_cost": money_n(total_cost),
        "profit": money_n(profit),
        "invoices_count": sale_count,
        "returns_count": return_count,
        "profit_margin": money_n((profit / total_revenue * 100) if total_revenue > 0 else 0),
    }


def get_customer_debts(db: Session) -> list[dict[str, Any]]:
    items = db.query(Customer).filter(Customer.balance > 0).order_by(desc(Customer.balance)).all()
    return [
        {"id": c.id, "name": c.name, "phone": c.phone or "", "balance": money_n(c.balance)}
        for c in items
    ]
