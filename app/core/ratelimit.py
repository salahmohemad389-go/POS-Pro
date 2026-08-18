"""Rate limiting for local and horizontally-scaled deployments.

SQLite development uses a small file lock. PostgreSQL production stores the
bucket in the database and uses a transaction-scoped advisory lock, so all
Vercel/server instances share the same limiter without Redis or local disk.
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.core.config import DATA_DIR, IS_SQLITE

RATE_FILE = DATA_DIR / "rate_limits.json"
LOCK_FILE = DATA_DIR / "rate_limits.lock"
RATE_LIMITS = {
    "login": {"max": 5, "window": 5, "lock": 5},
    "write": {"max": 60, "window": 1, "lock": 1},
    "delete": {"max": 15, "window": 1, "lock": 1},
    "export": {"max": 15, "window": 5, "lock": 2},
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@contextmanager
def _exclusive_lock(timeout: float = 2.0):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    fd = None
    while fd is None:
        try:
            fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}\n".encode("ascii", "ignore"))
        except FileExistsError:
            try:
                if time.time() - LOCK_FILE.stat().st_mtime > 10:
                    LOCK_FILE.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("rate-limit lock timeout")
            time.sleep(0.02)
    try:
        yield
    finally:
        try:
            os.close(fd)
        finally:
            LOCK_FILE.unlink(missing_ok=True)


def _load_file() -> dict:
    try:
        if RATE_FILE.exists():
            raw = json.loads(RATE_FILE.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return {}


def _save_file(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = _now() - timedelta(hours=1)
    cleaned = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        attempts = [t for t in value.get("attempts", []) if isinstance(t, str) and t > cutoff.isoformat()]
        locked_until = value.get("locked_until")
        if attempts or locked_until:
            cleaned[key] = {"attempts": attempts, "locked_until": locked_until}
    tmp = RATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cleaned, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, RATE_FILE)


def _consume_file(key: str, cfg: dict) -> tuple[bool, int]:
    with _exclusive_lock():
        data = _load_file()
        now = _now()
        entry = data.get(key, {"attempts": [], "locked_until": None})
        if not isinstance(entry, dict):
            entry = {"attempts": [], "locked_until": None}
        locked_until = entry.get("locked_until")
        if locked_until:
            try:
                until = datetime.fromisoformat(locked_until)
                if now < until:
                    return False, max(1, int((until - now).total_seconds()))
            except (TypeError, ValueError):
                pass
            entry = {"attempts": [], "locked_until": None}
        window_start = now - timedelta(minutes=cfg["window"])
        attempts = [t for t in entry.get("attempts", []) if isinstance(t, str) and t > window_start.isoformat()]
        attempts.append(now.isoformat())
        if len(attempts) > cfg["max"]:
            until = now + timedelta(minutes=cfg["lock"])
            data[key] = {"attempts": attempts, "locked_until": until.isoformat()}
            _save_file(data)
            return False, int(cfg["lock"] * 60)
        data[key] = {"attempts": attempts, "locked_until": None}
        _save_file(data)
        return True, 0


def _consume_db(key: str, cfg: dict) -> tuple[bool, int]:
    from app.db.session import SessionLocal
    from app.db.models import RateLimitBucket
    db = SessionLocal()
    try:
        # PostgreSQL advisory lock serializes the bucket across processes/instances.
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})
        now = _now()
        row = db.query(RateLimitBucket).filter(RateLimitBucket.key == key).first()
        if row is None:
            row = RateLimitBucket(key=key, attempts=[], locked_until=None)
            db.add(row)
            db.flush()
        if row.locked_until and now < row.locked_until:
            remaining = max(1, int((row.locked_until - now).total_seconds()))
            db.commit()
            return False, remaining
        window_start = now - timedelta(minutes=cfg["window"])
        attempts = []
        for raw in (row.attempts or []):
            try:
                dt = datetime.fromisoformat(raw) if isinstance(raw, str) else None
            except ValueError:
                dt = None
            if dt and dt > window_start:
                attempts.append(raw)
        attempts.append(now.isoformat())
        if len(attempts) > cfg["max"]:
            row.attempts = attempts
            row.locked_until = now + timedelta(minutes=cfg["lock"])
            db.commit()
            return False, int(cfg["lock"] * 60)
        row.attempts = attempts
        row.locked_until = None
        db.commit()
        return True, 0
    except Exception:
        db.rollback()
        # Fail closed for authentication, fail open for operational writes to avoid
        # a limiter outage taking down the POS. The caller type decides below.
        if cfg is RATE_LIMITS["login"]:
            return False, 60
        return True, 0
    finally:
        db.close()


def consume_attempt(key: str, limit_type: str = "login") -> tuple[bool, int]:
    cfg = RATE_LIMITS.get(limit_type, RATE_LIMITS["login"])
    return _consume_file(key, cfg) if IS_SQLITE else _consume_db(key, cfg)


def record_success(key: str) -> None:
    if IS_SQLITE:
        with _exclusive_lock():
            data = _load_file()
            if key in data:
                del data[key]
                _save_file(data)
        return
    from app.db.session import SessionLocal
    from app.db.models import RateLimitBucket
    db = SessionLocal()
    try:
        db.query(RateLimitBucket).filter(RateLimitBucket.key == key).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def check_rate_limit(key: str, limit_type: str = "login") -> bool:
    # Compatibility only. New code should consume atomically.
    allowed, _ = consume_attempt(key, limit_type)
    return allowed


def record_attempt(key: str, limit_type: str = "login") -> None:
    consume_attempt(key, limit_type)


def get_remaining_lock_seconds(key: str) -> int:
    if IS_SQLITE:
        with _exclusive_lock():
            data = _load_file()
            entry = data.get(key, {})
            raw = entry.get("locked_until") if isinstance(entry, dict) else None
            if not raw:
                return 0
            try:
                return max(0, int((datetime.fromisoformat(raw) - _now()).total_seconds()))
            except (TypeError, ValueError):
                return 0
    from app.db.session import SessionLocal
    from app.db.models import RateLimitBucket
    db = SessionLocal()
    try:
        row = db.query(RateLimitBucket).filter(RateLimitBucket.key == key).first()
        return max(0, int((row.locked_until - _now()).total_seconds())) if row and row.locked_until else 0
    finally:
        db.close()
