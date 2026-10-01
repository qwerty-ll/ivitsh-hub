"""S1: BOLA / BFLA / leader-of-own-association / mass assignment / main-admin rules.

Convention: tests named `test_*_ok` assert that the protection HOLDS (a regression guard);
tests named `test_*_FINDING` pass when the weakness is PRESENT (see docs/audit findings S1-xxx).
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.models as models
from app.db.database import SessionLocal
from srv_conftest import CSRF, login_admin, login_student

PDF = b"%PDF-1.4\n% poc\n"


@pytest.fixture(autouse=True)
def empty_catalog(app):
    s = SessionLocal()
    s.query(models.Association).delete()
    s.commit()
    s.close()


def _stu(app, fake_eios, n, name, **kw):
    return login_student(app, fake_eios, username=f"24-isbo-{n:03d}", eios_id=str(9000 + n), full_name=name, **kw)


def _uid(db, n):
    return db.query(models.User).filter_by(username=f"24-isbo-{n:03d}").one().id


def _window(start_offset_min, minutes=60):
    start = datetime.now(timezone.utc) + timedelta(minutes=start_offset_min)
    return {"starts_at": start.isoformat(), "ends_at": (start + timedelta(minutes=minutes)).isoformat()}


@pytest.fixture
def world(app, fake_eios, db):
    """Two associations A and B, a leader each, members, an outsider; one task/post/meeting/file in A."""
    admin = login_admin(app)
    a = admin.post("/api/v1/admin/associations", json={"name": "Alpha club"}, headers=CSRF).json()["id"]
    b = admin.post("/api/v1/admin/associations", json={"name": "Beta club"}, headers=CSRF).json()["id"]
    la = _stu(app, fake_eios, 1, "Лидер Альфа Первый")
    lb = _stu(app, fake_eios, 3, "Лидер Бета Третий")
    admin.put(f"/api/v1/admin/associations/{a}/leaders/{_uid(db, 1)}", headers=CSRF)
    admin.put(f"/api/v1/admin/associations/{b}/leaders/{_uid(db, 3)}", headers=CSRF)
    member = _stu(app, fake_eios, 2, "Участник Альфа Второй")
    rm = _stu(app, fake_eios, 5, "Исключаемый Пятый")
    outsider = _stu(app, fake_eios, 4, "Чужой Четвёртый")
    for n, c in ((2, member), (5, rm)):
        c.post(f"/api/v1/associations/{a}/apply", json={}, headers=CSRF)
        la.post(f"/api/v1/associations/{a}/members/{_uid(db, n)}/decision", json={"approve": True}, headers=CSRF)
    task = la.post("/api/v1/tasks", json={"title": "Task A", "description": "secret plan", "association_id": a, "to_all": True,
                                          "due_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()}, headers=CSRF).json()
    f = la.post(f"/api/v1/tasks/{task['id']}/files?name=plan.pdf", content=PDF, headers={**CSRF, "Content-Type": "application/octet-stream"})
    assert f.status_code == 201, f.text
    post = la.post(f"/api/v1/associations/{a}/posts", json={"title": "Internal", "text": "chat link", "to_all": True}, headers=CSRF).json()
    pf = la.post(f"/api/v1/associations/posts/{post['id']}/files?name=order.pdf", content=PDF, headers={**CSRF, "Content-Type": "application/octet-stream"})
    assert pf.status_code == 201, pf.text
    meeting = la.post(f"/api/v1/associations/{a}/meetings", json={"title": "Sync", **_window(120)}, headers=CSRF).json()
    return dict(admin=admin, a=a, b=b, la=la, lb=lb, member=member, rm=rm, outsider=outsider, task=task["id"],
                att=f.json()["id"], post=post["id"], post_att=pf.json()["id"], meeting=meeting["id"])


def _status(r):
    return r.status_code


def test_bola_other_association_leader_and_outsider_ok(world, db):
    """Leader of B and an outsider cannot touch anything of association A (404/403 on every call)."""
    w = world
    a, t, att, p, m = w["a"], w["task"], w["att"], w["post"], w["meeting"]
    uid_member = _uid(db, 2)
    calls = [
        ("GET", f"/api/v1/tasks/{t}", None),
        ("PUT", f"/api/v1/tasks/{t}", {"title": "x"}),
        ("DELETE", f"/api/v1/tasks/{t}", None),
        ("PATCH", f"/api/v1/tasks/{t}/status", {"status": "done", "user_id": uid_member}),
        ("PATCH", f"/api/v1/tasks/{t}/status", {"status": "done"}),
        ("PATCH", f"/api/v1/tasks/{t}/archive", {"archived": True}),
        ("PATCH", f"/api/v1/tasks/{t}/managed-archive", {"archived": True}),
        ("DELETE", f"/api/v1/tasks/{t}/assignees/{uid_member}", None),
        ("POST", f"/api/v1/tasks/{t}/comments", {"text": "hi"}),
        ("POST", f"/api/v1/tasks/{t}/links", {"url": "https://example.org/x"}),
        ("GET", f"/api/v1/attachments/{att}", None),
        ("DELETE", f"/api/v1/attachments/{att}", None),
        ("GET", f"/api/v1/attachments/{w['post_att']}", None),
        ("DELETE", f"/api/v1/attachments/{w['post_att']}", None),
        ("PUT", f"/api/v1/associations/{a}", {"description": "pwn"}),
        ("POST", f"/api/v1/associations/{a}/members/{uid_member}/decision", {"approve": True}),
        ("DELETE", f"/api/v1/associations/{a}/members/{uid_member}", None),
        ("POST", f"/api/v1/associations/{a}/members/{uid_member}/restore", None),
        ("POST", f"/api/v1/associations/{a}/posts", {"title": "x", "to_all": True}),
        ("DELETE", f"/api/v1/associations/posts/{p}", None),
        ("POST", f"/api/v1/associations/posts/{p}/links", {"url": "https://example.org/x"}),
        ("GET", f"/api/v1/associations/{a}/meetings", None),
        ("POST", f"/api/v1/associations/{a}/meetings", {"title": "x", **_window(60)}),
        ("GET", f"/api/v1/meetings/{m}", None),
        ("PUT", f"/api/v1/meetings/{m}", {"title": "x", **_window(60)}),
        ("DELETE", f"/api/v1/meetings/{m}", None),
        ("PUT", f"/api/v1/meetings/{m}/attendance", {"user_ids": [uid_member]}),
        ("POST", "/api/v1/tasks", {"title": "x", "association_id": a, "to_all": True}),
    ]
    bad = []
    for who in ("lb", "outsider"):
        c = w[who]
        for method, url, body in calls:
            r = c.request(method, url, json=body, headers=CSRF)
            if r.status_code < 400:
                bad.append((who, method, url, r.status_code))
    # posts list for a non-member is an empty list, not an error: it must not leak the post
    for who in ("lb", "outsider"):
        r = w[who].get(f"/api/v1/associations/{a}/posts")
        assert r.status_code in (200, 403) and (r.status_code == 403 or r.json() == []), r.text
    assert not bad, bad
    # the task and file are still there
    assert w["la"].get(f"/api/v1/tasks/{t}").status_code == 200


def test_bfla_students_and_moderators_cannot_use_admin_endpoints_ok(world, db, app, fake_eios):
    w = world
    mod = _stu(app, fake_eios, 7, "Модератор Седьмой")
    w["admin"].patch(f"/api/v1/admin/users/{_uid(db, 7)}/role", json={"role": "moderator"}, headers=CSRF)
    uid = _uid(db, 2)
    calls = [
        ("GET", "/api/v1/admin/users", None),
        ("PATCH", f"/api/v1/admin/users/{uid}/role", {"role": "admin"}),
        ("PATCH", f"/api/v1/admin/users/{uid}/block", {"blocked": True}),
        ("DELETE", f"/api/v1/admin/users/{uid}", None),
        ("POST", "/api/v1/admin/teachers", {"name": "Test Teacher", "department": "d", "role": "r"}),
        ("POST", "/api/v1/admin/announcements", {"title": "t", "content": "c"}),
        ("POST", "/api/v1/admin/faq", {"question": "q", "answer": "a"}),
        ("GET", "/api/v1/admin/associations", None),
        ("POST", "/api/v1/admin/associations", {"name": "Evil club"}),
        ("PUT", f"/api/v1/admin/associations/{w['a']}/leaders/{_uid(db, 2)}", None),
        ("DELETE", f"/api/v1/admin/associations/{w['a']}", None),
        ("POST", "/api/v1/forum/questions/1/pin", None),
    ]
    bad = []
    for who in (w["member"], w["la"], mod):
        for method, url, body in calls:
            r = who.request(method, url, json=body, headers=CSRF)
            if r.status_code < 400 and not (who is mod and url.endswith("/pin")):
                bad.append((method, url, r.status_code))
    anon = TestClient(w["admin"].app)
    for method, url, body in calls:
        r = anon.request(method, url, json=body)
        assert r.status_code in (401, 403), (method, url, r.status_code)
    assert not bad, bad


def test_removed_member_keeps_access_to_tasks_in_review_FINDING(world, db):
    """A member whose card is 'review'/'done' is excluded by the leader; drop_open_work only deletes
    todo/in_progress cards, so the excluded person still reads the task, comments, uploads and downloads files."""
    w = world
    t, att = w["task"], w["att"]
    r = w["rm"].patch(f"/api/v1/tasks/{t}/status", json={"status": "review"}, headers=CSRF)
    assert r.status_code == 200
    r = w["la"].delete(f"/api/v1/associations/{w['a']}/members/{_uid(db, 5)}", headers=CSRF)
    assert r.status_code == 200
    # the membership is really gone
    assert w["rm"].get("/api/v1/associations/mine").json()[0]["status"] == "removed"
    got = w["rm"].get(f"/api/v1/tasks/{t}")
    dl = w["rm"].get(f"/api/v1/attachments/{att}")
    com = w["rm"].post(f"/api/v1/tasks/{t}/comments", json={"text": "still here"}, headers=CSRF)
    up = w["rm"].post(f"/api/v1/tasks/{t}/files?name=x.pdf", content=PDF, headers={**CSRF, "Content-Type": "application/octet-stream"})
    mv = w["rm"].patch(f"/api/v1/tasks/{t}/status", json={"status": "in_progress"}, headers=CSRF)
    print("removed member:", got.status_code, dl.status_code, com.status_code, up.status_code, mv.status_code)
    assert (got.status_code, dl.status_code, com.status_code, up.status_code, mv.status_code) == (200, 200, 201, 201, 200)
    assert got.json()["description"] == "secret plan"
    # contrast: the same person cannot see the association's announcement any more
    assert w["rm"].get(f"/api/v1/associations/{w['a']}/posts").json() == []
    assert w["rm"].get(f"/api/v1/attachments/{w['post_att']}").status_code == 404
    # and a member who LEFT (leave) before handing in loses the card, as designed
    # (contrast case: todo cards are dropped)


def test_leader_of_inactive_association_keeps_partial_control_FINDING(world, db):
    """Deactivating (hiding) an association does not stop its leader from editing/deleting its meetings, posts, tasks."""
    w = world
    a = w["a"]
    r = w["admin"].put(f"/api/v1/admin/associations/{a}", json={"name": "Alpha club", "is_active": False}, headers=CSRF)
    assert r.status_code == 200
    la = w["la"]
    # creation of new things is blocked (404) ...
    assert la.post("/api/v1/tasks", json={"title": "n", "association_id": a, "to_all": True}, headers=CSRF).status_code == 404
    assert la.post(f"/api/v1/associations/{a}/posts", json={"title": "n"}, headers=CSRF).status_code == 404
    # ... but existing objects stay fully manageable
    got = la.get(f"/api/v1/meetings/{w['meeting']}")
    put = la.put(f"/api/v1/meetings/{w['meeting']}", json={"title": "edited", **_window(180)}, headers=CSRF)
    tsk = la.put(f"/api/v1/tasks/{w['task']}", json={"title": "edited task"}, headers=CSRF)
    dpost = la.delete(f"/api/v1/associations/posts/{w['post']}", headers=CSRF)
    print("inactive:", got.status_code, put.status_code, tsk.status_code, dpost.status_code)
    assert (got.status_code, put.status_code, tsk.status_code, dpost.status_code) == (200, 200, 200, 200)


def test_leader_after_admin_removes_leadership_loses_rights_ok(world, db):
    w = world
    w["admin"].delete(f"/api/v1/admin/associations/{w['a']}/leaders/{_uid(db, 1)}", headers=CSRF)
    la = w["la"]
    assert la.put(f"/api/v1/associations/{w['a']}", json={"description": "x"}, headers=CSRF).status_code == 403
    assert la.post("/api/v1/tasks", json={"title": "n", "association_id": w["a"], "to_all": True}, headers=CSRF).status_code == 403
    assert la.delete(f"/api/v1/tasks/{w['task']}", headers=CSRF).status_code in (403, 404)
    # the former leader is a plain member now and still sees his card? he had none: 404 on the task
    assert la.get(f"/api/v1/tasks/{w['task']}").status_code == 404
    # membership in states rejected/left/removed never gives leader rights
    m = db.query(models.Membership).filter_by(user_id=_uid(db, 1), association_id=w["a"]).one()
    for status in ("left", "removed", "rejected", "pending"):
        m.role, m.status = "leader", status
        db.commit()
        assert la.put(f"/api/v1/associations/{w['a']}", json={"description": "x"}, headers=CSRF).status_code == 403, status


def test_mass_assignment_is_ignored_ok(world, db):
    w = world
    me = w["member"].patch("/api/v1/auth/me", json={"vk_url": "vk.com/ivan", "role": "admin", "is_blocked": True,
                                                    "full_name": "Администратор", "auth_source": "local",
                                                    "sdo_id": "1", "id": 1, "email": "a@b.c"}, headers=CSRF)
    assert me.status_code == 200
    u = db.query(models.User).filter_by(id=_uid(db, 2)).one()
    db.refresh(u)
    assert (u.role, u.is_blocked, u.full_name, u.auth_source, u.email) == ("student", False, "Участник Альфа Второй", "eios", None)
    # tasks: created_by_id / status of the card / association in PUT are not settable
    t = w["la"].post("/api/v1/tasks", json={"title": "T2", "association_id": w["b"], "to_all": True}, headers=CSRF)
    assert t.status_code == 403
    mine = w["member"].post("/api/v1/tasks", json={"title": "mine", "created_by_id": 1, "association_id": None,
                                                   "status": "done", "archived_at": "2020-01-01T00:00:00Z"}, headers=CSRF).json()
    assert mine["my_status"] == "todo"
    put = w["la"].put(f"/api/v1/tasks/{w['task']}", json={"title": "x", "association_id": w["b"], "created_by_id": _uid(db, 3)}, headers=CSRF).json()
    assert put["association"]["id"] == w["a"]
    # meetings: association_id / created_by_id in the body are ignored
    m = w["la"].put(f"/api/v1/meetings/{w['meeting']}", json={"title": "x", **_window(60), "association_id": w["b"]}, headers=CSRF).json()
    assert m["association"]["id"] == w["a"]


def test_main_admin_rules_ok_and_no_audit_trail_FINDING(app, fake_eios, db):
    main_admin = login_admin(app)
    admin_id = db.query(models.User).filter_by(username="portal_admin").one().id
    a2 = _stu(app, fake_eios, 1, "Второй Админ")
    victim = _stu(app, fake_eios, 2, "Студент Жертва")
    mod = _stu(app, fake_eios, 3, "Третий Админ")
    uid = lambda n: _uid(db, n)  # noqa: E731
    # grant: only the main admin
    assert main_admin.patch(f"/api/v1/admin/users/{uid(1)}/role", json={"role": "admin"}, headers=CSRF).status_code == 200
    assert a2.patch(f"/api/v1/admin/users/{uid(3)}/role", json={"role": "admin"}, headers=CSRF).status_code == 403
    # a second admin cannot demote / block / delete another admin or the main one, nor himself
    assert main_admin.patch(f"/api/v1/admin/users/{uid(3)}/role", json={"role": "admin"}, headers=CSRF).status_code == 200
    for method, tail, body in (("PATCH", "role", {"role": "student"}), ("PATCH", "block", {"blocked": True}), ("DELETE", "", None)):
        url = f"/api/v1/admin/users/{uid(3)}" + (f"/{tail}" if tail else "")
        assert a2.request(method, url, json=body, headers=CSRF).status_code == 403
        url = f"/api/v1/admin/users/{admin_id}" + (f"/{tail}" if tail else "")
        assert a2.request(method, url, json=body, headers=CSRF).status_code == 400
        url = f"/api/v1/admin/users/{uid(1)}" + (f"/{tail}" if tail else "")
        assert a2.request(method, url, json=body, headers=CSRF).status_code == 400
        assert main_admin.request(method, f"/api/v1/admin/users/{admin_id}" + (f"/{tail}" if tail else ""), json=body, headers=CSRF).status_code == 400
    # a second admin may block/demote plain students and moderators
    assert a2.patch(f"/api/v1/admin/users/{uid(2)}/role", json={"role": "moderator"}, headers=CSRF).status_code == 200
    # revoke by the main admin: effective on the very next request (role is read from the DB each time)
    assert main_admin.patch(f"/api/v1/admin/users/{uid(1)}/role", json={"role": "student"}, headers=CSRF).status_code == 200
    assert a2.get("/api/v1/admin/users").status_code == 403
    # FINDING: no audit trail anywhere (no model/table, nothing logged)
    tables = {t for t in models.Base.metadata.tables} if hasattr(models, "Base") else set()
    from app.db.database import Base
    assert not [t for t in Base.metadata.tables if "audit" in t or "log" in t], Base.metadata.tables.keys()


def test_orphaned_local_admin_cannot_be_removed_after_ADMIN_USERNAME_change_FINDING(app, fake_eios, db):
    """If ADMIN_USERNAME is changed (rotation after a suspected compromise) the OLD local admin row stays admin,
    stays 'protected' (auth_source == local) and nobody can demote/block/delete it from the panel."""
    from app.core import security
    old = models.User(username="old_main_admin", full_name="Old Admin", hashed_password="x", role="admin", auth_source="local")
    db.add(old)
    db.commit()
    main_admin = login_admin(app)
    for method, tail, body in (("PATCH", "role", {"role": "student"}), ("PATCH", "block", {"blocked": True}), ("DELETE", "", None)):
        url = f"/api/v1/admin/users/{old.id}" + (f"/{tail}" if tail else "")
        assert main_admin.request(method, url, json=body, headers=CSRF).status_code == 400
    # and a still-valid token of that account keeps working as the "main administrator"
    tok = security.create_access_token("old_main_admin")
    c = TestClient(app, cookies={security.AUTH_COOKIE_NAME: tok})
    assert c.get("/api/v1/admin/users").status_code == 200
    assert c.get("/api/v1/auth/me").json()["auth_source"] == "local"


def test_admin_reads_other_students_personal_tasks_FINDING(app, fake_eios, db):
    """tasks.can_manage() returns True for every admin, also for PERSONAL tasks (private notes) and their files."""
    s = _stu(app, fake_eios, 1, "Студент Заметки")
    t = s.post("/api/v1/tasks", json={"title": "личная заметка про здоровье", "description": "приватно"}, headers=CSRF).json()
    f = s.post(f"/api/v1/tasks/{t['id']}/files?name=scan.pdf", content=PDF, headers={**CSRF, "Content-Type": "application/octet-stream"}).json()
    s.post(f"/api/v1/tasks/{t['id']}/comments", json={"text": "note to self"}, headers=CSRF)
    admin = login_admin(app)
    other = _stu(app, fake_eios, 2, "Другой Студент")
    assert other.get(f"/api/v1/tasks/{t['id']}").status_code == 404
    r = admin.get(f"/api/v1/tasks/{t['id']}")
    assert r.status_code == 200 and r.json()["description"] == "приватно" and r.json()["comments"]
    assert admin.get(f"/api/v1/attachments/{f['id']}").status_code == 200
    # contrast: manual achievements (also personal) are NOT readable by admin
    ach = s.post("/api/v1/achievements", json={"title": "x", "day": "2026-01-10"}, headers=CSRF).json()
    assert admin.put(f"/api/v1/achievements/{ach['id']}", json={"title": "y", "day": "2026-01-10"}, headers=CSRF).status_code == 404
    assert admin.delete(f"/api/v1/tasks/{t['id']}", headers=CSRF).status_code == 200  # and may delete them


def test_bfla_plain_member_cannot_use_leader_endpoints_ok(world, db):
    """A plain approved member of A: every leader-only call on A's own objects is refused; own-card rules hold."""
    w = world
    a, t, m, p = w["a"], w["task"], w["meeting"], w["post"]
    c = w["member"]
    other = _uid(db, 5)
    calls = [
        ("PUT", f"/api/v1/associations/{a}", {"description": "pwn"}),
        ("POST", f"/api/v1/associations/{a}/members/{other}/decision", {"approve": False}),
        ("DELETE", f"/api/v1/associations/{a}/members/{other}", None),
        ("POST", f"/api/v1/associations/{a}/members/{other}/restore", None),
        ("POST", "/api/v1/tasks", {"title": "x", "association_id": a, "to_all": True}),
        ("PUT", f"/api/v1/tasks/{t}", {"title": "x"}),
        ("DELETE", f"/api/v1/tasks/{t}", None),
        ("PATCH", f"/api/v1/tasks/{t}/status", {"status": "review", "user_id": other}),  # someone else's card
        ("PATCH", f"/api/v1/tasks/{t}/status", {"status": "done"}),                       # 'Готово' is the leader's
        ("PATCH", f"/api/v1/tasks/{t}/managed-archive", {"archived": True}),
        ("DELETE", f"/api/v1/tasks/{t}/assignees/{other}", None),
        ("POST", f"/api/v1/associations/{a}/posts", {"title": "x"}),
        ("DELETE", f"/api/v1/associations/posts/{p}", None),
        ("POST", f"/api/v1/associations/posts/{p}/links", {"url": "https://example.org/x"}),
        ("DELETE", f"/api/v1/attachments/{w['att']}", None),  # file uploaded by the leader
        ("POST", f"/api/v1/associations/{a}/meetings", {"title": "x", **_window(60)}),
        ("PUT", f"/api/v1/meetings/{m}", {"title": "x", **_window(60)}),
        ("DELETE", f"/api/v1/meetings/{m}", None),
        ("PUT", f"/api/v1/meetings/{m}/attendance", {"user_ids": [_uid(db, 2)]}),
    ]
    for method, url, body in calls:
        r = c.request(method, url, json=body, headers=CSRF)
        assert r.status_code in (400, 403, 404), (method, url, r.status_code)
    # contacts/member lists stay empty for a plain member
    d = c.get(f"/api/v1/associations/{a}").json()
    assert d["members"] == [] and d["applications"] == [] and d["removed"] == [] and d["can_manage"] is False
    mt = c.get(f"/api/v1/meetings/{m}").json()
    assert mt["attendance"] == [] and mt["can_manage"] is False
    tk = c.get(f"/api/v1/tasks/{t}").json()
    assert len(tk["assignees"]) == 1 and tk["can_manage"] is False  # only his own card


