import pytest

import main
import app.models as models
from app.db.database import SessionLocal
from conftest import CSRF, login_admin, login_student


@pytest.fixture(autouse=True)
def empty_catalog(app):
    """The startup seed fills the catalog once; every test here starts without it."""
    session = SessionLocal()
    session.query(models.Association).delete()
    session.commit()
    session.close()


def _student(app, fake_eios, n, full_name, **kwargs):
    return login_student(app, fake_eios, username=f"24-isbo-{n:03d}", eios_id=str(1000 + n), full_name=full_name, **kwargs)


def _user_id(db, username):
    return db.query(models.User).filter_by(username=username).one().id


def _create(admin, name="Спортивное программирование", **extra):
    r = admin.post("/api/v1/admin/associations", json={"name": name, **extra}, headers=CSRF)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _setup(app, fake_eios, db):
    """An association with a leader (who shared contacts) and a separate student."""
    admin = login_admin(app)
    aid = _create(admin, description="Олимпиады ICPC")
    leader = _student(app, fake_eios, 1, "Лебедев Глеб Андреевич")
    leader.patch("/api/v1/auth/me", json={"tg_username": "@gleb_lebedev", "vk_url": "https://vk.com/id42"}, headers=CSRF)
    assert admin.put(f"/api/v1/admin/associations/{aid}/leaders/{_user_id(db, '24-isbo-001')}", headers=CSRF).status_code == 200
    student = _student(app, fake_eios, 2, "Петрова Анна Сергеевна")
    return admin, aid, leader, student


def test_catalog_shows_leader_contacts_only_to_signed_in_users(app, fake_eios, db, client):
    _, aid, _, student = _setup(app, fake_eios, db)
    guest_item = client.get("/api/v1/associations").json()[0]
    assert guest_item["leaders"][0]["full_name"] == "Лебедев Глеб Андреевич" and guest_item["listed_leader"] is None
    assert guest_item["leaders"][0]["tg_username"] is None and guest_item["my_status"] is None
    item = student.get(f"/api/v1/associations/{aid}").json()
    assert item["leaders"][0]["tg_username"] == "gleb_lebedev" and item["leaders"][0]["vk_url"] == "id42"
    assert item["member_count"] == 1 and item["can_manage"] is False and item["members"] == []


def test_application_is_moderated_by_the_leader(app, fake_eios, db):
    _, aid, leader, student = _setup(app, fake_eios, db)
    r = student.post(f"/api/v1/associations/{aid}/apply", json={"message": "Хочу на ICPC"}, headers=CSRF)
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert student.post(f"/api/v1/associations/{aid}/apply", json={}, headers=CSRF).status_code == 400
    sid = _user_id(db, "24-isbo-002")

    # Another student cannot decide, the leader can
    other = _student(app, fake_eios, 3, "Сидоров Пётр Ильич")
    assert other.post(f"/api/v1/associations/{aid}/members/{sid}/decision", json={"approve": True}, headers=CSRF).status_code == 403
    detail = leader.get(f"/api/v1/associations/{aid}").json()
    assert detail["can_manage"] and [a["message"] for a in detail["applications"]] == ["Хочу на ICPC"]
    r = leader.post(f"/api/v1/associations/{aid}/members/{sid}/decision", json={"approve": True}, headers=CSRF)
    assert r.status_code == 200 and r.json()["status"] == "approved"

    mine = student.get("/api/v1/associations/mine").json()
    assert mine == [{**mine[0], "association_id": aid, "role": "member", "status": "approved"}]
    assert student.get(f"/api/v1/associations/{aid}").json()["member_count"] == 2
    # Deciding twice is not possible
    assert leader.post(f"/api/v1/associations/{aid}/members/{sid}/decision", json={"approve": False}, headers=CSRF).status_code == 404


