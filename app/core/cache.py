"""Simple in-memory cache with TTL for POS Pro.

Used for categories, settings, and other rarely-changing data.
"""

from __future__ import annotations

import time
from typing import Any, Optional

_store: dict[str, tuple[float, Any]] = {}
DEFAULT_TTL = 30  # seconds


def get(key: str) -> Optional[Any]:
    entry = _store.get(key)
    if not entry:
        return None
    ts, val = entry
    if time.time() - ts > DEFAULT_TTL:
        del _store[key]
        return None
    return val


def set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    _store[key] = (time.time(), value)


def invalidate(key: str) -> None:
    _store.pop(key, None)
