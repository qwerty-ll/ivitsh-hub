"""S1: output leakage, public (anonymous) surface, group isolation, self-attendance bits.

`*_ok` = protection holds, `*_FINDING` = passes when the weakness is PRESENT.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.models as models
from app.db.database import SessionLocal
from app.services import eios, timetable
from srv_conftest import CSRF, login_admin, login_student


@pytest.fixture(autouse=True)
def empty_catalog(app):
    s = SessionLocal()
    s.query(models.Association).delete()
    s.commit()
    s.close()


def _stu(app, fake_eios, n, name, **kw):
    return login_student(app, fake_eios, username=f"24-isbo-{n:03d}", eios_id=str(7000 + n), full_name=name, **kw)


def _uid(db, n):
    return db.query(models.User).filter_by(username=f"24-isbo-{n:03d}").one().id


def test_forum_exposes_real_names_and_user_ids_to_anonymous_visitors_FINDING(app, fake_eios, db):
    s = _stu(app, fake_eios, 1, "Петрова Анна Сергеевна")
    s.post("/api/v1/forum/questions", json={"title": "Как сдать зачёт", "content": "Подскажите пожалуйста как"}, headers=CSRF)
    anon = TestClient(app)
    qs = anon.get("/api/v1/forum/questions").json()
    assert qs[0]["author_name"] == "Петрова Анна Сергеевна" and qs[0]["author_id"] == _uid(db, 1)
    # internal user ids can be enumerated and used as a filter without signing in
    by_id = anon.get(f"/api/v1/forum/questions?author_id={_uid(db, 1)}").json()
    assert len(by_id) == 1
    q = qs[0]["id"]
    s.post(f"/api/v1/forum/questions/{q}/answers", json={"content": "Вот так"}, headers=CSRF)
    ans = anon.get(f"/api/v1/forum/questions/{q}/answers").json()
    assert ans[0]["author_name"] == "Петрова Анна Сергеевна"
    # any anonymous GET also writes to the DB (views_count) for each hit
    v1 = anon.get(f"/api/v1/forum/questions/{q}").json()["views_count"]
    v2 = anon.get(f"/api/v1/forum/questions/{q}").json()["views_count"]
    assert v2 == v1 + 1


def test_catalog_shows_leader_name_group_and_id_to_anonymous_FINDING(app, fake_eios, db):
    admin = login_admin(app)
    a = admin.post("/api/v1/admin/associations", json={"name": "Alpha club"}, headers=CSRF).json()["id"]
    lead = _stu(app, fake_eios, 1, "Смирнов Макар Олегович", group="24-ИСбо-1")
    lead.patch("/api/v1/auth/me", json={"vk_url": "makar.s", "max_contact": "+79990001122"}, headers=CSRF)
    admin.put(f"/api/v1/admin/associations/{a}/leaders/{_uid(db, 1)}", headers=CSRF)
    anon = TestClient(app).get("/api/v1/associations").json()
    leader = anon[0]["leaders"][0]
    print(leader)
    assert leader["full_name"] == "Смирнов Макар Олегович" and leader["group_number"] == "24-ИСбо-1" and leader["user_id"] == _uid(db, 1)
    assert leader["vk_url"] is None and leader["max_contact"] is None  # contacts are hidden: that part is OK
    signed = _stu(app, fake_eios, 2, "Иванов Иван Иванович").get("/api/v1/associations").json()
    assert signed[0]["leaders"][0]["vk_url"] == "makar.s"  # visible to any signed-in student (accepted design)


def test_no_hidden_fields_in_ordinary_student_responses_ok(app, fake_eios, db):
    """A plain member walks through the read endpoints; no other person's login/EIOS id/contacts/hash may appear."""
    admin = login_admin(app)
    a = admin.post("/api/v1/admin/associations", json={"name": "Alpha club"}, headers=CSRF).json()["id"]
    lead = _stu(app, fake_eios, 1, "Лидер Первый")
    admin.put(f"/api/v1/admin/associations/{a}/leaders/{_uid(db, 1)}", headers=CSRF)
    m = _stu(app, fake_eios, 2, "Участник Второй")
    m.patch("/api/v1/auth/me", json={"vk_url": "member.vk", "max_contact": "max-2"}, headers=CSRF)
    m3 = _stu(app, fake_eios, 3, "Участник Третий")
    m3.patch("/api/v1/auth/me", json={"vk_url": "third.vk", "max_contact": "max-3"}, headers=CSRF)
    for c in (m, m3):
        c.post(f"/api/v1/associations/{a}/apply", json={}, headers=CSRF)
        lead.post(f"/api/v1/associations/{a}/members/{_uid(db, 2 if c is m else 3)}/decision", json={"approve": True}, headers=CSRF)
    t = lead.post("/api/v1/tasks", json={"title": "T", "association_id": a, "to_all": True}, headers=CSRF).json()
    lead.post(f"/api/v1/associations/{a}/posts", json={"title": "P", "to_all": True}, headers=CSRF)
    m3.post("/api/v1/forum/questions", json={"title": "Вопрос про сессию", "content": "Когда будет пересдача?"}, headers=CSRF)
    urls = [
        "/api/v1/associations", f"/api/v1/associations/{a}", "/api/v1/associations/mine", f"/api/v1/associations/{a}/posts",
        f"/api/v1/tasks/{t['id']}", "/api/v1/tasks/my", f"/api/v1/associations/{a}/meetings", "/api/v1/forum/questions",
        "/api/v1/calendar?start=2026-10-01&days=7", "/api/v1/progress", "/api/v1/auth/me", "/api/v1/homework",
    ]
    blob = ""
    for u in urls:
        r = m.get(u)
        assert r.status_code == 200, (u, r.status_code)
        blob += json.dumps(r.json(), ensure_ascii=False)
    for secret in ("third.vk", "max-3", "hashed_password", "7003", "7001", "24-isbo-003", "24-isbo-001", "sdo_id", "pd_consent"):
        assert secret not in blob, secret
    # the member's own record exposes only own fields
    me = m.get("/api/v1/auth/me").json()
    assert set(me) == {"id", "username", "full_name", "role", "group_number", "eios_group_id", "email", "userpictureurl",
                       "auth_source", "is_blocked", "vk_url", "max_contact", "created_at"}
    # the leader (manager) sees contacts of members: accepted design; a plain member does not see them
    mem = lead.get(f"/api/v1/associations/{a}").json()
    assert {x["vk_url"] for x in mem["members"]} >= {"member.vk", "third.vk"}
    assert m.get(f"/api/v1/associations/{a}").json()["members"] == []