def test_rejected_student_can_apply_again_and_members_can_leave(app, fake_eios, db):
    _, aid, leader, student = _setup(app, fake_eios, db)
    sid = _user_id(db, "24-isbo-002")
    student.post(f"/api/v1/associations/{aid}/apply", json={}, headers=CSRF)
    leader.post(f"/api/v1/associations/{aid}/members/{sid}/decision", json={"approve": False}, headers=CSRF)
    assert student.get(f"/api/v1/associations/{aid}").json()["my_status"] == "rejected"
    assert student.post(f"/api/v1/associations/{aid}/apply", json={}, headers=CSRF).json()["status"] == "pending"
    # Withdrawing a pending application removes it
    assert student.delete(f"/api/v1/associations/{aid}/membership", headers=CSRF).status_code == 200
    assert student.get(f"/api/v1/associations/{aid}").json()["my_status"] is None
    # A leader cannot simply leave
    assert leader.delete(f"/api/v1/associations/{aid}/membership", headers=CSRF).status_code == 400


def test_leader_removes_members_but_not_leaders(app, fake_eios, db):
    admin, aid, leader, student = _setup(app, fake_eios, db)
    sid, lid = _user_id(db, "24-isbo-002"), _user_id(db, "24-isbo-001")
    student.post(f"/api/v1/associations/{aid}/apply", json={}, headers=CSRF)
    leader.post(f"/api/v1/associations/{aid}/members/{sid}/decision", json={"approve": True}, headers=CSRF)
    assert leader.delete(f"/api/v1/associations/{aid}/members/{lid}", headers=CSRF).status_code == 400
    assert leader.delete(f"/api/v1/associations/{aid}/members/{sid}", headers=CSRF).status_code == 200
    assert student.get(f"/api/v1/associations/{aid}").json()["my_status"] == "left"
    # Taking the leader role away keeps them as a member
    r = admin.delete(f"/api/v1/admin/associations/{aid}/leaders/{lid}", headers=CSRF)
    assert r.status_code == 200 and r.json()["leaders"] == [] and r.json()["member_count"] == 1
    assert leader.get(f"/api/v1/associations/{aid}").json()["can_manage"] is False


def test_leader_edits_description_but_not_other_associations(app, fake_eios, db):
    admin, aid, leader, _ = _setup(app, fake_eios, db)
    r = leader.put(f"/api/v1/associations/{aid}", json={"description": "Тренировки по средам", "contacts": "t.me/ivitsh_icpc"}, headers=CSRF)
    assert r.status_code == 200 and r.json()["description"] == "Тренировки по средам"
    other = _create(admin, name="Театр")
    assert leader.put(f"/api/v1/associations/{other}", json={"description": "x"}, headers=CSRF).status_code == 403


def test_admin_manages_associations(app, fake_eios, db, client):
    admin = login_admin(app)
    student = _student(app, fake_eios, 2, "Петрова Анна Сергеевна")
    aid = _create(admin, name="Театр")
    assert admin.post("/api/v1/admin/associations", json={"name": "театр"}, headers=CSRF).status_code == 400
    assert student.post("/api/v1/admin/associations", json={"name": "Хор"}, headers=CSRF).status_code == 403
    # Hidden associations leave the catalog but stay with the admin
    r = admin.put(f"/api/v1/admin/associations/{aid}", json={"name": "Театр", "is_active": False}, headers=CSRF)
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert client.get("/api/v1/associations").json() == []
    assert student.get(f"/api/v1/associations/{aid}").status_code == 404
    assert student.post(f"/api/v1/associations/{aid}/apply", json={}, headers=CSRF).status_code == 404
    assert admin.get(f"/api/v1/associations/{aid}").status_code == 200
    assert admin.delete(f"/api/v1/admin/associations/{aid}", headers=CSRF).status_code == 200
    assert admin.get("/api/v1/admin/associations").json() == []


def test_leader_hint_suggests_the_signed_in_student(app, fake_eios, db):
    admin = login_admin(app)
    aid = _create(admin, name="Волонтёры ИВИТШ", leader_hint="Иванов Артем")
    assert admin.get(f"/api/v1/associations/{aid}").json()["listed_leader"] == "Иванов Артем"
    _student(app, fake_eios, 5, "Иванов Артём Сергеевич")
    _student(app, fake_eios, 6, "Иванова Мария Петровна")
    item = next(a for a in admin.get("/api/v1/admin/associations").json() if a["id"] == aid)
    assert [u["full_name"] for u in item["hint_matches"]] == ["Иванов Артём Сергеевич"]
    admin.put(f"/api/v1/admin/associations/{aid}/leaders/{item['hint_matches'][0]['id']}", headers=CSRF)
    item = next(a for a in admin.get("/api/v1/admin/associations").json() if a["id"] == aid)
    assert item["hint_matches"] == [] and item["leaders"][0]["full_name"] == "Иванов Артём Сергеевич"


