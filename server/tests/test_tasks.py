import os

import pytest

import app.models as models
from app.core.config import settings
from app.db.database import SessionLocal
from conftest import CSRF, login_admin, login_student

PDF = b"%PDF-1.4\n% test\n"


@pytest.fixture(autouse=True)
def empty_catalog(app):
    session = SessionLocal()
    session.query(models.Association).delete()
    session.commit()
    session.close()


def _student(app, fake_eios, n, full_name):
    return login_student(app, fake_eios, username=f"24-isbo-{n:03d}", eios_id=str(2000 + n), full_name=full_name)


def _uid(db, n):
    return db.query(models.User).filter_by(username=f"24-isbo-{n:03d}").one().id


@pytest.fixture
def club(app, fake_eios, db):
    """An association with a leader and two approved members; returns (id, leader, member1, member2, outsider)."""
    admin = login_admin(app)
    aid = admin.post("/api/v1/admin/associations", json={"name": "ВИТШ медиа"}, headers=CSRF).json()["id"]
    leader = _student(app, fake_eios, 1, "Смирнов Макар Олегович")
    admin.put(f"/api/v1/admin/associations/{aid}/leaders/{_uid(db, 1)}", headers=CSRF)
    members = []
    for n, name in ((2, "Петрова Анна Сергеевна"), (3, "Сидоров Пётр Ильич")):
        c = _student(app, fake_eios, n, name)
        c.post(f"/api/v1/associations/{aid}/apply", json={}, headers=CSRF)
        leader.post(f"/api/v1/associations/{aid}/members/{_uid(db, n)}/decision", json={"approve": True}, headers=CSRF)
        members.append(c)
    outsider = _student(app, fake_eios, 4, "Ли Михаил Юрьевич")
    return aid, leader, members[0], members[1], outsider


def _task(client, **data):
    r = client.post("/api/v1/tasks", json={"title": "Смонтировать видео", **data}, headers=CSRF)
    assert r.status_code == 201, r.text
    return r.json()


def test_personal_task_with_color_and_deadline(app, fake_eios):
    c = _student(app, fake_eios, 5, "Цветкова Валерия Игоревна")
    t = _task(c, title="Купить тетради", color="green", due_at="2026-10-05T18:00:00+03:00")
    assert t["color"] == "green" and t["association"] is None and t["can_manage"] and t["my_status"] == "todo"
    # Stored in UTC, sent back with the offset
    assert t["due_at"] == "2026-10-05T15:00:00+00:00"
    board = c.get("/api/v1/tasks/my").json()
    assert [b["title"] for b in board] == ["Купить тетради"]
    # The owner may mark it done at once
    r = c.patch(f"/api/v1/tasks/{t['id']}/status", json={"status": "done"}, headers=CSRF)
    assert r.status_code == 200 and r.json()["completed_at"]
    assert c.get("/api/v1/tasks/my", params={"personal": True}).json()[0]["my_status"] == "done"


def test_leader_sets_a_task_for_the_whole_association(club, db):
    aid, leader, m1, m2, outsider = club
    t = _task(leader, association_id=aid, to_all=True, description="Ролик про посвящение")
    assert {a["full_name"] for a in t["assignees"]} == {"Петрова Анна Сергеевна", "Сидоров Пётр Ильич"}
    assert [c["title"] for c in m1.get("/api/v1/tasks/my").json()] == ["Смонтировать видео"]
    assert leader.get("/api/v1/tasks/my").json() == []  # the leader is not an assignee
    managed = leader.get("/api/v1/tasks/managed").json()
    assert managed[0]["total"] == 2 and managed[0]["counts"]["todo"] == 2
    # Strangers do not even learn that the task exists
    assert outsider.get(f"/api/v1/tasks/{t['id']}").status_code == 404
    assert outsider.post("/api/v1/tasks", json={"title": "x", "association_id": aid, "to_all": True}, headers=CSRF).status_code == 403


