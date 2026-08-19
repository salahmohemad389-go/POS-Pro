"""Product routes for POS Pro."""

from __future__ import annotations

from pathlib import Path

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import case, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.permissions import has_permission
from app.db.models import Category, Product, StockMovement, Supplier
from app.db.session import get_db
from app.core.security import get_current_user
from app.db.models import User
from app.services.audit_service import log_audit
from app.services.import_service import import_products as do_import, update_product_prices as do_price_update, export_products, write_csv, write_xlsx
from app.schemas.requests import ProductSave, ProductFind
from app.utils.helpers import money_n, r2, r3, record_stock_movement

router = APIRouter(prefix="/api/products", tags=["products"])


def _rate_limit_or_403(key: str, limit_type: str):
    from app.core.ratelimit import consume_attempt
    from fastapi import status
    allowed, remaining = consume_attempt(key, limit_type)
    if not allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"تجاوزت الحد المسموح. حاول بعد {remaining // 60 + 1} دقيقة")


@router.get("")
async def list_products(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    q: Optional[str] = None,
    category_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not has_permission(user, "product_view"):
        raise HTTPException(403, "لا تملك صلاحية عرض المنتجات")
    query = db.query(Product)
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
    if search_rank is not None:
        query = query.order_by(search_rank, Product.name, Product.id)
    else:
        query = query.order_by(Product.name, Product.id)
    items = query.offset((page - 1) * limit).limit(limit).all()
    return {"total": total, "page": page, "limit": limit, "items": [p.to_dict() for p in items]}


@router.get("/by-barcode/{barcode}")
async def product_by_barcode(barcode: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "product_view"):
        raise HTTPException(403, "لا تملك صلاحية عرض المنتجات")
    if barcode is None:
        return None
    raw = str(barcode).strip()
    raw = "".join(ch for ch in raw if ord(ch) >= 32 or ch == "\t").strip()
    if not raw:
        return None
    p = db.query(Product).filter(or_(Product.barcode == raw, Product.code == raw)).first()
    if p:
        return p.to_dict()
    p = db.query(Product).filter(or_(func.trim(Product.barcode) == raw, func.trim(Product.code) == raw)).first()
    return p.to_dict() if p else None


@router.post("/find")
async def product_find(payload: ProductFind, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "product_view"):
        raise HTTPException(403, "لا تملك صلاحية عرض المنتجات")
    q = payload.q.strip()
    if not q:
        return {"matches": [], "exact": None}
    raw = "".join(ch for ch in q if ord(ch) >= 32 or ch == "\t").strip()
    if not raw:
        return {"matches": [], "exact": None}

    exact = db.query(Product).filter(or_(Product.barcode == raw, Product.code == raw)).first()
    if exact:
        return {"matches": [exact.to_dict()], "exact": exact.to_dict()}
    p = db.query(Product).filter(or_(func.trim(Product.barcode) == raw, func.trim(Product.code) == raw)).first()
    if p:
        return {"matches": [p.to_dict()], "exact": p.to_dict()}
    if raw.isdigit():
        p = db.query(Product).filter(Product.id == int(raw)).first()
        if p:
            return {"matches": [p.to_dict()], "exact": p.to_dict()}
    like = f"%{raw}%"
    matches = db.query(Product).filter(or_(Product.barcode.ilike(like), Product.code.ilike(like), Product.name.ilike(like))).limit(10).all()
    return {"matches": [m.to_dict() for m in matches], "exact": None}


@router.post("")
async def save_product(payload: ProductSave, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _rate_limit_or_403(f"product_write:{user.id}", "write")
    if not has_permission(user, "product_save"):
        raise HTTPException(403, "لا تملك صلاحية")
    data = payload.model_dump()
    pid = data.get("id")
    old_stock = 0.0
    if pid:
        p = db.query(Product).filter(Product.id == pid).first()
        if not p:
            raise HTTPException(404, "منتج غير موجود")
        old_stock = float(p.stock or 0)
    else:
        p = Product()
        db.add(p)
    p.name = (data.get("name") or "").strip()
    if not p.name:
        raise HTTPException(400, "أدخل اسم المنتج")
    new_barcode = (data.get("barcode") or "").strip()
    new_code = (data.get("code") or "").strip()

    if new_barcode:
        existing_barcode = db.query(Product).filter(Product.barcode == new_barcode, Product.id != (pid or 0)).first()
        if existing_barcode:
            raise HTTPException(400, f"الباركود '{new_barcode}' مستخدم بالفعل في منتج آخر")
    if new_code:
        existing_code = db.query(Product).filter(Product.code == new_code, Product.id != (pid or 0)).first()
        if existing_code:
            raise HTTPException(400, f"الكود '{new_code}' مستخدم بالفعل في منتج آخر")

    p.barcode = new_barcode
    p.code = new_code
    p.category_id = int(data["category_id"]) if data.get("category_id") else None
    p.supplier_id = int(data["supplier_id"]) if data.get("supplier_id") else None
    p.unit = data.get("unit") or "قطعة"
    p.cost = r2(data.get("cost", 0))
    p.price = r2(data.get("price", 0))
    p.stock = r3(data.get("stock", 0))
    p.min_stock = r3(data.get("min_stock", 5))
    db.flush()
    stock_delta = r3(float(p.stock or 0) - old_stock)
    if abs(stock_delta) >= 0.001:
        record_stock_movement(
            db, product_id=p.id, product_name=p.name, quantity_delta=stock_delta,
            unit_cost=float(p.cost or 0), movement_type="adjustment",
            user_name=user.name, user_id=user.id, notes="تعديل مخزون من شاشة المنتج",
        )
    try:
        log_audit(db, user, "product_save", f"{'تعديل' if pid else 'إضافة'} منتج: {p.name}", request.client.host if request else None, commit=False)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        msg = str(exc).lower()
        if "unique" in msg:
            if "barcode" in msg:
                raise HTTPException(400, f"الباركود '{new_barcode}' مستخدم بالفعل")
            if "code" in msg:
                raise HTTPException(400, f"الكود '{new_code}' مستخدم بالفعل")
        raise HTTPException(500, "تعذر حفظ المنتج بسبب خطأ داخلي في قاعدة البيانات")
    return {"ok": True, "id": p.id}


@router.get("/export")
async def export_products_endpoint(request: Request, format: str = "xlsx", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    if not has_permission(user, "product_export"):
        raise HTTPException(403, "لا تملك صلاحية")
    _rate_limit_or_403(f"export:{user.id}", "export")
    result = export_products(db, format)
    from datetime import datetime as dt
    ts = dt.now().strftime('%Y%m%d_%H%M%S')
    if format == "csv":
        path = write_csv(result["headers"], result["rows"], "products")
        filename = f"products_{ts}.csv"
        media_type = "text/csv; charset=utf-8"
    else:
        path = write_xlsx(result["headers"], result["rows"], "products")
        filename = f"products_{ts}.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    log_audit(db, user, "products_export", f"تصدير {format.upper()}: {result['count']} سجل", request.client.host if request else None)
    from starlette.background import BackgroundTask
    cleanup = BackgroundTask(lambda p=str(path): Path(p).unlink(missing_ok=True))
    return FileResponse(str(path), media_type=media_type, filename=filename, headers={"Content-Disposition": f'attachment; filename="{filename}"'}, background=cleanup)


@router.post("/import-prices")
async def update_product_prices_endpoint(request: Request, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "product_import"):
        raise HTTPException(403, "لا تملك صلاحية")
    _rate_limit_or_403(f"product_price_import:{user.id}", "write")
    filename = (file.filename or "").lower()
    if not filename:
        raise HTTPException(400, "اسم الملف مطلوب")
    raw = await file.read()
    result = do_price_update(db, raw, filename)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "فشل تحديث الأسعار")
    try:
        log_audit(db, user, "products_price_update", f"تحديث أسعار {result['updated']} منتج من {filename}", request.client.host if request else None, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر حفظ تحديث الأسعار بأمان")
    return result


@router.get("/{pid}")
async def get_product(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "product_view"):
        raise HTTPException(403, "لا تملك صلاحية عرض المنتجات")
    p = db.query(Product).filter(Product.id == pid).first()
    if not p:
        raise HTTPException(404, "منتج غير موجود")
    return p.to_dict()


@router.delete("/{pid}")
async def delete_product(pid: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _rate_limit_or_403(f"product_delete:{user.id}", "delete")
    if not has_permission(user, "product_delete"):
        raise HTTPException(403, "لا تملك صلاحية")
    p = db.query(Product).filter(Product.id == pid).first()
    if not p:
        raise HTTPException(404, "منتج غير موجود")
    has_movements = db.query(StockMovement).filter(StockMovement.product_id == pid).first()
    if has_movements:
        raise HTTPException(400, "لا يمكن حذف هذا المنتج لأنه له حركات مخزون/مبيعات سابقة.")
    name = p.name
    db.delete(p)
    try:
        log_audit(db, user, "product_delete", f"حذف: {name}", request.client.host if request else None, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر حذف المنتج")
    return {"ok": True}


@router.post("/import")
async def import_products_endpoint(request: Request, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "product_save"):
        raise HTTPException(403, "لا تملك صلاحية")
    _rate_limit_or_403(f"product_import:{user.id}", "write")
    filename = (file.filename or "").lower()
    if not filename:
        raise HTTPException(400, "اسم الملف مطلوب")
    raw = await file.read()
    result = do_import(db, raw, filename)
    if not result.get("ok"):
        err = result.get("error", "")
        if "كبير" in err or "MAX" in err or "الحد" in err:
            raise HTTPException(413, err)
        raise HTTPException(400, err)
    log_audit(db, user, "products_import", f"استيراد {result['added']} منتج (تخطي {result['skipped_duplicates']} مكرر، أخطاء {result['total_errors']}) من {filename}", request.client.host if request else None)
    return result