def test_contacts_are_normalized_and_validated(app, fake_eios):
    c = _student(app, fake_eios, 7, "Смирнов Макар Олегович")
    r = c.patch("/api/v1/auth/me", json={"tg_username": "https://t.me/makar_s", "vk_url": "vk.com/makar.smirnov", "max_contact": "+7 900 000-00-00"}, headers=CSRF)
    assert r.status_code == 200
    assert (r.json()["tg_username"], r.json()["vk_url"], r.json()["max_contact"]) == ("makar_s", "makar.smirnov", "+7 900 000-00-00")
    assert c.patch("/api/v1/auth/me", json={"tg_username": "a b"}, headers=CSRF).status_code == 422
    assert c.patch("/api/v1/auth/me", json={"vk_url": "https://evil.example/x"}, headers=CSRF).status_code == 422
    # An empty value clears the contact, a missing one keeps it
    r = c.patch("/api/v1/auth/me", json={"tg_username": ""}, headers=CSRF)
    assert r.json()["tg_username"] is None and r.json()["vk_url"] == "makar.smirnov"


def test_member_contacts_are_for_leaders_only(app, fake_eios, db):
    _, aid, leader, student = _setup(app, fake_eios, db)
    student.patch("/api/v1/auth/me", json={"tg_username": "anna_petrova"}, headers=CSRF)
    student.post(f"/api/v1/associations/{aid}/apply", json={}, headers=CSRF)
    applicant = leader.get(f"/api/v1/associations/{aid}").json()["applications"][0]
    assert applicant["tg_username"] == "anna_petrova" and applicant["group_number"] == "24-ИСбо-1"
    other = _student(app, fake_eios, 3, "Сидоров Пётр Ильич")
    detail = other.get(f"/api/v1/associations/{aid}").json()
    assert detail["applications"] == [] and detail["members"] == []


def test_last_seen_is_recorded(app, fake_eios, db):
    c = _student(app, fake_eios, 8, "Ли Михаил Юрьевич")
    assert c.get("/api/v1/auth/me").status_code == 200
    assert db.query(models.User).filter_by(username="24-isbo-008").one().last_seen_at is not None


def test_deleting_a_user_removes_their_memberships(app, fake_eios, db):
    admin, aid, _, student = _setup(app, fake_eios, db)
    student.post(f"/api/v1/associations/{aid}/apply", json={}, headers=CSRF)
    assert admin.delete(f"/api/v1/admin/users/{_user_id(db, '24-isbo-002')}", headers=CSRF).status_code == 200
    assert db.query(models.Membership).count() == 1  # only the leader's


def test_admin_finds_users_by_cyrillic_name(app, fake_eios):
    admin = login_admin(app)
    _student(app, fake_eios, 9, "Цветкова Валерия Игоревна")
    found = admin.get("/api/v1/admin/users", params={"q": "цветкова"}).json()
    assert [u["full_name"] for u in found] == ["Цветкова Валерия Игоревна"]


def test_seed_loads_the_institute_associations(app):
    main.seed_database()
    session = SessionLocal()
    try:
        names = {a.name: a.leader_hint for a in session.query(models.Association).all()}
    finally:
        session.close()
    assert len(names) == 21
    assert names["ТОП ИВИТШ"] == "Боровков Александр Константинович" and names["Наука"] is None


def test_catalog_lists_russian_names_first(app, client):
    admin = login_admin(app)
    for name in ("IT профессионал", "Театр", "Актив ИВИТШ", "Nexthub"):
        _create(admin, name=name)
    assert [a["name"] for a in client.get("/api/v1/associations").json()] == ["Актив ИВИТШ", "Театр", "IT профессионал", "Nexthub"]
