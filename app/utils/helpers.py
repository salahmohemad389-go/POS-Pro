"""Generic utility helpers for POS Pro.

These are pure functions with no database or FastAPI dependencies.
Database helpers (record_ledger_entry, record_stock_movement) are also
provided here since they are used by both the API layer and services.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session


MONEY_QUANT = Decimal("0.01")
STOCK_QUANT = Decimal("0.001")


def _dec(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def r2(n) -> float:
    """Round money deterministically using commercial HALF_UP rounding."""
    return float(_dec(n).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def r3(n) -> float:
    """Round stock/quantities to the database's 3-decimal precision."""
    return float(_dec(n).quantize(STOCK_QUANT, rounding=ROUND_HALF_UP))


def money_n(value) -> float:
    """Convert DB Numeric/Decimal money to JSON-safe two-decimal float."""
    return r2(value)


def safe_str(val, default: str = "") -> str:
    """Coerce any value to a stripped string."""
    if val is None:
        return default
    try:
        s = str(val).strip()
        return s if s else default
    except Exception:
        return default


def safe_float(val, default: float = 0.0) -> float:
    """Parse a numeric value without silently changing its precision."""
    if val is None or val == "":
        return default
    try:
        return float(_dec(val))
    except (ValueError, TypeError, ArithmeticError):
        return default


# ── Database helpers (used by invoice_service, customers route, etc.) ──


def record_ledger_entry(
    db: Session,
    customer_id: int,
    customer_name: str,
    *,
    invoice_id: Optional[int] = None,
    invoice_number: Optional[str] = None,
    movement_type: str,
    description: str = "",
    debit: float = 0,
    credit: float = 0,
    user_name: str = "",
    user_id: Optional[int] = None,
) -> None:
    """Insert a ledger entry. The balance_after is computed from Customer.balance."""
    from app.db.models import Customer, CustomerLedger

    c = db.query(Customer).filter(Customer.id == customer_id).first()
    balance_after = money_n(c.balance) if c else 0
    entry = CustomerLedger(
        customer_id=customer_id,
        customer_name=customer_name,
        invoice_id=invoice_id,
        invoice_number=invoice_number,
        movement_type=movement_type,
        description=description,
        debit=r2(debit),
        credit=r2(credit),
        balance_after=balance_after,
        user_id=user_id,
        user_name=user_name,
    )
    db.add(entry)


def record_stock_movement(
    db: Session,
    product_id: int,
    product_name: str,
    quantity_delta: float,
    *,
    unit_cost: float = 0,
    movement_type: str = "sale",
    invoice_id: Optional[int] = None,
    invoice_number: Optional[str] = None,
    user_name: str = "",
    user_id: Optional[int] = None,
    notes: str = "",
) -> None:
    """Record a stock movement (negative quantity = sold, positive = returned)."""
    from app.db.models import StockMovement

    entry = StockMovement(
        product_id=product_id,
        product_name=product_name,
        quantity=r3(quantity_delta),
        unit_cost=r2(unit_cost),
        movement_type=movement_type,
        invoice_id=invoice_id,
        invoice_number=invoice_number,
        user_id=user_id,
        user_name=user_name,
        notes=notes,
    )
    db.add(entry)
