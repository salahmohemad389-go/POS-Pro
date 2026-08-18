"""Report routes for POS Pro."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.permissions import has_permission
from app.db.session import get_db
from app.core.security import get_current_user
from app.db.models import User
from app.services.report_service import get_dashboard, get_low_stock, get_profit_report, get_customer_debts

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/dashboard")
async def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "report_dashboard"):
        raise HTTPException(403, "لا تملك صلاحية")
    return get_dashboard(db, user_role=user.role, user_id=user.id)


@router.get("/low-stock")
async def low_stock(threshold: float = Query(5, ge=0), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "report_low_stock"):
        raise HTTPException(403, "لا تملك صلاحية")
    return get_low_stock(db, threshold)


@router.get("/profit")
async def profit_report(date_from: Optional[str] = None, date_to: Optional[str] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "report_profit"):
        raise HTTPException(403, "لا تملك صلاحية")
    return get_profit_report(db, date_from=date_from, date_to=date_to)


@router.get("/customer-debts")
async def customer_debts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "report_customer_debts"):
        raise HTTPException(403, "لا تملك صلاحية")
    return get_customer_debts(db)
