"""Findings of the independent audit of 2026-10-01 (docs/AUDIT_2026-10-01.md) stay fixed."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.models as models
from app.db.database import SessionLocal
from conftest import CSRF, add_eios_account, login_admin, login_student

ADMIN = {"username": "portal_admin", "password": "Adm1n-Test-Password!"}


@pytest.fixture(autouse=True)
def empty_catalog(app):
    session = SessionLocal()
    session.query(models.Association).delete()
    session.commit()
    session.close()


def _from(app, ip):
    return TestClient(app, client=(ip, 50000))


def _uid(db, username):
    return db.query(models.User).filter_by(username=username).one().id


# --- B1: someone else's failed attempts must not lock an account out ---

def test_failed_admin_logins_from_elsewhere_do_not_lock_the_admin_out(app):
    attacker = _from(app, "10.0.0.66")
    codes = [attacker.post("/api/v1/auth/admin-login", json={**ADMIN, "password": "wrong"}).status_code for _ in range(7)]
    assert codes == [401] * 5 + [429] * 2
    # The attacker's own address stays locked, even with the right password
    assert attacker.post("/api/v1/auth/admin-login", json=ADMIN).status_code == 429
    assert _from(app, "10.0.0.1").post("/api/v1/auth/admin-login", json=ADMIN).status_code == 200


def test_failed_eios_logins_from_elsewhere_do_not_lock_the_student_out(app, fake_eios):
    add_eios_account(fake_eios, "24-isbo-002", password="right")
    attacker = _from(app, "10.0.0.66")
    for _ in range(5):
        attacker.post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-002", "password": "bad"})
    body = {"consent": True, "username": "24-isbo-002", "password": "right"}
    assert attacker.post("/api/v1/auth/eios-login", json=body).status_code == 429
    assert _from(app, "10.0.0.2").post("/api/v1/auth/eios-login", json=body).status_code == 200


# --- B2: impossible numbers are 404 / 400, never 500 ---

@pytest.mark.parametrize("path", [
    "/api/v1/events/1180591620717411303424",
    "/api/v1/events/99999999999",
    "/api/v1/tasks/2147483648",
    "/api/v1/forum/questions/1180591620717411303424",
])
def test_huge_ids_in_the_path_are_not_found(app, fake_eios, path):
    student = login_student(app, fake_eios)
    assert student.get(path).status_code == 404


def test_huge_numbers_in_a_query_are_rejected_cleanly(app):
    r = TestClient(app, raise_server_exceptions=False).get("/api/v1/forum/questions", params={"offset": 2 ** 70})
    assert r.status_code == 400


# --- B3: the users tab sees everybody, with search, filters and a real total ---

def test_admin_user_list_has_a_total_filters_and_sorting(app, fake_eios, db):
    admin = login_admin(app)
    login_student(app, fake_eios, "24-isbo-001", eios_id="1", full_name="Яковлев Юрий", group="24-ИСбо-1")
    login_student(app, fake_eios, "24-isbo-002", eios_id="2", full_name="Андреева Анна", group="25-ИБбо-1")
    login_student(app, fake_eios, "24-isbo-003", eios_id="3", full_name="Борисов Борис", group="24-ИСбо-1")
    admin.patch(f"/api/v1/admin/users/{_uid(db, '24-isbo-003')}/block", json={"blocked": True}, headers=CSRF)

    r = admin.get("/api/v1/admin/users", params={"limit": 2})
    assert r.headers["X-Total-Count"] == "4" and len(r.json()) == 2
    r = admin.get("/api/v1/admin/users", params={"limit": 2, "offset": 2})
    assert len(r.json()) == 2

    names = [u["full_name"] for u in admin.get("/api/v1/admin/users", params={"role": "student", "sort": "name"}).json()]
    assert names == ["Андреева Анна", "Борисов Борис", "Яковлев Юрий"]
    r = admin.get("/api/v1/admin/users", params={"q": "ИСБО", "state": "active"})
    assert [u["full_name"] for u in r.json()] == ["Яковлев Юрий"] and r.headers["X-Total-Count"] == "1"
    assert [u["full_name"] for u in admin.get("/api/v1/admin/users", params={"state": "blocked"}).json()] == ["Борисов Борис"]
    assert admin.get("/api/v1/admin/users", params={"q": "нет такого"}).headers["X-Total-Count"] == "0"
    assert all("last_seen_at" in u for u in admin.get("/api/v1/admin/users").json())


def test_forum_list_reports_its_total(app, fake_eios):
    student = login_student(app, fake_eios)
    for i in range(3):
        student.post("/api/v1/forum/questions", json={"title": f"Вопрос {i}", "content": "Где найти расписание?"}, headers=CSRF)
    r = student.get("/api/v1/forum/questions", params={"limit": 2})
    assert r.headers["X-Total-Count"] == "3" and len(r.json()) == 2


# --- B4 and R10: deleting anonymizes and keeps the history; everything goes to the journal ---

def _history(db, user_id):
    now = datetime.now(timezone.utc)
    item = models.ShopItem(title="Худи", price=10, stock=5)
    db.add(item)
    db.flush()
    db.add_all([
        models.ShopOrder(user_id=user_id, item_id=item.id, item_title="Худи", price=10, status="issued"),
        models.ShopOrder(user_id=user_id, item_id=item.id, item_title="Худи", price=10, status="new"),
        models.Booking(resource="room", zone="top", starts_at=now - timedelta(days=1, hours=2),
                       ends_at=now - timedelta(days=1), booked_by_id=user_id, purpose="Собрание"),
        models.ForumQuestion(author_id=user_id, title="Где 108?", content="Подскажите, где коворкинг", category="Учеба"),
    ])
    db.commit()
    return item.id


def test_deleting_a_user_anonymizes_and_keeps_the_history(app, fake_eios, db):
    student = login_student(app, fake_eios, "24-isbo-001", eios_id="77", full_name="Иванов Иван Иванович")
    student.patch("/api/v1/auth/me", json={"vk_url": "id12345", "max_contact": "@ivan"}, headers=CSRF)
    admin = login_admin(app)
    uid = _uid(db, "24-isbo-001")
    item_id = _history(db, uid)

    r = admin.delete(f"/api/v1/admin/users/{uid}", headers=CSRF)
    assert r.status_code == 200 and r.json()["status"] == "anonymized"
    db.expire_all()
    user = db.get(models.User, uid)
    assert user.full_name == "Удалённый пользователь" and user.auth_source == "deleted" and user.is_blocked
    assert (user.group_number, user.sdo_id, user.vk_url, user.max_contact) == (None, None, None, None)
    assert student.get("/api/v1/auth/me").status_code == 401
    # History stays: the issued order, the booking, the forum thread; the open order is cancelled
    statuses = sorted(o.status for o in db.query(models.ShopOrder).filter_by(user_id=uid))
    assert statuses == ["cancelled", "issued"]
    assert db.get(models.ShopItem, item_id).stock == 6
    assert db.query(models.Booking).filter_by(booked_by_id=uid).count() == 1
    assert db.query(models.ForumQuestion).filter_by(author_id=uid).count() == 1
    # Not in the default list; under "deleted"
    assert uid not in [u["id"] for u in admin.get("/api/v1/admin/users").json()]
    assert [u["id"] for u in admin.get("/api/v1/admin/users", params={"state": "deleted"}).json()] == [uid]
    # The same student signing in again gets a fresh account
    login_student(app, fake_eios, "24-isbo-001", eios_id="77")
    assert db.query(models.User).filter_by(username="24-isbo-001").one().id != uid

    # A second delete is refused; erasing for good is a separate, explicit step
    assert admin.delete(f"/api/v1/admin/users/{uid}", headers=CSRF).status_code == 400
    assert admin.delete(f"/api/v1/admin/users/{uid}", params={"purge": True}, headers=CSRF).json()["status"] == "deleted"
    db.expire_all()
    assert db.get(models.User, uid) is None

    journal = admin.get("/api/v1/admin/actions").json()
    assert [a["action"] for a in journal] == ["purge", "anonymize"]
    assert all("Иванов" not in (a["target_name"] or "") + (a["details"] or "") for a in journal)


def test_live_accounts_cannot_be_purged_directly(app, fake_eios, db):
    login_student(app, fake_eios)
    admin = login_admin(app)
    uid = _uid(db, "24-isbo-001")
    assert admin.delete(f"/api/v1/admin/users/{uid}", params={"purge": True}, headers=CSRF).status_code == 400
    assert db.query(models.User).filter_by(id=uid).count() == 1


def test_role_and_block_changes_are_journaled(app, fake_eios, db):
    login_student(app, fake_eios, full_name="Петров Пётр")
    admin = login_admin(app)
    uid = _uid(db, "24-isbo-001")
    admin.patch(f"/api/v1/admin/users/{uid}/role", json={"role": "moderator"}, headers=CSRF)
    admin.patch(f"/api/v1/admin/users/{uid}/block", json={"blocked": True}, headers=CSRF)
    admin.patch(f"/api/v1/admin/users/{uid}/block", json={"blocked": True}, headers=CSRF)  # no change, no entry
    r = admin.get("/api/v1/admin/actions")
    assert r.headers["X-Total-Count"] == "2"
    block, role = r.json()
    assert block["action"] == "block" and "Петров Пётр" in block["target_name"]
    assert role["details"] == "Студент → Модератор" and role["action_text"] == "Смена роли"


def test_only_admins_read_the_journal(app, fake_eios):
    student = login_student(app, fake_eios)
    assert student.get("/api/v1/admin/actions").status_code == 403


# --- B5: Max contact cannot carry a script link ---

@pytest.mark.parametrize("value", ["javascript:alert(1)", "data:text/html,<b>", "http://evil.example", "//evil.example"])
def test_max_contact_refuses_links_other_than_max(app, fake_eios, value):
    student = login_student(app, fake_eios)
    assert student.patch("/api/v1/auth/me", json={"max_contact": value}, headers=CSRF).status_code == 422


def test_max_contact_keeps_phones_nicknames_and_max_links(app, fake_eios):
    student = login_student(app, fake_eios)
    for value, stored in [("+7 900 123-45-67", "+7 900 123-45-67"), ("@ivan", "@ivan"), ("max.ru/ivan", "https://max.ru/ivan")]:
        assert student.patch("/api/v1/auth/me", json={"max_contact": value}, headers=CSRF).json()["max_contact"] == stored


# --- R5, R7, R8 ---

def test_readiness_checks_the_database(app):
    assert TestClient(app).get("/api/v1/health/ready").json() == {"status": "ok", "database": "ok"}


def test_unused_curator_role_cannot_be_given(app, fake_eios, db):
    login_student(app, fake_eios)
    admin = login_admin(app)
    r = admin.patch(f"/api/v1/admin/users/{_uid(db, '24-isbo-001')}/role", json={"role": "curator"}, headers=CSRF)
    assert r.status_code == 422


def test_anonymous_catalog_shows_leaders_without_group_or_contacts(app, fake_eios, db):
    admin = login_admin(app)
    aid = admin.post("/api/v1/admin/associations", json={"name": "Медиацентр"}, headers=CSRF).json()["id"]
    leader = login_student(app, fake_eios, "24-isbo-001", full_name="Смирнов Макар")
    leader.patch("/api/v1/auth/me", json={"vk_url": "id1"}, headers=CSRF)
    admin.put(f"/api/v1/admin/associations/{aid}/leaders/{_uid(db, '24-isbo-001')}", headers=CSRF)

    anonymous = TestClient(app).get("/api/v1/associations").json()
    person = next(a for a in anonymous if a["id"] == aid)["leaders"][0]
    assert person["full_name"] == "Смирнов Макар" and person["group_number"] is None and person["vk_url"] is None
    signed_in = next(a for a in leader.get("/api/v1/associations").json() if a["id"] == aid)["leaders"][0]
    assert signed_in["group_number"] == "24-ИСбо-1" and signed_in["vk_url"] == "id1"
    assert [a["action"] for a in admin.get("/api/v1/admin/actions").json()] == ["leader_add"]


# --- B8: a guest's page load is a 200, not a 401 in the console ---

def test_session_answers_guests_without_an_error(app, fake_eios, db):
    assert TestClient(app).get("/api/v1/auth/session").json() == {"user": None}
    student = login_student(app, fake_eios)
    assert student.get("/api/v1/auth/session").json()["user"]["username"] == "24-isbo-001"
    login_admin(app).patch(f"/api/v1/admin/users/{_uid(db, '24-isbo-001')}/block", json={"blocked": True}, headers=CSRF)
    r = student.get("/api/v1/auth/session")
    assert r.status_code == 200 and r.json() == {"user": None}
    assert "portal_token=" in r.headers.get("set-cookie", "")
