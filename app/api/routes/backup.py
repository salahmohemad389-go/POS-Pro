"""Backup routes for POS Pro."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import IS_SQLITE
from app.db.session import get_db, engine
from app.core.security import get_current_user
from app.core.permissions import has_permission
from app.db.models import User
from app.services.audit_service import log_audit
from app.services.backup_service import make_backup, list_backups, restore_backup
from app.schemas.requests import BackupRestore

router = APIRouter(prefix="/api/backup", tags=["backup"])


def _rate_limit_or_403(key: str, limit_type: str):
    from app.core.ratelimit import consume_attempt
    from fastapi import status
    allowed, remaining = consume_attempt(key, limit_type)
    if not allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"تجاوزت الحد المسموح. حاول بعد {remaining // 60 + 1} دقيقة")


@router.post("")
async def create_backup_endpoint(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _rate_limit_or_403(f"backup:{user.id}", "export")
    if not has_permission(user, "backup_create"):
        raise HTTPException(403, "صلاحية المدير مطلوبة")
    if not IS_SQLITE:
        raise HTTPException(409, "النسخ المحلية داخل التطبيق غير متاحة مع PostgreSQL؛ استخدم النسخ الاحتياطية المُدارة لدى مزود قاعدة البيانات")
    path = make_backup()
    if not path:
        raise HTTPException(503, "تعذر إنشاء النسخة الاحتياطية")
    log_audit(db, user, "backup", f"نسخة احتياطية: {path}", request.client.host if request else None)
    return {"ok": True, "name": Path(path).name}


@router.get("/list")
async def list_backups_endpoint(user: User = Depends(get_current_user)):
    if not has_permission(user, "backup_create"):
        raise HTTPException(403, "صلاحية المدير مطلوبة")
    return list_backups()




@router.get("/download/{name}")
async def download_backup(name: str, user: User = Depends(get_current_user)):
    if not has_permission(user, "backup_create"):
        raise HTTPException(403, "صلاحية المدير مطلوبة")
    if not IS_SQLITE:
        raise HTTPException(409, "التنزيل المحلي مخصص لنسخة SQLite")
    safe = Path(name).name
    if safe != name or not safe.startswith("backup_") or not safe.endswith(".zip"):
        raise HTTPException(400, "اسم النسخة غير صالح")
    from app.core.config import BACKUP_DIR
    path = (BACKUP_DIR / safe).resolve()
    if path.parent != BACKUP_DIR.resolve() or not path.exists():
        raise HTTPException(404, "النسخة غير موجودة")
    from fastapi.responses import FileResponse
    return FileResponse(str(path), media_type="application/zip", filename=safe)

@router.post("/restore")
async def restore_backup_endpoint(payload: BackupRestore, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_permission(user, "backup_restore"):
        raise HTTPException(403, "صلاحية المدير مطلوبة")
    if not IS_SQLITE:
        raise HTTPException(400, "استعادة ZIP مخصصة لقاعدة SQLite المحلية فقط.")
    name = payload.name
    db.close()
    engine.dispose()
    try:
        return restore_backup(name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        raise HTTPException(500, "فشل الاستعادة بسبب خطأ داخلي")
