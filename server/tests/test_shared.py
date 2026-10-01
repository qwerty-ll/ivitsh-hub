"""Several workers: what they must share goes through Redis (here an in-memory fake standing in for it)."""
import asyncio
import os

import fakeredis
import pytest

from app.core import rate_limit, shared
from app.core.config import Settings
from app.services import rag_service
from app.services import tribes as tribes_service
from conftest import CSRF, login_admin, login_student


@pytest.fixture
def redis_mode():
    shared.use(fakeredis.FakeRedis())
    tribes_service.clear_cache()
    yield shared.client()
    rate_limit.reset_all()
    shared.use(None)
    tribes_service.clear_cache()


def test_two_workers_count_one_limit(redis_mode):
    worker_a = rate_limit.RateLimiter("demo", max_events=3, window_seconds=60)
    worker_b = rate_limit.RateLimiter("demo", max_events=3, window_seconds=60)
    assert worker_a.hit("k") and worker_b.hit("k") and worker_a.hit("k")
    assert not worker_b.hit("k") and worker_a.is_limited("k")
    worker_b.reset("k")
    assert not worker_a.is_limited("k")


def test_login_lockout_works_through_redis(app, fake_eios, redis_mode):
    from fastapi.testclient import TestClient
    c = TestClient(app)
    for _ in range(5):
        assert c.post("/api/v1/auth/admin-login", json={"username": "portal_admin", "password": "x"}).status_code == 401
    assert c.post("/api/v1/auth/admin-login", json={"username": "portal_admin", "password": "x"}).status_code == 429
    assert any(k.startswith(b"ivitsh:rl:login_user:") for k in redis_mode.keys())


def test_tribe_snapshot_is_shared_and_dropped_for_every_worker(app, fake_eios, db, redis_mode, monkeypatch):
    from datetime import date, timedelta
    admin = login_admin(app)
    students = [login_student(app, fake_eios, username=f"24-isbo-{i:03d}", eios_id=str(700 + i)) for i in range(1, 5)]
    t = admin.post("/api/v1/tribes/tournaments", json={
        "title": "Турнир", "starts_on": (date.today() - timedelta(days=1)).isoformat(),
        "ends_on": (date.today() + timedelta(days=9)).isoformat(), "tribe_names": ["Альфа", "Бета"]}, headers=CSRF).json()
    admin.post(f"/api/v1/tribes/tournaments/{t['id']}/start", headers=CSRF)
    calls = []
    real = tribes_service._compute
    monkeypatch.setattr(tribes_service, "_compute", lambda *a: calls.append(1) or real(*a))
    # Computed once when the tournament started (on some worker); every worker reads that copy
    students[0].get("/api/v1/tribes/current")
    tribes_service._cache.clear()  # another worker: nothing in its own memory
    students[1].get("/api/v1/tribes/current")
    assert calls == [] and any(k.startswith(b"ivitsh:tribes:") for k in redis_mode.keys())
    # An administrator's change on one worker reaches the others
    tribe = admin.get("/api/v1/tribes/current").json()["tournament"]["tribes"][0]
    r = admin.post(f"/api/v1/tribes/{tribe['id']}/awards", json={"points": 7, "reason": "Хакатон"}, headers=CSRF)
    assert r.status_code == 200
    points = {tr["id"]: tr["points"] for tr in students[2].get("/api/v1/tribes/current").json()["tournament"]["tribes"]}
    assert points[tribe["id"]] == 7


def test_gigachat_streams_are_counted_for_all_workers(redis_mode, monkeypatch):
    monkeypatch.setattr(rag_service.settings, "GIGACHAT_MAX_STREAMS", 1)

    async def scenario():
        held = await rag_service._acquire_stream(1.0)
        with pytest.raises(asyncio.TimeoutError):
            await rag_service._acquire_stream(0.3)  # "another worker" waits in vain
        await rag_service._release_stream(held)
        again = await rag_service._acquire_stream(0.5)
        await rag_service._release_stream(again)

    asyncio.run(scenario())


def test_readiness_reports_redis(app, redis_mode):
    from fastapi.testclient import TestClient
    assert TestClient(app).get("/api/v1/health/ready").status_code == 200


def test_several_workers_need_redis_and_postgresql(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    monkeypatch.setenv("REDIS_URL", "")
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        Settings()
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///x.db")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        Settings()
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/portal")
    assert Settings().WEB_CONCURRENCY == 2
    assert os.environ["WEB_CONCURRENCY"] == "2"
