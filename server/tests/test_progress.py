from datetime import datetime, timedelta, timezone

import pytest

import app.models as models
from app.db.database import SessionLocal
from conftest import CSRF, login_admin, login_student


@pytest.fixture(autouse=True)
def empty_catalog(app):
    session = SessionLocal()
    session.query(models.Association).delete()
    session.commit()
    session.close()


def _uid(db, n):
    return db.query(models.User).filter_by(username=f"24-isbo-{n:03d}").one().id


@pytest.fixture
def club(app, fake_eios, db):
    admin = login_admin(app)
    aid = admin.post("/api/v1/admin/associations", json={"name": "Медиацентр"}, headers=CSRF).json()["id"]
    leader = login_student(app, fake_eios, username="24-isbo-001", eios_id="7001", full_name="Смирнов Макар Олегович")
    member = login_student(app, fake_eios, username="24-isbo-002", eios_id="7002", full_name="Петрова Анна Сергеевна")
    admin.put(f"/api/v1/admin/associations/{aid}/leaders/{_uid(db, 1)}", headers=CSRF)
    member.post(f"/api/v1/associations/{aid}/apply", json={}, headers=CSRF)
    leader.post(f"/api/v1/associations/{aid}/members/{_uid(db, 2)}/decision", json={"approve": True}, headers=CSRF)
    return admin, aid, leader, member


def test_done_cards_go_to_the_archive(club, db):
    admin, aid, leader, member = club
    t = member.post("/api/v1/tasks", json={"title": "Купить тетради"}, headers=CSRF).json()
    member.patch(f"/api/v1/tasks/{t['id']}/status", json={"status": "done"}, headers=CSRF)
    assert [c["title"] for c in member.get("/api/v1/tasks/my").json()] == ["Купить тетради"]
    # By hand...
    assert member.patch(f"/api/v1/tasks/{t['id']}/archive", json={"archived": True}, headers=CSRF).json()["archived_at"]
    assert member.get("/api/v1/tasks/my").json() == []
    assert [c["title"] for c in member.get("/api/v1/tasks/my", params={"archived": True}).json()] == ["Купить тетради"]
    member.patch(f"/api/v1/tasks/{t['id']}/archive", json={"archived": False}, headers=CSRF)
    assert len(member.get("/api/v1/tasks/my").json()) == 1
    # ...or a week after "Готово"
    card = db.query(models.TaskAssignee).filter_by(task_id=t["id"]).one()
    card.status_changed_at = datetime.now(timezone.utc) - timedelta(days=8)
    db.commit()
    assert member.get("/api/v1/tasks/my").json() == []
    # Only finished work goes there; moving it back to work returns it to the board
    t2 = member.post("/api/v1/tasks", json={"title": "Эссе"}, headers=CSRF).json()
    assert member.patch(f"/api/v1/tasks/{t2['id']}/archive", json={"archived": True}, headers=CSRF).status_code == 400
    member.patch(f"/api/v1/tasks/{t['id']}/status", json={"status": "in_progress"}, headers=CSRF)
    assert {c["title"] for c in member.get("/api/v1/tasks/my").json()} == {"Купить тетради", "Эссе"}


def test_leaders_archive_tasks_they_set(club):
    admin, aid, leader, member = club
    t = leader.post("/api/v1/tasks", json={"title": "Ролик", "association_id": aid, "to_all": True}, headers=CSRF).json()
    assert member.patch(f"/api/v1/tasks/{t['id']}/managed-archive", json={"archived": True}, headers=CSRF).status_code == 403
    leader.patch(f"/api/v1/tasks/{t['id']}/managed-archive", json={"archived": True}, headers=CSRF)
    assert leader.get("/api/v1/tasks/managed").json() == []
    assert [x["title"] for x in leader.get("/api/v1/tasks/managed", params={"archived": True}).json()] == ["Ролик"]
    # The assignee still has their card
    assert [c["title"] for c in member.get("/api/v1/tasks/my").json()] == ["Ролик"]


def test_points_and_badges_come_from_confirmed_facts(club, db):
    admin, aid, leader, member = club
    past = datetime.now(timezone.utc) - timedelta(days=1)
    ev = leader.post("/api/v1/events", json={"title": "Квиз", "association_id": aid, "starts_at": past.isoformat(),
                                             "ends_at": (past + timedelta(hours=2)).isoformat(), "volunteer_limit": 3}, headers=CSRF).json()
    leader.post(f"/api/v1/events/{ev['id']}/registrations", json={"user_ids": [_uid(db, 2)], "role": "volunteer"}, headers=CSRF)
    # A task handed in on time, and a personal one (does not count)
    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    t = leader.post("/api/v1/tasks", json={"title": "Ролик", "association_id": aid, "to_all": True, "due_at": due}, headers=CSRF).json()
    member.patch(f"/api/v1/tasks/{t['id']}/status", json={"status": "review"}, headers=CSRF)
    p = member.post("/api/v1/tasks", json={"title": "Личная"}, headers=CSRF).json()
    member.patch(f"/api/v1/tasks/{p['id']}/status", json={"status": "done"}, headers=CSRF)
    for i in range(12):
        member.post("/api/v1/homework", json={"text": f"Задание {i}"}, headers=CSRF)

    r = member.get("/api/v1/progress").json()
    assert r["facts"]["volunteer"] == 1 and r["facts"]["on_time"] == 1 and r["facts"]["homework"] == 12
    # 15 volunteering + 5 on time + homework capped at 10 × 2
    assert r["points"] == 15 + 5 + 20 and r["semester_points"] == 40
    assert r["level"]["title"] == "Новичок" and r["level"]["next_at"] == 50
    badges = {b["id"]: b for b in r["badges"]}
    assert badges["volunteer"]["level"] == 1 and badges["volunteer"]["next"] == 3
    assert badges["homework"]["level"] == 2 and badges["associations"]["level"] == 1
    assert badges["events"]["level"] == 0 and badges["events"]["hint"] == "Побывать на мероприятиях: 1"
    # The leader organized an event that took place
    assert {b["id"]: b["level"] for b in leader.get("/api/v1/progress").json()["badges"]}["organized"] == 1
    # Marked absent: nothing
    leader.put(f"/api/v1/events/{ev['id']}/attendance", json={"user_ids": []}, headers=CSRF)
    assert member.get("/api/v1/progress").json()["facts"]["volunteer"] == 0