def test_assignees_see_each_others_handed_in_files_FINDING(world, db):
    """On a task given to everyone each assignee can download files that OTHER assignees attached (their answers)."""
    w = world
    t = w["task"]
    up = w["member"].post(f"/api/v1/tasks/{t}/files?name=my_answer.pdf", content=PDF, headers={**CSRF, "Content-Type": "application/octet-stream"})
    assert up.status_code == 201
    fid = up.json()["id"]
    r = w["rm"].get(f"/api/v1/attachments/{fid}")  # another assignee, not a manager
    assert r.status_code == 200 and r.content == PDF
    names = [a["title"] for a in w["rm"].get(f"/api/v1/tasks/{t}").json()["attachments"]]
    assert "my_answer.pdf" in names and "plan.pdf" in names
    # while an outsider gets nothing
    assert w["outsider"].get(f"/api/v1/attachments/{fid}").status_code == 404


def test_double_submit_of_apply_gives_500_FINDING(world, db, app):
    """Two simultaneous 'apply' requests: both see no row, the second INSERT violates uq_membership_user_association
    and the unhandled IntegrityError surfaces as HTTP 500 instead of 400. (Race: may need a few tries.)"""
    from concurrent.futures import ThreadPoolExecutor
    w = world
    tok = w["outsider"].cookies.get("portal_token")
    codes = []
    for _ in range(8):
        db.query(models.Membership).filter_by(user_id=_uid(db, 4), association_id=w["b"]).delete()
        db.commit()

        def go(_):
            c = TestClient(app, cookies={"portal_token": tok}, raise_server_exceptions=False)
            return c.post(f"/api/v1/associations/{w['b']}/apply", json={}, headers=CSRF).status_code

        with ThreadPoolExecutor(8) as pool:
            codes = list(pool.map(go, range(8)))
        if 500 in codes:
            break
    print("apply codes:", codes)
    assert 500 in codes
