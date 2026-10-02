"""R3: re-derive bit-farming numbers through the real API with fake-EIOS logins (different order than S3 PoC)."""
from datetime import datetime, timedelta, timezone
from conftest import login_student, login_admin, CSRF
import app.models as models
from app.services import progress


def uid(db, n):
    return db.query(models.User).filter_by(username=f"24-isbo-{n:03d}").one().id


def mk(app, fe, n):
    return login_student(app, fe, f"24-isbo-{n:03d}", eios_id=str(100 + n), full_name=f"Студент{n} Тестов", group="24-ИСбо-1")


def test_derive(app, fake_eios, db):
    admin = login_admin(app)
    L, f1, f2, f3, asker = (mk(app, fake_eios, i) for i in range(1, 6))
    aid = admin.post("/api/v1/admin/associations", json={"name": "Кружок R3"}, headers=CSRF).json()["id"]
    admin.put(f"/api/v1/admin/associations/{aid}/leaders/{uid(db, 1)}", headers=CSRF)
    for c in (f1, f2, f3):
        assert c.post(f"/api/v1/associations/{aid}/apply", json={}, headers=CSRF).status_code in (200, 201)
    for n in (2, 3, 4):
        r = L.post(f"/api/v1/associations/{aid}/members/{uid(db, n)}/decision", json={"approve": True}, headers=CSRF)
        print("approve", n, r.status_code, r.text[:80])
    ids = [uid(db, n) for n in (1, 2, 3, 4)]
    now = datetime.now(timezone.utc)
    iso = lambda d: d.isoformat()
    # 14 meetings (cap is 12) started a minute ago, leader marks everybody including himself
    ok = 0
    for i in range(14):
        m = L.post(f"/api/v1/associations/{aid}/meetings", json={"title": f"Сбор {i}", "starts_at": iso(now - timedelta(minutes=1)), "ends_at": iso(now + timedelta(minutes=5))}, headers=CSRF)
        assert m.status_code == 201, m.text
        ok += L.put(f"/api/v1/meetings/{m.json()['id']}/attendance", json={"user_ids": ids}, headers=CSRF).status_code == 200
    # 10 association events (cap is 8), starting 23h ago (inside LEADER_BACKDATE=1 day)
    for i in range(10):
        e = L.post("/api/v1/events", json={"title": f"Событие {i}", "scope": "association", "association_id": aid,
                   "starts_at": iso(now - timedelta(hours=23)), "ends_at": iso(now - timedelta(hours=22))}, headers=CSRF)
        assert e.status_code == 201, e.text
        eid = e.json()["id"]
        assert L.post(f"/api/v1/events/{eid}/registrations", json={"user_ids": ids, "role": "participant"}, headers=CSRF).status_code == 200
        assert L.put(f"/api/v1/events/{eid}/attendance", json={"user_ids": ids}, headers=CSRF).status_code == 200
    # what about older than 1 day?
    r = L.post("/api/v1/events", json={"title": "Давно", "scope": "association", "association_id": aid,
               "starts_at": iso(now - timedelta(days=2)), "ends_at": iso(now - timedelta(days=2) + timedelta(hours=1))}, headers=CSRF)
    print("backdate 2 days ->", r.status_code, r.json().get("detail"))
    for name, c in (("leader", L), ("friend", f1)):
        p = c.get("/api/v1/progress").json()
        print(name, "points", p["points"], "semester", p["semester_points"], "facts", {k: v for k, v in p["facts"].items() if v})
    print("meetings ok", ok, "caps", progress.CAPS)