def test_task_for_chosen_members_only(club, db):
    aid, leader, m1, m2, _ = club
    t = _task(leader, association_id=aid, assignee_ids=[_uid(db, 2)])
    assert [a["full_name"] for a in t["assignees"]] == ["Петрова Анна Сергеевна"]
    assert m2.get("/api/v1/tasks/my").json() == []
    # Only members can be assignees
    r = leader.post("/api/v1/tasks", json={"title": "x", "association_id": aid, "assignee_ids": [_uid(db, 4)]}, headers=CSRF)
    assert r.status_code == 400
    # The leader adds one more later; the first one keeps their progress
    m1.patch(f"/api/v1/tasks/{t['id']}/status", json={"status": "in_progress"}, headers=CSRF)
    r = leader.put(f"/api/v1/tasks/{t['id']}", json={"title": "Смонтировать видео", "add_assignee_ids": [_uid(db, 3)]}, headers=CSRF)
    assert {a["full_name"]: a["status"] for a in r.json()["assignees"]} == {"Петрова Анна Сергеевна": "in_progress", "Сидоров Пётр Ильич": "todo"}


def test_member_hands_in_and_the_leader_accepts(club, db):
    aid, leader, m1, m2, _ = club
    t = _task(leader, association_id=aid, to_all=True)
    tid, sid = t["id"], _uid(db, 2)
    assert m1.patch(f"/api/v1/tasks/{tid}/status", json={"status": "review"}, headers=CSRF).status_code == 200
    # A member cannot mark it done, nor move someone else's card
    assert m1.patch(f"/api/v1/tasks/{tid}/status", json={"status": "done"}, headers=CSRF).status_code == 403
    assert m2.patch(f"/api/v1/tasks/{tid}/status", json={"status": "review", "user_id": sid}, headers=CSRF).status_code == 403
    r = leader.patch(f"/api/v1/tasks/{tid}/status", json={"status": "done", "user_id": sid}, headers=CSRF)
    assert r.status_code == 200 and r.json()["status"] == "done" and r.json()["completed_at"]
    counts = leader.get("/api/v1/tasks/managed").json()[0]["counts"]
    assert counts == {"todo": 1, "in_progress": 0, "review": 0, "done": 1}
    # Returned for rework: no longer counted as handed in
    r = leader.patch(f"/api/v1/tasks/{tid}/status", json={"status": "in_progress", "user_id": sid}, headers=CSRF)
    assert r.json()["completed_at"] is None


def test_comments_are_shared_by_the_task_people(club, db):
    aid, leader, m1, m2, outsider = club
    t = _task(leader, association_id=aid, to_all=True)
    c = m1.post(f"/api/v1/tasks/{t['id']}/comments", json={"text": "Какой формат?"}, headers=CSRF).json()
    leader.post(f"/api/v1/tasks/{t['id']}/comments", json={"text": "MP4, 1080p"}, headers=CSRF)
    assert [x["text"] for x in m2.get(f"/api/v1/tasks/{t['id']}").json()["comments"]] == ["Какой формат?", "MP4, 1080p"]
    assert m2.delete(f"/api/v1/tasks/comments/{c['id']}", headers=CSRF).status_code == 403
    assert leader.delete(f"/api/v1/tasks/comments/{c['id']}", headers=CSRF).status_code == 200
    assert outsider.post(f"/api/v1/tasks/{t['id']}/comments", json={"text": "спам"}, headers=CSRF).status_code == 404


