"""Loopholes closed after the security review: bits farming, backdating, double prizes, flooding."""
from datetime import date, datetime, timedelta, timezone

import pytest

import app.models as models
from app.core.config import settings
from app.db.database import SessionLocal
from app.services import timetable, tribes as tribes_service
from conftest import CSRF, login_admin, login_student


@pytest.fixture(autouse=True)
def empty_catalog(app):
    session = SessionLocal()
    session.query(models.Association).delete()
    session.commit()
    session.close()
    tribes_service.clear_cache()


def _student(app, fake_eios, n, full_name="Студент Тест Тестович"):
    return login_student(app, fake_eios, username=f"24-isbo-{n:03d}", eios_id=str(6000 + n), full_name=full_name)


def _uid(db, n):
    return db.query(models.User).filter_by(username=f"24-isbo-{n:03d}").one().id


def _when(days, hours=2):
    start = datetime.now(timezone.utc) + timedelta(days=days)
    return {"starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=hours)).isoformat()}


@pytest.fixture
def club(app, fake_eios, db):
    admin = login_admin(app)
    aid = admin.post("/api/v1/admin/associations", json={"name": "Медиацентр"}, headers=CSRF).json()["id"]
    leader = _student(app, fake_eios, 1)
    admin.put(f"/api/v1/admin/associations/{aid}/leaders/{_uid(db, 1)}", headers=CSRF)
    member = _student(app, fake_eios, 2)
    member.post(f"/api/v1/associations/{aid}/apply", json={}, headers=CSRF)
    leader.post(f"/api/v1/associations/{aid}/members/{_uid(db, 2)}/decision", json={"approve": True}, headers=CSRF)
    return admin, aid, leader, member


def test_no_bits_for_answering_ones_own_question(app, fake_eios):
    alice = _student(app, fake_eios, 1)
    bob = _student(app, fake_eios, 2)
    q = alice.post("/api/v1/forum/questions", json={"title": "Где Б-108?", "content": "Не могу найти коворкинг"}, headers=CSRF).json()
    own = alice.post(f"/api/v1/forum/questions/{q['id']}/answers", json={"content": "Нашла сама"}, headers=CSRF).json()
    assert alice.post(f"/api/v1/forum/answers/{own['id']}/solution", headers=CSRF).status_code == 400
    assert alice.get("/api/v1/progress").json()["facts"]["answers"] == 0
    # Someone else's answer still counts, and is a solution
    other = bob.post(f"/api/v1/forum/questions/{q['id']}/answers", json={"content": "Первый этаж"}, headers=CSRF).json()
    assert alice.post(f"/api/v1/forum/answers/{other['id']}/solution", headers=CSRF).status_code == 200
    assert bob.get("/api/v1/progress").json()["points"] == 2 + 5


def test_solutions_are_capped_per_semester(app, fake_eios, db):
    from app.services import progress
    f = {k: 0 for k in ("events", "volunteer", "association_events", "meetings", "on_time", "late", "homework", "answers", "organized")}
    f["solutions"] = 40
    assert progress.points(f, capped=True) == progress.CAPS["solution"] * progress.POINTS["solution"]


def test_a_sign_up_alone_brings_no_bits(club, db):
    admin, aid, leader, member = club
    ev = admin.post("/api/v1/events", json={"title": "День ИВИТШ", "scope": "institute", **_when(1)}, headers=CSRF).json()
    member.post(f"/api/v1/events/{ev['id']}/register", json={"role": "participant"}, headers=CSRF)
    row = db.get(models.Event, ev["id"])
    row.starts_at = datetime.now(timezone.utc) - timedelta(hours=3)
    row.ends_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    assert member.get("/api/v1/progress").json()["facts"]["events"] == 0
    admin.put(f"/api/v1/events/{ev['id']}/attendance", json={"user_ids": [_uid(db, 2)]}, headers=CSRF)
    assert member.get("/api/v1/progress").json()["facts"]["events"] == 1


def test_leaders_cannot_backdate_events_and_meetings(club, db):
    admin, aid, leader, member = club
    past = _when(-10)
    r = leader.post("/api/v1/events", json={"title": "Хакатон", "association_id": aid, **past}, headers=CSRF)
    assert r.status_code == 400
    # One just held can be recorded
    assert leader.post("/api/v1/events", json={"title": "Вчера", "association_id": aid, **_when(0, 1)}, headers=CSRF).status_code == 201
    # Nor move a coming one into the past
    ev = leader.post("/api/v1/events", json={"title": "Квиз", "association_id": aid, **_when(3)}, headers=CSRF).json()
    assert leader.put(f"/api/v1/events/{ev['id']}", json={"title": "Квиз", "association_id": aid, **past}, headers=CSRF).status_code == 400
    # The administration can
    assert admin.post("/api/v1/events", json={"title": "Хакатон", "association_id": aid, **past}, headers=CSRF).status_code == 201
    assert leader.post(f"/api/v1/associations/{aid}/meetings", json=past, headers=CSRF).status_code == 400
    assert admin.post(f"/api/v1/associations/{aid}/meetings", json=past, headers=CSRF).status_code == 201


def test_leaders_fix_the_list_within_a_week(club, db):
    admin, aid, leader, member = club
    ev = leader.post("/api/v1/events", json={"title": "Квиз", "association_id": aid, **_when(1)}, headers=CSRF).json()
    row = db.get(models.Event, ev["id"])
    row.starts_at = datetime.now(timezone.utc) - timedelta(days=9)
    row.ends_at = row.starts_at + timedelta(hours=2)
    db.commit()
    body = {"user_ids": [_uid(db, 2)], "role": "participant"}
    assert leader.post(f"/api/v1/events/{ev['id']}/registrations", json=body, headers=CSRF).status_code == 400
    assert leader.put(f"/api/v1/events/{ev['id']}/attendance", json={"user_ids": []}, headers=CSRF).status_code == 400
    assert admin.post(f"/api/v1/events/{ev['id']}/registrations", json=body, headers=CSRF).status_code == 200


def test_finishing_twice_pays_once(app, fake_eios, db):
    admin = login_admin(app)
    for n in range(1, 5):
        _student(app, fake_eios, n)
    today = date.today()
    t = admin.post("/api/v1/tribes/tournaments", json={
        "title": "Турнир", "starts_on": (today - timedelta(days=1)).isoformat(), "ends_on": (today + timedelta(days=5)).isoformat(),
        "tribe_names": ["Альфа", "Бета"]}, headers=CSRF).json()
    assert admin.post(f"/api/v1/tribes/tournaments/{t['id']}/start", headers=CSRF).status_code == 200
    assert admin.post(f"/api/v1/tribes/tournaments/{t['id']}/start", headers=CSRF).status_code == 400
    assert admin.post(f"/api/v1/tribes/tournaments/{t['id']}/finish", headers=CSRF).status_code == 200
    paid = db.query(models.BitsGrant).count()
    assert admin.post(f"/api/v1/tribes/tournaments/{t['id']}/finish", headers=CSRF).status_code == 400
    assert db.query(models.BitsGrant).count() == paid == 4


def test_admins_cannot_grant_bits_to_themselves(app, fake_eios, db):
    admin = login_admin(app)
    me = admin.get("/api/v1/auth/me").json()["id"]
    r = admin.post("/api/v1/bits/grants", json={"user_id": me, "amount": 1000, "reason": "Себе"}, headers=CSRF)
    assert r.status_code == 403
    _student(app, fake_eios, 1)
    assert admin.post("/api/v1/bits/grants", json={"user_id": _uid(db, 1), "amount": 50, "reason": "Приз"}, headers=CSRF).status_code == 201


def test_leaders_cannot_hold_the_room_for_the_semester(club):
    admin, aid, leader, member = club
    day = (timetable.msk_now() + timedelta(days=2)).date()

    def book(d, start="09:00", end="10:00"):
        return leader.post("/api/v1/bookings", json={
            "resource": "room", "zone": "top", "association_id": aid,
            "starts_at": f"{d.isoformat()}T{start}:00+03:00", "ends_at": f"{d.isoformat()}T{end}:00+03:00"}, headers=CSRF)

    assert book(day, "08:00", "20:00").status_code == 400
    for i in range(10):
        assert book(day + timedelta(days=i)).status_code == 201
    assert book(day + timedelta(days=11)).status_code == 409


def test_files_per_item_are_limited(club, monkeypatch):
    admin, aid, leader, member = club
    monkeypatch.setattr(settings, "FILES_PER_ITEM", 2)
    t = member.post("/api/v1/tasks", json={"title": "Эссе"}, headers=CSRF).json()
    pdf = b"%PDF-1.4\n% test\n"
    for _ in range(2):
        assert member.post(f"/api/v1/tasks/{t['id']}/files", params={"name": "a.pdf"}, content=pdf, headers=CSRF).status_code == 201
    assert member.post(f"/api/v1/tasks/{t['id']}/files", params={"name": "a.pdf"}, content=pdf, headers=CSRF).status_code == 400


def test_upload_quota_per_student(club, monkeypatch, db):
    admin, aid, leader, member = club
    monkeypatch.setattr(settings, "USER_UPLOAD_QUOTA_MB", 1)
    t = member.post("/api/v1/tasks", json={"title": "Эссе"}, headers=CSRF).json()
    pdf = b"%PDF-1.4\n% test\n"
    assert member.post(f"/api/v1/tasks/{t['id']}/files", params={"name": "a.pdf"}, content=pdf, headers=CSRF).status_code == 201
    # A megabyte already stored somewhere else
    db.add(models.Attachment(kind="file", title="old.pdf", size=1024 * 1024, uploaded_by_id=_uid(db, 2), task_id=t["id"]))
    db.commit()
    assert member.post(f"/api/v1/tasks/{t['id']}/files", params={"name": "b.pdf"}, content=pdf, headers=CSRF).status_code == 413


def test_posting_is_rate_limited(app, fake_eios):
    alice = _student(app, fake_eios, 1)
    codes = [alice.post("/api/v1/homework", json={"text": f"Задание {i}"}, headers=CSRF).status_code for i in range(31)]
    assert codes[:30] == [201] * 30 and codes[30] == 429
