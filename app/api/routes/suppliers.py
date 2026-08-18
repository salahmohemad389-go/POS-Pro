"""Supplier routes for POS Pro."""

from __future__ import annotations

from pathlib import Path

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.permissions import has_permission
from app.db.models import Supplier
from app.db.session import get_db
from app.core.security import get_current_user
from app.db.models import User
from app.services.audit_service import log_audit
from app.services.import_service import export_suppliers, write_csv, write_xlsx
from app.utils.helpers import money_n
from app.schemas.requests import SupplierSave

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


def _rate_limit_or_403(key: str, limit_type: str):
    from app.core.ratelimit import consume_attempt
    from fastapi import status
    allowed, remaining = consume_attempt(key, limit_type)
    if not allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"تجاوزت الحد المسموح. حاول بعد {remaining // 60 + 1} دقيقة")


@router.get("")
async def list_suppliers(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    q: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not has_permission(user, "supplier_view"):
        raise HTTPException(403, "لا تملك صلاحية")
    query = db.query(Supplier)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(Supplier.name.ilike(like), Supplier.phone.ilike(like), Supplier.email.ilike(like)))
    total = query.count()
    items = query.order_by(Supplier.name).offset((page - 1) * limit).limit(limit).all()
    return {"total": total, "page": page, "limit": limit, "items": [s.to_dict() for s in items]}


@router.post("")
async def save_supplier(payload: SupplierSave, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _rate_limit_or_403(f"supplier_write:{user.id}", "write")
    if not has_permission(user, "supplier_save"):
        raise HTTPException(403, "لا تملك صلاحية")
    data = payload.model_dump()
    sid = data.get("id")
    name = data["name"].strip()
    if not name:
        raise HTTPException(400, "أدخل اسم المورد")
    if sid:
        s = db.query(Supplier).filter(Supplier.id == sid).first()
        if not s:
            raise HTTPException(404, "مورد غير موجود")
    else:
        s = Supplier()
        db.add(s)
    s.name = name
    s.phone = data.get("phone", "").strip()
    s.email = data.get("email", "").strip()
    s.address = data.get("address", "").strip()
    s.notes = data.get("notes", "").strip()
    try:
        log_audit(db, user, "supplier_save", f"{'تعديل' if sid else 'إضافة'} مورد: {name}", request.client.host if request else None, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر حفظ المورد")
    return {"ok": True, "id": s.id}


@router.delete("/{sid}")
async def delete_supplier(sid: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _rate_limit_or_403(f"supplier_delete:{user.id}", "delete")
    if not has_permission(user, "supplier_delete"):
        raise HTTPException(403, "صلاحية المدير مطلوبة")
    s = db.query(Supplier).filter(Supplier.id == sid).first()
    if not s:
        raise HTTPException(404, "مورد غير موجود")
    name = s.name
    db.delete(s)
    try:
        log_audit(db, user, "supplier_delete", f"حذف مورد: {name}", request.client.host if request else None, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر حذف المورد")
    return {"ok": True}


@router.get("/export")
async def export_suppliers_endpoint(request: Request, format: str = "xlsx", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    from datetime import datetime as dt
    if not has_permission(user, "supplier_export"):
        raise HTTPException(403, "لا تملك صلاحية")
    _rate_limit_or_403(f"export:{user.id}", "export")
    result = export_suppliers(db)
    ts = dt.now().strftime('%Y%m%d_%H%M%S')
    if format == "csv":
        path = write_csv(result["headers"], result["rows"], "suppliers")
        filename = f"suppliers_{ts}.csv"
        media_type = "text/csv; charset=utf-8"
    else:
        path = write_xlsx(result["headers"], result["rows"], "suppliers")
        filename = f"suppliers_{ts}.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    log_audit(db, user, "suppliers_export", f"تصدير {format.upper()}: {result['count']} سجل", request.client.host if request else None)
    from starlette.background import BackgroundTask
    cleanup = BackgroundTask(lambda p=str(path): Path(p).unlink(missing_ok=True))
    return FileResponse(str(path), media_type=media_type, filename=filename, headers={"Content-Disposition": f'attachment; filename="{filename}"'}, background=cleanup)