def test_schedule_is_an_open_unauthenticated_proxy_to_eios_FINDING(app, monkeypatch):
    """/api/v1/schedule/* needs no login, has no rate limit and accepts arbitrary ids/dates: every distinct query is a
    fresh upstream EIOS call, and a few thousand distinct keys flush the shared cache incl. the 24 h stale fallback."""
    upstream = []
    state = {"up": True}

    async def fetch_json(endpoint, params, timeout=5.0):
        upstream.append((endpoint, dict(params)))
        return {"state": 1, "data": [{"id": 1, "name": "G"}]} if state["up"] else None

    monkeypatch.setattr(eios, "fetch_json", fetch_json)
    monkeypatch.setattr(timetable, "_MAX_CACHE_ENTRIES", 50)  # real value: 2000 (same behaviour, more requests)
    anon = TestClient(app)
    assert anon.get("/api/v1/schedule/groups?year=2026-2027").status_code == 200  # a legit hot entry
    for i in range(1, 121):  # 120 distinct anonymous queries
        assert anon.get(f"/api/v1/schedule/rasp?idGroup={i}&year=2026-2027&sdate=2026-10-{(i % 28) + 1:02d}").status_code == 200
    assert len(upstream) == 121  # not one of them was served from cache or refused
    state["up"] = False  # EIOS goes down: the stale copy should save the day, but it was evicted
    r = anon.get("/api/v1/schedule/groups?year=2026-2027")
    assert r.status_code == 503


def test_leader_marks_himself_and_friends_present_for_bits_FINDING(app, fake_eios, db):
    """A leader can create meetings 'now', mark himself and anyone in the association as present - no confirmation by the
    attendees, no minimum people, no overlap check: 3 bits per meeting up to the cap of 12 per semester (36 bits)."""
    admin = login_admin(app)
    a = admin.post("/api/v1/admin/associations", json={"name": "Alpha club"}, headers=CSRF).json()["id"]
    lead = _stu(app, fake_eios, 1, "Лидер Первый")
    admin.put(f"/api/v1/admin/associations/{a}/leaders/{_uid(db, 1)}", headers=CSRF)
    friend = _stu(app, fake_eios, 2, "Друг Второй")
    friend.post(f"/api/v1/associations/{a}/apply", json={}, headers=CSRF)
    lead.post(f"/api/v1/associations/{a}/members/{_uid(db, 2)}/decision", json={"approve": True}, headers=CSRF)
    before = lead.get("/api/v1/progress").json()["points"]
    start = datetime.now(timezone.utc) - timedelta(minutes=30)
    for i in range(15):
        m = lead.post(f"/api/v1/associations/{a}/meetings", json={
            "title": f"Sync {i}", "starts_at": start.isoformat(), "ends_at": (start + timedelta(minutes=10)).isoformat()}, headers=CSRF)
        assert m.status_code == 201, m.text
        r = lead.put(f"/api/v1/meetings/{m.json()['id']}/attendance", json={"user_ids": [_uid(db, 1), _uid(db, 2)]}, headers=CSRF)
        assert r.status_code == 200, r.text
    lp, fp = lead.get("/api/v1/progress").json(), friend.get("/api/v1/progress").json()
    print("leader:", lp["points"] - before, "friend:", fp["points"], lp["facts"]["meetings"])
    assert lp["points"] - before >= 36 and fp["points"] >= 36  # 12 capped meetings x 3 bits, both of them
    assert lp["balance"]["available"] >= 36  # spendable in the shop


def test_group_can_be_claimed_by_hand_without_eios_group_id_FINDING(app, fake_eios, db):
    """If EIOS did not return the group id, /auth/me PATCH sets any group: its homework becomes readable/writable."""
    owner = _stu(app, fake_eios, 1, "Староста Первый", group="24-ИСбо-1", group_id=4242)
    owner.post("/api/v1/homework", json={"subject": "Базы данных", "text": "Лаба 3 до пятницы"}, headers=CSRF)
    # a student whose EIOS answer carried no group id
    other = _stu(app, fake_eios, 2, "Чужой Второй", group="23-ИСбо-2")
    assert other.get("/api/v1/homework").json() == []
    r = other.patch("/api/v1/auth/me", json={"group_number": "24-ИСбо-1"}, headers=CSRF)
    assert r.status_code == 200
    rows = other.get("/api/v1/homework").json()
    assert [x["text"] for x in rows] == ["Лаба 3 до пятницы"]
    assert other.post("/api/v1/homework", json={"text": "spam"}, headers=CSRF).status_code == 201
    # the confirmed group (with group id) is protected: the owner cannot do the same
    assert owner.patch("/api/v1/auth/me", json={"group_number": "23-ИСбо-2"}, headers=CSRF).status_code == 400
