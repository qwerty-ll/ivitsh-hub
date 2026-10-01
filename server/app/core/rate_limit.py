"""Small in-process sliding-window rate limiter.

State lives in the worker's memory, so limits apply per uvicorn process. That is enough for the
single-worker deployment; nginx adds coarse per-IP flood protection in front of it.
"""
import threading
import time
from collections import deque
from typing import Deque, Dict

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, max_events: int, window_seconds: int, max_keys: int = 50_000):
        self.max_events = max_events
        self.window = window_seconds
        self.max_keys = max_keys
        self._events: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> Deque[float]:
        events = self._events.get(key)
        if events is None:
            return deque()
        while events and events[0] <= now - self.window:
            events.popleft()
        if not events:
            del self._events[key]
        return events

    def is_limited(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, time.monotonic())) >= self.max_events

    def add(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(key, now)
            if len(self._events) >= self.max_keys:
                # Drop the stalest keys instead of growing without bound.
                for stale in sorted(self._events, key=lambda k: self._events[k][-1])[: self.max_keys // 10]:
                    del self._events[stale]
            self._events.setdefault(key, deque()).append(now)

    def hit(self, key: str) -> bool:
        """Record an event and return False when the key is over the limit."""
        with self._lock:
            now = time.monotonic()
            events = self._prune(key, now)
            if len(events) >= self.max_events:
                return False
        self.add(key)
        return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def too_many_requests(detail: str = "Слишком много попыток. Попробуйте через несколько минут.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)


# Failed logins: per account and address (stops password guessing) and per IP (stops spraying many accounts).
# Keyed by the pair, not the login alone: otherwise anyone who knows a login could lock its owner out.
# The per-IP budget is generous because the whole campus Wi-Fi shares one NAT address.
login_failures_by_user = RateLimiter(max_events=5, window_seconds=15 * 60)
login_failures_by_ip = RateLimiter(max_events=300, window_seconds=15 * 60)
admin_login_failures_by_ip = RateLimiter(max_events=10, window_seconds=15 * 60)
chat_requests = RateLimiter(max_events=20, window_seconds=60)
document_requests = RateLimiter(max_events=30, window_seconds=60)
# Forum questions and answers, homework entries, comments: a person does not write more than this
content_posts = RateLimiter(max_events=30, window_seconds=10 * 60)


def login_key(kind: str, username: str, ip: str) -> str:
    return f"{kind}:{username.strip().lower()}|{ip}"


def check_posting(user) -> None:
    if not content_posts.hit(f"user:{user.id}"):
        raise too_many_requests("Слишком много сообщений подряд. Подождите несколько минут.")


def reset_all() -> None:
    for limiter in (login_failures_by_user, login_failures_by_ip, admin_login_failures_by_ip, chat_requests, document_requests, content_posts):
        limiter.clear()
