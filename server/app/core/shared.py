"""State the backend workers share: rate limits, the tribes snapshot, GigaChat's free streams.

With REDIS_URL set (several uvicorn workers, WEB_CONCURRENCY > 1) it lives in Redis, so every worker sees the
same counters. Without it (one worker, development, tests) each piece keeps its state in this process's memory.
"""
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("ivitsh_portal.shared")

PREFIX = "ivitsh:"
_client = None
_ready = False


def client():
    """The Redis connection, or None when the portal runs without Redis."""
    global _client, _ready
    if not _ready:
        if settings.REDIS_URL:
            import redis

            _client = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2, socket_connect_timeout=2,
                                           health_check_interval=30)
        _ready = True
    return _client


def use(redis_client) -> None:
    """Replaces the connection (tests use an in-memory fake; None goes back to process memory)."""
    global _client, _ready
    _client, _ready = redis_client, True


def key(*parts) -> str:
    return PREFIX + ":".join(str(p) for p in parts)


def check() -> Optional[str]:
    """None when shared state works, else what is wrong (for the readiness probe)."""
    r = client()
    if r is None:
        return None
    try:
        r.ping()
        return None
    except Exception as e:  # noqa: BLE001 - any connection problem means "not ready"
        return type(e).__name__
