"""S6 PoCs for the backend quality area (G): query counts, tribe standings cost, 500 on odd input."""
import time
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

import app.models as models
from app.db.database import SessionLocal, engine
from app.services import tribes as tribes_service
from server_tests_conftest import CSRF, login_admin, login_student


class Counter:
    def __init__(self):
        self.n = 0

    def __enter__(self):
        event.listen(engine, "before_cursor_execute", self._hit)
        return self

    def __exit__(self, *a):
        event.remove(engine, "before_cursor_execute", self._hit)

    def _hit(self, *args, **kw):
        self.n += 1


@pytest.fixture(autouse=True)
def empty(app):
    s = SessionLocal()
    s.query(models.Association).delete()
    s.commit()
    s.close()
    tribes_service.clear_cache()


def _when(days, hours=2):
    start = datetime.now(timezone.utc) + timedelta(days=days)
    return {"starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=hours)).isoformat()}


def test_events_list_is_n_plus_one_for_a_member(app, fake_eios, db):
    """GET /events for a non-admin issues one is_leader() query per association event (card -> can_manage)."""
    admin = login_admin(app)
    aid = admin.post("/api/v1/admin/associations", json={"name": "Клуб"}, headers=CSRF).json()["id"]
    member = login_student(app, fake_eios, "24-isbo-001", eios_id="1")
    member.post(f"/api/v1/associations/{aid}/apply", json={}, headers=CSRF)
    uid = db.query(models.User).filter_by(username="24-isbo-001").one().id
    admin.put(f"/api/v1/admin/associations/{aid}/leaders/{uid}", headers=CSRF)  # becomes leader, can create events
    counts = {}
    for total in (5, 40):
        have = db.query(models.Event).count()
        for i in range(total - have):
            r = member.post("/api/v1/events", json={"title": f"E{i}", "association_id": aid, **_when(3 + i)}, headers=CSRF)
            assert r.status_code == 201, r.text
        with Counter() as c:
            assert len(member.get("/api/v1/events?view=upcoming").json()) == total
        counts[total] = c.n
    print("SQL statements for GET /events:", counts)
    assert counts[40] - counts[5] >= 30  # grows linearly with the number of events (N+1)


def test_tribe_standings_cost_grows_with_members(app, fake_eios, db):
    """The first GET /tribes/current after the 5-minute cache runs earned_between() per member."""
    admin = login_admin(app)
    for i in range(1, 121):
        add = f"24-isbo-{i:03d}"
        login_student(app, fake_eios, add, eios_id=str(7000 + i), full_name=f"Студент{chr(1040 + i % 30)} Имя Отчество")
    today = date.today()
    t = admin.post("/api/v1/tribes/tournaments", json={"title": "T", "starts_on": (today - timedelta(days=1)).isoformat(),
                   "ends_on": (today + timedelta(days=30)).isoformat(), "tribe_names": ["А", "Б", "В"]}, headers=CSRF).json()
    assert admin.post(f"/api/v1/tribes/tournaments/{t['id']}/start", headers=CSRF).status_code == 200
    tribes_service.clear_cache()
    viewer = TestClient(app)
    viewer.post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-001", "password": "pw"})
    with Counter() as c:
        t0 = time.perf_counter()
        r = viewer.get("/api/v1/tribes/current")
        dt = time.perf_counter() - t0
    assert r.status_code == 200
    print(f"GET /tribes/current (cold cache, 120 members): {c.n} SQL statements, {dt:.2f}s")
    assert c.n > 120 * 5


@pytest.mark.parametrize("stamp", ["0001-01-01T00:00:00+03:00", "9999-12-31T23:59:59-05:00"])
def test_extreme_datetimes_give_500(app, fake_eios, stamp):
    """_utc_or_none() converts with astimezone(): an offset at the edge of the datetime range overflows -> 500."""
    s = login_student(app, fake_eios)
    c = TestClient(app, raise_server_exceptions=False)
    c.cookies = s.cookies
    r = c.post("/api/v1/tasks", json={"title": "x", "due_at": stamp}, headers=CSRF)
    print(stamp, "->", r.status_code)
    assert r.status_code == 500  # documents the bug; a fixed server returns 422
