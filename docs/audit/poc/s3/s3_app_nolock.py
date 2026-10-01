"""The app with the PostgreSQL advisory lock removed from core.locks (only the in-process lock stays).
Used by the PoCs to show what the advisory lock is worth when there is more than one worker."""
import threading
from contextlib import contextmanager

import main
from app.core import locks

_mine = {}


@contextmanager
def _process_only(db, key):
    lock = _mine.setdefault(key, threading.Lock())
    with lock:
        yield


locks.serialized = _process_only
app = main.app
