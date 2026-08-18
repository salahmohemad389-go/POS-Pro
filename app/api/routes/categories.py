"""Category routes for POS Pro."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.cache import get as cache_get, set as cache_set, invalidate as cache_invalidate
from app.core.permissions import has_permission
from app.db.models import Category, Product
from app.db.session import get_db
from app.core.security import get_current_user
from app.db.models import User
from app.services.audit_service import log_audit
from app.schemas.requests import CategorySave

router = APIRouter(prefix="/api/categories", tags=["categories"])


def _rate_limit_or_403(key: str, limit_type: str):
    from app.core.ratelimit import consume_attempt
    from fastapi import status
    allowed, remaining = consume_attempt(key, limit_type)
    if not allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"تجاوزت الحد المسموح. حاول بعد {remaining // 60 + 1} دقيقة")


@router.get("")
async def list_categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cached_data = cache_get("categories")
    if cached_data is not None:
        return cached_data
    data = [c.to_dict() for c in db.query(Category).order_by(Category.name).all()]
    cache_set("categories", data)
    return data


@router.post("")
async def save_category(payload: CategorySave, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _rate_limit_or_403(f"category_write:{user.id}", "write")
    if not has_permission(user, "category_save"):
        raise HTTPException(403, "لا تملك صلاحية")
    data = payload.model_dump()
    cid = data.get("id")
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "أدخل اسم القسم")
    if cid:
        c = db.query(Category).filter(Category.id == cid).first()
        if not c:
            raise HTTPException(404, "قسم غير موجود")
    else:
        c = Category()
        db.add(c)
    c.name = name
    parent_id = data.get("parent_id")
    if parent_id:
        if cid and int(parent_id) == int(cid):
            raise HTTPException(400, "لا يمكن أن يكون القسم أباً لنفسه")
        parent = db.query(Category).filter(Category.id == int(parent_id)).first()
        if not parent:
            raise HTTPException(400, "القسم الأب غير موجود")
        # Prevent cycles when moving an existing node under one of its descendants.
        cursor = parent
        seen = set()
        while cursor and cursor.id not in seen:
            if cid and cursor.id == int(cid):
                raise HTTPException(400, "لا يمكن إنشاء دورة في شجرة الأقسام")
            seen.add(cursor.id)
            cursor = db.query(Category).filter(Category.id == cursor.parent_id).first() if cursor.parent_id else None
    c.parent_id = int(parent_id) if parent_id else None
    try:
        log_audit(db, user, "category_save", f"{'تعديل' if cid else 'إضافة'} قسم: {name}", request.client.host if request else None, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر حفظ القسم")
    cache_invalidate("categories")
    return {"ok": True, "id": c.id}


@router.delete("/{cid}")
async def delete_category(cid: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _rate_limit_or_403(f"category_delete:{user.id}", "delete")
    if not has_permission(user, "category_delete"):
        raise HTTPException(403, "لا تملك صلاحية")
    c = db.query(Category).filter(Category.id == cid).first()
    if not c:
        raise HTTPException(404, "قسم غير موجود")
    name = c.name
    child_count = db.query(Category).filter(Category.parent_id == cid).count()
    product_count = db.query(Product).filter(Product.category_id == cid).count()
    if child_count or product_count:
        raise HTTPException(409, f"لا يمكن حذف القسم: مرتبط بـ {child_count} قسم فرعي و {product_count} منتج")
    db.delete(c)
    try:
        log_audit(db, user, "category_delete", f"حذف: {name}", request.client.host if request else None, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "تعذر حذف القسم")
    cache_invalidate("categories")
    return {"ok": True}
