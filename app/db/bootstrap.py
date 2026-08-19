"""Database migrations, indexes, and bootstrap logic."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import IS_SQLITE, DB_PATH, DATA_DIR, BACKUP_DIR, LEGACY_DB_PATH, LEGACY_DATA_DIR
from app.db.session import Base, SessionLocal, engine

log = logging.getLogger("pospro.db")


def _table_has_column(table_name: str, column_name: str) -> bool:
    try:
        insp = inspect(engine)
        cols = [c["name"] for c in insp.get_columns(table_name)]
        return column_name in cols
    except Exception:
        return False


def _table_exists(table_name: str) -> bool:
    try:
        insp = inspect(engine)
        return table_name in insp.get_table_names()
    except Exception:
        return False


def _auto_migrate():
    Base.metadata.create_all(bind=engine)
    migrations = []
    if not _table_exists("app_counters"):
        migrations.append("CREATE TABLE app_counters (name VARCHAR(80) PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0)")
    if _table_exists("users"):
        if not _table_has_column("users", "token_version"):
            migrations.append("ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 0 NOT NULL")
        user_columns = [
            ("permissions", "ALTER TABLE users ADD COLUMN permissions " + ("TEXT" if engine.dialect.name == "sqlite" else "JSON")),
            ("expires_at", "ALTER TABLE users ADD COLUMN expires_at TIMESTAMP"),
            ("is_owner", f"ALTER TABLE users ADD COLUMN is_owner BOOLEAN DEFAULT {'0' if engine.dialect.name == 'sqlite' else 'FALSE'} NOT NULL"),
        ]
        for col_name, sql in user_columns:
            if not _table_has_column("users", col_name): migrations.append(sql)
    if _table_exists("settings"):
        for col_name, sql in [
            ("auto_print_after_sale", f"ALTER TABLE settings ADD COLUMN auto_print_after_sale BOOLEAN DEFAULT {'0' if engine.dialect.name == 'sqlite' else 'FALSE'}"),
            ("vat_enabled", f"ALTER TABLE settings ADD COLUMN vat_enabled BOOLEAN DEFAULT {'0' if engine.dialect.name == 'sqlite' else 'FALSE'}"),
            ("theme", "ALTER TABLE settings ADD COLUMN theme VARCHAR(20) DEFAULT 'light'"),
            ("cached_at", "ALTER TABLE settings ADD COLUMN cached_at TIMESTAMP"),
            ("tagline", "ALTER TABLE settings ADD COLUMN tagline VARCHAR(200) DEFAULT ''"),
            ("slogan", "ALTER TABLE settings ADD COLUMN slogan VARCHAR(200) DEFAULT ''"),
            ("custom_lines", "ALTER TABLE settings ADD COLUMN custom_lines TEXT DEFAULT ''"),
            ("invoice_format", "ALTER TABLE settings ADD COLUMN invoice_format VARCHAR(20) DEFAULT 'a4'"),
            ("header_note", "ALTER TABLE settings ADD COLUMN header_note VARCHAR(200) DEFAULT ''"),
            ("terms_conditions", "ALTER TABLE settings ADD COLUMN terms_conditions TEXT DEFAULT ''"),
            ("warranty_text", "ALTER TABLE settings ADD COLUMN warranty_text VARCHAR(300) DEFAULT ''"),
            ("max_items_per_page", "ALTER TABLE settings ADD COLUMN max_items_per_page INTEGER DEFAULT 15"),
            ("feature_reports_enabled", f"ALTER TABLE settings ADD COLUMN feature_reports_enabled BOOLEAN DEFAULT {'1' if engine.dialect.name == 'sqlite' else 'TRUE'} NOT NULL"),
            ("feature_suppliers_enabled", f"ALTER TABLE settings ADD COLUMN feature_suppliers_enabled BOOLEAN DEFAULT {'1' if engine.dialect.name == 'sqlite' else 'TRUE'} NOT NULL"),
        ]:
            if not _table_has_column("settings", col_name): migrations.append(sql)
    if _table_exists("products"):
        for col_name, sql in [
            ("supplier_id", "ALTER TABLE products ADD COLUMN supplier_id INTEGER REFERENCES suppliers(id) ON DELETE SET NULL"),
            ("min_stock", "ALTER TABLE products ADD COLUMN min_stock NUMERIC(12, 3) DEFAULT 5"),
        ]:
            if not _table_has_column("products", col_name): migrations.append(sql)
    if _table_exists("invoices"):
        for col_name, sql in [
            ("notes", "ALTER TABLE invoices ADD COLUMN notes TEXT"),
            ("invoice_number", "ALTER TABLE invoices ADD COLUMN invoice_number VARCHAR(50)"),
            ("customer_phone", "ALTER TABLE invoices ADD COLUMN customer_phone VARCHAR(40)"),
            ("original_invoice_id", "ALTER TABLE invoices ADD COLUMN original_invoice_id INTEGER REFERENCES invoices(id) ON DELETE SET NULL"),
            ("parent_number", "ALTER TABLE invoices ADD COLUMN parent_number VARCHAR(50)"),
            ("combined_source_ids", "ALTER TABLE invoices ADD COLUMN combined_source_ids TEXT"),
            ("combined_options", "ALTER TABLE invoices ADD COLUMN combined_options TEXT"),
        ]:
            if not _table_has_column("invoices", col_name): migrations.append(sql)
    try:
        insp = inspect(engine)
        if _table_exists("invoices"):
            existing_indexes = {ix["name"] for ix in insp.get_indexes("invoices")}
            if "uq_invoices_number" not in existing_indexes: migrations.append("CREATE UNIQUE INDEX uq_invoices_number ON invoices(number)")
            if "uq_invoices_invoice_number" not in existing_indexes and _table_has_column("invoices", "invoice_number"):
                migrations.append("CREATE UNIQUE INDEX uq_invoices_invoice_number ON invoices(invoice_number)")
    except Exception:
        pass
    if migrations:
        with engine.begin() as conn:
            for sql in migrations:
                try:
                    conn.exec_driver_sql(sql); log.info("Migration applied: %s...", sql[:60])
                except Exception as e:
                    log.exception("Critical migration failed: %s", sql); raise RuntimeError(f"Database migration failed: {sql[:80]}") from e


_SQLITE_PERFORMANCE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_products_name_nocase ON products(name COLLATE NOCASE)",
    "CREATE INDEX IF NOT EXISTS idx_products_barcode_nocase ON products(barcode COLLATE NOCASE)",
    "CREATE INDEX IF NOT EXISTS idx_products_code_nocase ON products(code COLLATE NOCASE)",
    "CREATE INDEX IF NOT EXISTS idx_customers_name_nocase ON customers(name COLLATE NOCASE)",
    "CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone)",
    "CREATE INDEX IF NOT EXISTS idx_invoices_number_desc ON invoices(number DESC)",
    "CREATE INDEX IF NOT EXISTS idx_invoices_invoice_number_nocase ON invoices(invoice_number COLLATE NOCASE)",
    "CREATE INDEX IF NOT EXISTS idx_audit_created_at_desc ON audit_log(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_suppliers_name_nocase ON suppliers(name COLLATE NOCASE)",
)
_POSTGRES_PERFORMANCE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_products_name_lower ON products(lower(name))",
    "CREATE INDEX IF NOT EXISTS idx_products_barcode_lower ON products(lower(barcode))",
    "CREATE INDEX IF NOT EXISTS idx_products_code_lower ON products(lower(code))",
    "CREATE INDEX IF NOT EXISTS idx_customers_name_lower ON customers(lower(name))",
    "CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone)",
    "CREATE INDEX IF NOT EXISTS idx_invoices_number_desc ON invoices(number DESC)",
    "CREATE INDEX IF NOT EXISTS idx_invoices_invoice_number_lower ON invoices(lower(invoice_number))",
    "CREATE INDEX IF NOT EXISTS idx_audit_created_at_desc ON audit_log(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_suppliers_name_lower ON suppliers(lower(name))",
)


def _apply_performance_indexes():
    indexes = _SQLITE_PERFORMANCE_INDEXES if engine.dialect.name == "sqlite" else _POSTGRES_PERFORMANCE_INDEXES
    try:
        with engine.begin() as conn:
            for sql in indexes:
                try: conn.exec_driver_sql(sql)
                except SQLAlchemyError as exc: log.warning("Performance index skipped: %s -> %s", sql[:60], exc)
    except SQLAlchemyError as exc:
        log.warning("Performance index creation failed: %s", exc)


def _enforce_barcode_uniqueness():
    try:
        with engine.begin() as conn:
            dupes = conn.exec_driver_sql("SELECT code, COUNT(*) AS n FROM products WHERE code IS NOT NULL AND code != '' GROUP BY code HAVING COUNT(*) > 1").fetchall()
            if dupes:
                examples = ", ".join(str(row[0]) for row in dupes[:10]); raise RuntimeError(f"Duplicate product codes must be resolved before startup: {examples}")
            conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_products_barcode ON products(barcode) WHERE barcode IS NOT NULL AND barcode != ''")
            conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_products_code ON products(code) WHERE code IS NOT NULL AND code != ''")
    except SQLAlchemyError as exc:
        log.warning("Barcode unique index creation skipped: %s", exc)


def _ensure_runtime_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True); BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if LEGACY_DATA_DIR.exists() and LEGACY_DB_PATH.exists() and not DB_PATH.exists():
        try:
            import shutil
            shutil.copy2(str(LEGACY_DB_PATH), str(DB_PATH)); log.info("Migrated database from %s to %s", LEGACY_DB_PATH, DB_PATH)
            for fname in ("secret.key", "rate_limits.json"):
                legacy = LEGACY_DATA_DIR / fname
                if legacy.exists():
                    dest = DATA_DIR / fname
                    if not dest.exists(): shutil.copy2(str(legacy), str(dest)); log.info("Migrated %s to runtime directory", fname)
        except Exception as e:
            log.warning("Legacy data migration failed: %s", e)


def _legacy_bundled_logo() -> str:
    """Read the historical bundled logo only so old installs can be cleaned."""
    path = Path(__file__).resolve().parent.parent.parent / "static" / "assets" / "logo.png"
    if not path.exists(): return ""
    try:
        import base64
        return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception:
        return ""


def _init_db_unlocked():
    from app.core.security import hash_password
    from app.db.models import Setting, User
    _ensure_runtime_dirs(); _auto_migrate(); _enforce_barcode_uniqueness(); _apply_performance_indexes()
    if IS_SQLITE:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL"); conn.exec_driver_sql("PRAGMA synchronous=NORMAL"); conn.exec_driver_sql("PRAGMA foreign_keys=ON"); conn.exec_driver_sql("PRAGMA temp_store=MEMORY"); conn.exec_driver_sql("PRAGMA cache_size=-64000"); conn.exec_driver_sql("PRAGMA optimize")
    db = SessionLocal()
    try:
        legacy_logo = _legacy_bundled_logo()
        s = db.query(Setting).first()
        if not s:
            s = Setting(id=1, store_name="POS", branch="", phone="", address="", currency="ج.م", tax_rate=0, vat_enabled=False, footer="شكراً لك على ثقتك", copies=1, logo="", header_position="top", quick_qty="1,5,10,20,30,50,100", printer_type="browser", auto_print_after_sale=False, theme="light", tagline="", slogan="", custom_lines="", invoice_format="a4", header_note="", terms_conditions="", warranty_text="", max_items_per_page=15)
            db.add(s)
        else:
            # Permanently remove only the known historical demo branding. Never
            # touch branding that the owner uploaded/typed themselves.
            if (s.store_name or "").strip() in {"صالح الأسناوي", "صالح الأستاذ", ""}: s.store_name = "POS"
            if (s.tagline or "").strip() in {"لتوريد وتركيب أدوات صحية", "توريد وتركيب أدوات صحية"}: s.tagline = ""
            if (s.slogan or "").strip() in {"أبو خليفة", "ابو خلفية"}: s.slogan = ""
            if (s.branch or "").strip() in {"أبو خليفة", "ابو خلفية"}: s.branch = ""
            if legacy_logo and s.logo == legacy_logo: s.logo = ""
            if not s.footer: s.footer = "شكراً لك على ثقتك"
        db.commit()

        if not db.query(User).first():
            from app.core.config import POS_ADMIN_PASSWORD, POS_ADMIN_LOGIN, POS_ADMIN_NAME
            admin_password = POS_ADMIN_PASSWORD
            if not admin_password: raise RuntimeError("POS_ADMIN_PASSWORD must be set before first startup")
            if len(admin_password) < 12: raise RuntimeError("POS_ADMIN_PASSWORD must be at least 12 characters")
            db.add(User(name=POS_ADMIN_NAME, login=POS_ADMIN_LOGIN, password_hash=hash_password(admin_password), role="admin", is_owner=True))
        if not db.query(User).filter(User.is_owner.is_(True)).first():
            first_admin = db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()
            if first_admin: first_admin.is_owner = True
        db.commit()
    finally:
        db.close()


def init_db():
    if engine.dialect.name != "postgresql": return _init_db_unlocked()
    with engine.connect() as lock_conn:
        lock_conn.exec_driver_sql("SELECT pg_advisory_lock(hashtext('pospro_init_db'))")
        try: return _init_db_unlocked()
        finally:
            try: lock_conn.exec_driver_sql("SELECT pg_advisory_unlock(hashtext('pospro_init_db'))")
            except Exception: log.exception("Failed to release POS Pro init advisory lock")
