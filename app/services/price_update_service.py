"""Update existing product prices from CSV/XLSX without creating products."""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.services.import_export_engine import MAX_FILE_BYTES, _find_col, parse_file, safe_str, strict_float

log = logging.getLogger("pospro.price_update")


def update_product_prices(db: Session, raw: bytes, filename: str) -> dict[str, Any]:
    if not raw:
        return {"ok": False, "error": "ملف فارغ"}
    if len(raw) > MAX_FILE_BYTES:
        return {"ok": False, "error": f"حجم الملف أكبر من {MAX_FILE_BYTES // (1024 * 1024)} MB"}
    try:
        headers, rows = parse_file(filename, raw)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        log.exception("Price update file parse failed")
        return {"ok": False, "error": "فشل قراءة الملف"}
    if not headers or not rows:
        return {"ok": False, "error": "الملف لا يحتوي على بيانات"}

    idx_name = _find_col(headers, "الاسم", "Name", "name", "product", "الصنف")
    idx_barcode = _find_col(headers, "الباركود", "Barcode", "barcode")
    idx_code = _find_col(headers, "الكود", "Code", "code", "sku")
    idx_price = _find_col(headers, "السعر", "Price", "price", "سعر البيع")
    idx_cost = _find_col(headers, "التكلفة", "Cost", "cost", "سعر التكلفة")
    if idx_price is None and idx_cost is None:
        return {"ok": False, "error": "يجب أن يحتوي الملف على عمود السعر أو التكلفة"}
    if idx_barcode is None and idx_code is None and idx_name is None:
        return {"ok": False, "error": "يلزم الباركود أو الكود أو الاسم لمطابقة المنتجات"}

    from app.db.models import Product

    products = db.query(Product).all()
    by_barcode = {str(p.barcode).strip(): p for p in products if p.barcode}
    by_code = {str(p.code).strip(): p for p in products if p.code}
    by_name: dict[str, list[Product]] = {}
    for product in products:
        by_name.setdefault((product.name or "").strip().casefold(), []).append(product)

    def cell(row: list[Any], idx: Optional[int]) -> Any:
        return row[idx] if idx is not None and idx < len(row) else None

    updated = unchanged = not_found = 0
    errors: list[dict[str, Any]] = []
    for row_num, row in enumerate(rows, start=2):
        if not row or all(c is None or safe_str(c) == "" for c in row):
            continue
        barcode = safe_str(cell(row, idx_barcode))
        code = safe_str(cell(row, idx_code))
        name = safe_str(cell(row, idx_name))
        try:
            matches: list[Product] = []
            if barcode and barcode in by_barcode:
                matches.append(by_barcode[barcode])
            if code and code in by_code and by_code[code] not in matches:
                matches.append(by_code[code])
            if len(matches) > 1:
                raise ValueError("الباركود والكود يشيران إلى منتجين مختلفين")
            product = matches[0] if matches else None
            if product is None and name:
                name_matches = by_name.get(name.casefold(), [])
                if len(name_matches) == 1:
                    product = name_matches[0]
                elif len(name_matches) > 1:
                    raise ValueError("الاسم مكرر؛ استخدم الباركود أو الكود")
            if product is None:
                not_found += 1
                errors.append({"row": row_num, "name": name, "error": "المنتج غير موجود؛ لم يتم إنشاء منتج جديد"})
                continue

            changed = False
            if idx_price is not None and safe_str(cell(row, idx_price)) != "":
                price = strict_float(cell(row, idx_price))
                if price < 0:
                    raise ValueError("السعر لا يمكن أن يكون سالباً")
                if float(product.price or 0) != price:
                    product.price = price
                    changed = True
            if idx_cost is not None and safe_str(cell(row, idx_cost)) != "":
                cost = strict_float(cell(row, idx_cost))
                if cost < 0:
                    raise ValueError("التكلفة لا يمكن أن تكون سالبة")
                if float(product.cost or 0) != cost:
                    product.cost = cost
                    changed = True
            if changed:
                updated += 1
            else:
                unchanged += 1
        except ValueError as exc:
            errors.append({"row": row_num, "name": name, "error": str(exc)[:200]})
        except Exception:
            log.exception("Unexpected price update failure at row %s", row_num)
            errors.append({"row": row_num, "name": name, "error": "تعذر تحديث هذا الصف"})

    try:
        db.flush()
    except SQLAlchemyError:
        db.rollback()
        log.exception("Price update flush failed")
        return {"ok": False, "error": "فشل تجهيز تحديثات الأسعار"}
    return {
        "ok": True,
        "updated": updated,
        "unchanged": unchanged,
        "not_found": not_found,
        "errors": errors[:50],
        "total_errors": len(errors),
    }