def test_files_are_checked_stored_and_protected(club, db):
    aid, leader, m1, _, outsider = club
    t = _task(leader, association_id=aid, to_all=True)
    up = lambda c, name, body: c.post(f"/api/v1/tasks/{t['id']}/files", params={"name": name}, content=body,  # noqa: E731
                                      headers={**CSRF, "Content-Type": "application/octet-stream"})
    r = up(m1, "Сценарий.pdf", PDF)
    assert r.status_code == 201 and r.json()["title"] == "Сценарий.pdf" and r.json()["size"] == len(PDF)
    aid_file = r.json()["id"]
    # A program renamed to .pdf, an unknown type and a too big file are refused
    assert up(m1, "virus.pdf", b"MZ\x90\x00").status_code == 415
    assert up(m1, "page.html", b"<html>").status_code == 415
    assert up(m1, "big.pdf", b"%PDF" + b"0" * (settings.MAX_UPLOAD_MB * 1024 * 1024)).status_code == 413
    # Downloads go through the rights check
    r = leader.get(f"/api/v1/attachments/{aid_file}")
    assert r.status_code == 200 and r.content == PDF and "attachment" in r.headers["content-disposition"]
    assert outsider.get(f"/api/v1/attachments/{aid_file}").status_code == 404
    # Deleting the task removes the file from disk
    stored = db.get(models.Attachment, aid_file).stored_name
    assert os.path.exists(os.path.join(settings.UPLOAD_DIR, stored))
    assert leader.delete(f"/api/v1/tasks/{t['id']}", headers=CSRF).status_code == 200
    assert not os.path.exists(os.path.join(settings.UPLOAD_DIR, stored))


def test_links_on_tasks(club):
    aid, leader, m1, _, _ = club
    t = _task(leader, association_id=aid, to_all=True)
    r = m1.post(f"/api/v1/tasks/{t['id']}/links", json={"url": "https://disk.yandex.ru/d/abc", "title": "Исходники"}, headers=CSRF)
    assert r.status_code == 201 and r.json()["url"] == "https://disk.yandex.ru/d/abc"
    assert m1.post(f"/api/v1/tasks/{t['id']}/links", json={"url": "javascript:alert(1)"}, headers=CSRF).status_code == 422


def test_announcements_reach_their_recipients(club, db):
    aid, leader, m1, m2, outsider = club
    r = leader.post(f"/api/v1/associations/{aid}/posts", json={"title": "Чат объединения", "text": "vk.me/join/abc"}, headers=CSRF)
    assert r.status_code == 201
    r = leader.post(f"/api/v1/associations/{aid}/posts", json={"title": "Распоряжение", "to_all": False, "recipient_ids": [_uid(db, 2)]}, headers=CSRF)
    private = r.json()
    assert [p["full_name"] for p in private["recipients"]] == ["Петрова Анна Сергеевна"]
    r = leader.post(f"/api/v1/associations/posts/{private['id']}/files", params={"name": "Распоряжение.pdf"}, content=PDF,
                    headers={**CSRF, "Content-Type": "application/pdf"})
    file_id = r.json()["id"]
    assert [p["title"] for p in m1.get(f"/api/v1/associations/{aid}/posts").json()] == ["Распоряжение", "Чат объединения"]
    assert [p["title"] for p in m2.get(f"/api/v1/associations/{aid}/posts").json()] == ["Чат объединения"]
    assert outsider.get(f"/api/v1/associations/{aid}/posts").json() == []
    assert m1.get(f"/api/v1/attachments/{file_id}").status_code == 200
    assert m2.get(f"/api/v1/attachments/{file_id}").status_code == 404
    # Members cannot post
    assert m1.post(f"/api/v1/associations/{aid}/posts", json={"title": "x"}, headers=CSRF).status_code == 403


def test_deleting_an_association_removes_its_files(club, app, db):
    aid, leader, _, _, _ = club
    t = _task(leader, association_id=aid, to_all=True)
    r = leader.post(f"/api/v1/tasks/{t['id']}/files", params={"name": "a.pdf"}, content=PDF, headers={**CSRF, "Content-Type": "application/pdf"})
    stored = db.get(models.Attachment, r.json()["id"]).stored_name
    assert login_admin(app).delete(f"/api/v1/admin/associations/{aid}", headers=CSRF).status_code == 200
    assert not os.path.exists(os.path.join(settings.UPLOAD_DIR, stored))
    assert db.query(models.Task).count() == 0
