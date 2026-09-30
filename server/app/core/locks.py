"""Check-then-write sections that must not interleave (stock and balance, booked time).

One lock per key in the process (the portal runs one worker), plus a transaction-level advisory lock
on PostgreSQL, released at commit or rollback.
"""
import threading
from contextlib import contextmanager
from typing import Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

_locks: Dict[int, threading.Lock] = {}
_guard = threading.Lock()


@contextmanager
def serialized(db: Session, key: int):
    with _guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
        yield
