"""Backup service for POS Pro.

Handles SQLite backup/restore and scheduled maintenance.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from app.core.config import IS_SQLITE, DATA_DIR, BACKUP_DIR
from app.db.session import SessionLocal, engine

log = logging.getLogger("pospro.services.backup")


def _sqlite_db_path() -> Path | None:
    if not IS_SQLITE:
        return None
    value = engine.url.database
    if not value or value == ":memory:":
        return None
    return Path(value).expanduser().resolve()



def make_backup() -> str | None:
    """Create a compressed ZIP backup of the SQLite DB."""
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        if not IS_SQLITE:
            log.info("Built-in ZIP backup skipped for server database")
            return None
        db_path = _sqlite_db_path()
        if db_path is None or not db_path.exists():
            return None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        temp_dir = tempfile.gettempdir()
        temp_db = Path(temp_dir) / f"pospro_temp_{ts}.db"
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(temp_db))
        with dst:
            src.backup(dst)
        src.close()
        dst.close()

        zip_path = BACKUP_DIR / f"backup_{ts}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(temp_db, f"pospro_{ts}.db")
            rate_file = DATA_DIR / "rate_limits.json"
            if rate_file.exists():
                zf.write(rate_file, "rate_limits.json")
        temp_db.unlink()

        # Keep only last 30 backups
        backups = sorted(BACKUP_DIR.glob("backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[30:]:
            try:
                old.unlink()
            except OSError as exc:
                log.warning("Could not delete old backup %s: %s", old, exc)
        return str(zip_path)
    except Exception as e:
        log.error("Backup failed: %s", e)
        return None


def list_backups() -> list[dict]:
    """List all available backup files."""
    if not BACKUP_DIR.exists():
        return []
    files = []
    for p in sorted(BACKUP_DIR.glob("backup_*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = p.stat()
        files.append({
            "name": p.name,
            "size": st.st_size,
            "created_at": datetime.fromtimestamp(st.st_mtime).isoformat(),
        })
    return files


def restore_backup(name: str) -> dict:
    """Validate a SQLite backup fully, then replace the live DB atomically."""
    safe_name = Path(str(name or "")).name
    if safe_name != name or not safe_name.startswith("backup_") or not safe_name.endswith(".zip"):
        raise ValueError("اسم ملف النسخة غير صالح")
    src_zip = (BACKUP_DIR / safe_name).resolve()
    if src_zip.parent != BACKUP_DIR.resolve() or not src_zip.exists():
        raise ValueError("ملف غير موجود")

    tmp_dir = Path(tempfile.mkdtemp(prefix="pospro_restore_"))
    tmp_db = tmp_dir / "candidate.db"
    try:
        with zipfile.ZipFile(str(src_zip), "r") as zf:
            db_entries = [i for i in zf.infolist() if i.filename.lower().endswith(".db") and not i.is_dir()]
            if len(db_entries) != 1:
                raise ValueError("النسخة يجب أن تحتوي قاعدة بيانات واحدة")
            entry = db_entries[0]
            if entry.file_size <= 0 or entry.file_size > 2 * 1024 * 1024 * 1024:
                raise ValueError("حجم قاعدة البيانات داخل النسخة غير صالح")
            with zf.open(entry) as src, open(tmp_db, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)

        with open(tmp_db, "rb") as fh:
            if fh.read(16) != b"SQLite format 3\x00":
                raise ValueError("الملف المستخرج ليس قاعدة SQLite صالحة")
        conn = sqlite3.connect(str(tmp_db))
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if not result or str(result[0]).lower() != "ok":
                raise ValueError("فشل فحص سلامة قاعدة البيانات")
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {"users", "products", "customers", "invoices"}
            if not required.issubset(tables):
                raise ValueError("قاعدة النسخة لا تحتوي الجداول الأساسية")
        finally:
            conn.close()

        db_path = _sqlite_db_path()
        if db_path is None:
            raise ValueError("مسار قاعدة SQLite غير متاح")
        safety = make_backup()
        if db_path.exists() and not safety:
            raise ValueError("تعذر إنشاء نسخة أمان قبل الاستعادة")
        replace_tmp = db_path.with_suffix(db_path.suffix + ".restore_tmp")
        shutil.copy2(tmp_db, replace_tmp)
        replace_tmp.replace(db_path)
        return {"ok": True, "message": "تمت الاستعادة والتحقق من سلامة قاعدة البيانات. أعد تشغيل التطبيق."}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

