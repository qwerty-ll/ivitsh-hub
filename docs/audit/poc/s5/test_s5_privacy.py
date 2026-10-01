"""S5 / Area E: personal-data observations on a local instance (temp SQLite, fake EIOS, nothing external)."""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, text

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "server", "tests"))

import app.models as models  # noqa: E402
from app.core import security  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.database import Base, engine  # noqa: E402
from conftest import CSRF, login_admin, login_student, add_eios_account  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PD_KEYS = {"full_name", "author_name", "author", "group_number", "group", "vk_url", "max_contact", "username", "user_id",
           "author_id", "email", "created_by", "booked_by", "cancelled_by", "uploaded_by", "eios_group_id", "sdo_id",
           "last_seen_at", "pd_consent_at", "avatar_url", "userpictureurl", "is_blocked"}


def pd_fields(node, path="$", out=None):
    """Collects (path, key) of personal-data keys in a JSON document (list indexes collapsed)."""
    out = set() if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            if k in PD_KEYS and v not in (None, "", 0):
                out.add(f"{path}.{k}")
            pd_fields(v, f"{path}.{k}", out)
    elif isinstance(node, list):
        for v in node:
            pd_fields(v, path + "[]", out)
    return out


# --- E-1: the forum shows full names to the open internet ---------------------------------------------

def test_e1_forum_exposes_full_name_and_user_id_without_signing_in(app, fake_eios, client):
    s = login_student(app, fake_eios, username="24-isbo-010", eios_id="10", full_name="Смирнова Анна Олеговна")
    q = s.post("/api/v1/forum/questions", json={"title": "Тестовый вопрос", "category": "Учеба", "content": "Содержимое вопроса тут"}, headers=CSRF).json()
    s.post(f"/api/v1/forum/questions/{q['id']}/answers", json={"content": "Мой ответ"}, headers=CSRF)
    anon = client  # no cookie
    lst = anon.get("/api/v1/forum/questions")
    ans = anon.get(f"/api/v1/forum/questions/{q['id']}/answers")
    by_author = anon.get(f"/api/v1/forum/questions?author_id={q['author_id']}")
    print("\nE-1 anonymous /forum/questions ->", lst.status_code, {k: lst.json()[0][k] for k in ("author_id", "author_name")})
    print("E-1 anonymous answers ->", ans.status_code, {k: ans.json()[0][k] for k in ("author_id", "author_name")})
    assert lst.status_code == 200 and lst.json()[0]["author_name"] == "Смирнова Анна Олеговна"
    assert ans.json()[0]["author_name"] == "Смирнова Анна Олеговна"
    assert by_author.status_code == 200 and len(by_author.json()) == 1  # author_id enumerates a person's posts


# --- E-2: key list endpoints, personal fields per viewer ---------------------------------------------------

@pytest.fixture
def world(app, fake_eios, db):
    admin = login_admin(app)
    lead = login_student(app, fake_eios, username="24-isbo-021", eios_id="21", full_name="Руководитель Роман Романович", group="23-ИСбо-1")
    member = login_student(app, fake_eios, username="24-isbo-022", eios_id="22", full_name="Участников Игорь Иванович", group="24-ИСбо-1")
    other = login_student(app, fake_eios, username="24-isbo-023", eios_id="23", full_name="Посторонний Пётр Петрович", group="24-ИСбо-2")
    for c, vk, mx in ((lead, "vk.com/lead", "@lead_max"), (member, "vk.com/member", "@member_max")):
        r = c.patch("/api/v1/auth/me", json={"vk_url": vk, "max_contact": mx}, headers=CSRF)
        assert r.status_code == 200, r.text
    ids = {u.username: u.id for u in db.query(models.User)}
    assoc = models.Association(name="Клуб тестов", description="d")
    db.add(assoc)
    db.flush()
    db.add_all([
        models.Membership(user_id=ids["24-isbo-021"], association_id=assoc.id, role="leader", status="approved"),
        models.Membership(user_id=ids["24-isbo-022"], association_id=assoc.id, role="member", status="approved"),
        models.Membership(user_id=ids["24-isbo-023"], association_id=assoc.id, role="member", status="pending", message="возьмите меня"),
    ])
    now = datetime.now(timezone.utc)
    ev = models.Event(scope="association", association_id=assoc.id, created_by_id=ids["24-isbo-021"], title="Прошедшее", starts_at=now - timedelta(days=2),
                      ends_at=now - timedelta(days=2) + timedelta(hours=2))
    db.add(ev)
    db.flush()
    db.add(models.EventRegistration(event_id=ev.id, user_id=ids["24-isbo-022"], role="participant", source="self", attended=True))
    db.add(models.EventFeedback(event_id=ev.id, user_id=ids["24-isbo-022"], rating=2, text="Было скучно"))
    db.add(models.Booking(resource="room", zone="top", starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=1, hours=1),
                          purpose="Встреча", association_id=assoc.id, booked_by_id=ids["24-isbo-021"]))
    db.commit()
    return dict(admin=admin, lead=lead, member=member, other=other, anon=TestClient(app), assoc=assoc.id, event=ev.id, ids=ids)


def test_e2_disclosure_matrix(world):
    w = world
    today = date.today().isoformat()
    admin = w["admin"]
    t = admin.post("/api/v1/tribes/tournaments", json={"title": "T", "starts_on": today, "ends_on": (date.today() + timedelta(days=9)).isoformat(),
                                                       "tribe_names": ["А", "Б"]}, headers=CSRF).json()
    assert admin.post(f"/api/v1/tribes/tournaments/{t['id']}/start", headers=CSRF).status_code == 200
    probes = [
        ("anon", "/api/v1/associations"),
        ("other", f"/api/v1/associations/{w['assoc']}"),
        ("lead", f"/api/v1/associations/{w['assoc']}"),
        ("anon", "/api/v1/forum/questions"),
        ("other", f"/api/v1/events/{w['event']}"),
        ("member", f"/api/v1/events/{w['event']}"),
        ("lead", f"/api/v1/events/{w['event']}"),
        ("other", f"/api/v1/bookings?day={(date.today() + timedelta(days=1)).isoformat()}"),
        ("other", "/api/v1/tribes/current"),
        ("member", "/api/v1/tribes/current"),
        ("other", "/api/v1/auth/me"),
        ("admin", "/api/v1/admin/users"),
    ]
    table = {}
    print()
    for who, url in probes:
        r = w[who].get(url)
        fields = sorted(pd_fields(r.json())) if r.status_code == 200 else []
        table[(who, url)] = (r.status_code, fields)
        print(f"E-2 {who:6s} GET {url.split('?')[0]:34s} -> {r.status_code} {fields}")
    # leaders' name+group are open to the web, contacts only to signed-in users
    anon_assoc = table[("anon", "/api/v1/associations")][1]
    assert "$[].leaders[].full_name" in anon_assoc and "$[].leaders[].group_number" in anon_assoc
    assert not any(f.endswith("vk_url") or f.endswith("max_contact") for f in anon_assoc)
    # an unrelated student sees nothing of the member list
    assert not any("members" in f or "applications" in f for f in table[("other", f"/api/v1/associations/{w['assoc']}")][1])
    # feedback is shown to the leader without names, but only the leader gets it
    lead_event = w["lead"].get(f"/api/v1/events/{w['event']}").json()
    assert lead_event["feedback"]["comments"] == [{"rating": 2, "text": "Было скучно"}]
    assert w["member"].get(f"/api/v1/events/{w['event']}").json()["feedback"] is None
    # no endpoint outside the admin panel returns usernames (EIOS logins), is_blocked, sdo_id, last_seen_at, consent data
    for (who, url), (code, fields) in table.items():
        if who != "admin" and url != "/api/v1/auth/me":
            assert not any(f.split(".")[-1] in {"username", "sdo_id", "last_seen_at", "pd_consent_at", "is_blocked", "eios_group_id", "email"} for f in fields), (who, url, fields)


def test_e2_anonymity_of_feedback_for_a_small_event(world):
    """With one registered person the 'anonymous' comment is attributable by the organizer."""
    lead_event = world["lead"].get(f"/api/v1/events/{world['event']}").json()
    regs = lead_event["registrations"]
    comments = lead_event["feedback"]["comments"]
    print("\nE-2 registrations:", len(regs), "comments:", len(comments))
    assert len(regs) == 1 and len(comments) == 1


# --- E-3: consent: stored once, overwritten at each login, no withdrawal / export endpoint -----------------

def test_e3_consent_is_overwritten_and_there_is_no_withdrawal_or_export(app, fake_eios, db):
    c = login_student(app, fake_eios, username="24-isbo-030", eios_id="30")
    u = db.query(models.User).filter_by(username="24-isbo-030").one()
    first = u.pd_consent_at
    assert u.pd_consent_version == "2026-09-30"
    c.post("/api/v1/auth/logout", headers=CSRF)
    c2 = TestClient(app)
    assert c2.post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-030", "password": "pw"}).status_code == 200
    db.expire_all()
    u = db.query(models.User).filter_by(username="24-isbo-030").one()
    assert u.pd_consent_at >= first  # replaced, no history table
    paths = {(m.upper(), p) for p, v in app.openapi()["paths"].items() for m in v}
    mine = sorted(p for p in paths if "/auth/" in p[1] or "export" in p[1] or "/me" in p[1])
    print("\nE-3 routes touching the account:", mine)
    assert not any(m == "DELETE" and p.endswith("/me") for m, p in paths)
    assert len(paths) > 100
    assert not any("withdraw" in p or "consent" in p or "my-data" in p or p.endswith("/me/export") for _, p in paths)
    # the only deletion path is the administrator's
    assert ("DELETE", "/api/v1/admin/users/{user_id}") in paths


def test_e3_token_session_is_not_rechecked_against_the_consent_version(app, fake_eios, db):
    c = login_student(app, fake_eios, username="24-isbo-031", eios_id="31")
    u = db.query(models.User).filter_by(username="24-isbo-031").one()
    u.pd_consent_version = "2020-01-01"  # as if the policy text changed after the session started
    u.pd_consent_at = None
    db.commit()
    assert c.get("/api/v1/auth/me").status_code == 200  # no re-consent gate
    assert c.get("/api/v1/tasks/my").status_code == 200


# --- E-4: account deletion cascade and files on disk --------------------------------------------------------

def _file(name_ext=".pdf", body=b"%PDF-1.4 test"):
    import uuid
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    name = uuid.uuid4().hex + name_ext
    with open(os.path.join(settings.UPLOAD_DIR, name), "wb") as f:
        f.write(body)
    return name


def test_e4_delete_user_cascade_and_what_stays_behind(app, fake_eios, db):
    admin = login_admin(app)
    leader = login_student(app, fake_eios, username="24-isbo-040", eios_id="40", full_name="Лидер Лев Львович")
    victim = login_student(app, fake_eios, username="24-isbo-041", eios_id="41", full_name="Удаляемый Иван Иванович")
    uid = db.query(models.User).filter_by(username="24-isbo-041").one().id
    lid = db.query(models.User).filter_by(username="24-isbo-040").one().id
    now = datetime.now(timezone.utc)
    assoc = models.Association(name="Клуб удаления", description="d")
    db.add(assoc)
    db.flush()
    db.add_all([models.Membership(user_id=lid, association_id=assoc.id, role="leader", status="approved"),
                models.Membership(user_id=uid, association_id=assoc.id, role="member", status="approved", message="Я Удаляемый Иван, мой тел. +7 900")])
    # forum
    q_mine = models.ForumQuestion(author_id=uid, title="Мой вопрос", content="Содержимое вопроса")
    q_other = models.ForumQuestion(author_id=lid, title="Чужой вопрос", content="Содержимое вопроса 2")
    db.add_all([q_mine, q_other])
    db.flush()
    db.add_all([models.ForumAnswer(question_id=q_other.id, author_id=uid, content="Ответ удаляемого"),
                models.ForumAnswer(question_id=q_mine.id, author_id=lid, content="Ответ другого на мой вопрос"),
                models.Vote(user_id=uid, question_id=q_other.id, vote_type=1)])
    # files: personal task, manual achievement scan, an upload into an association task, an event document
    f_personal, f_scan, f_assoc, f_event = _file(), _file(".png", b"\x89PNG\r\n\x1a\n0"), _file(), _file()
    personal = models.Task(created_by_id=uid, title="Личная задача", description="")
    shared = models.Task(association_id=assoc.id, created_by_id=lid, title="Задача объединения", description="")
    ach = models.ManualAchievement(user_id=uid, title="Хакатон", day=date.today())
    ev = models.Event(scope="association", association_id=assoc.id, created_by_id=uid, title="Событие удаляемого",
                      starts_at=now, ends_at=now + timedelta(hours=1))
    db.add_all([personal, shared, ach, ev])
    db.flush()
    db.add_all([
        models.TaskAssignee(task_id=shared.id, user_id=uid),
        models.TaskComment(task_id=shared.id, author_id=uid, text="Комментарий удаляемого"),
        models.Attachment(task_id=personal.id, kind="file", title="личный.pdf", stored_name=f_personal, size=10, uploaded_by_id=uid),
        models.Attachment(achievement_id=ach.id, kind="file", title="скан Удаляемый Иван.png", stored_name=f_scan, size=10, uploaded_by_id=uid),
        models.Attachment(task_id=shared.id, kind="file", title="Удаляемый Иван паспорт.pdf", stored_name=f_assoc, size=10, uploaded_by_id=uid),
        models.Attachment(event_id=ev.id, kind="file", title="приказ.pdf", stored_name=f_event, size=10, uploaded_by_id=uid),
        models.EventRegistration(event_id=ev.id, user_id=uid), models.EventFeedback(event_id=ev.id, user_id=uid, rating=3, text="отзыв"),
        models.Booking(resource="room", zone="top", starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=1, hours=1),
                       purpose="День рождения Удаляемого Ивана", association_id=assoc.id, booked_by_id=uid),
        models.ShopOrder(user_id=uid, item_title="Футболка", price=10), models.BitsGrant(user_id=uid, amount=5, reason="за что-то"),
        models.SdoCourse(user_id=uid, course_id=5, name="Курс"), models.MeetingAttendance(meeting_id=0, user_id=uid) if False else models.SdoCourse(user_id=uid, course_id=6, name="Курс 2"),
    ])
    db.commit()
    q_mine_id, shared_id, ev_id = q_mine.id, shared.id, ev.id

    r = admin.delete(f"/api/v1/admin/users/{uid}", headers=CSRF)
    assert r.status_code == 200, r.text
    db.expire_all()

    # 1) rows still pointing at the person (by any user-FK column) after deletion
    leftovers = {}
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if any(fk.column.table.name == "users" for fk in col.foreign_keys):
                n = db.execute(text(f'SELECT COUNT(*) FROM "{table.name}" WHERE "{col.name}" = :i'), {"i": uid}).scalar()
                if n:
                    leftovers[f"{table.name}.{col.name}"] = n
    print("\nE-4 rows still referencing the deleted user id:", leftovers)
    assert leftovers == {}

    # 2) rows that belonged to the person but were only detached (SET NULL) and keep personal text
    kept = {
        "attachment (association task) title": [a.title for a in db.query(models.Attachment).filter(models.Attachment.task_id == shared_id)],
        "attachment uploaded_by is NULL": db.query(models.Attachment).filter(models.Attachment.uploaded_by_id.is_(None)).count(),
        "booking purpose": [b.purpose for b in db.query(models.Booking)],
        "event created_by NULL": db.query(models.Event).filter(models.Event.id == ev_id, models.Event.created_by_id.is_(None)).count(),
        "membership rows": db.query(models.Membership).filter(models.Membership.user_id == uid).count(),
        "forum answer of someone else on his question": db.query(models.ForumAnswer).filter(models.ForumAnswer.question_id == q_mine_id).count(),
    }
    print("E-4 detached rows that still carry the person's text:", kept)
    assert kept["booking purpose"] == ["День рождения Удаляемого Ивана"]
    assert kept["attachment (association task) title"] == ["Удаляемый Иван паспорт.pdf"]

    # 3) files on disk
    on_disk = {n for n in os.listdir(settings.UPLOAD_DIR)}
    status = {"personal task file": f_personal in on_disk, "achievement scan": f_scan in on_disk,
              "file in association task": f_assoc in on_disk, "event document": f_event in on_disk}
    print("E-4 files still on disk:", status)
    assert not status["personal task file"] and not status["achievement scan"]
    assert status["file in association task"] and status["event document"]


def test_e4_deleted_account_can_be_recreated_by_next_login_and_consent_is_lost(app, fake_eios, db):
    admin = login_admin(app)
    login_student(app, fake_eios, username="24-isbo-050", eios_id="50")
    uid = db.query(models.User).filter_by(username="24-isbo-050").one().id
    admin.delete(f"/api/v1/admin/users/{uid}", headers=CSRF)
    db.expire_all()
    assert db.query(models.User).filter_by(username="24-isbo-050").first() is None  # the proof of consent went with the row
    again = TestClient(app).post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-050", "password": "pw"})
    assert again.status_code == 200  # nothing remembers that the person asked to be deleted


# --- E-5: retention: RevokedToken and the in-memory limiter ----------------------------------------------------

def test_e5_revoked_tokens_are_purged_only_when_somebody_logs_out(app, fake_eios, db):
    old = models.RevokedToken(jti="old-jti", revoked_at=datetime.now(timezone.utc) - timedelta(days=30))
    db.add(old)
    db.commit()
    # many logins/logouts happen elsewhere... but the stale row stays until the *next* revoke_token call
    assert db.query(models.RevokedToken).count() == 1
    c = login_student(app, fake_eios, username="24-isbo-060", eios_id="60")
    c.post("/api/v1/auth/logout", headers=CSRF)
    db.expire_all()
    left = [r.jti for r in db.query(models.RevokedToken)]
    print("\nE-5 revoked tokens after the next logout:", len(left))
    assert "old-jti" not in left and len(left) == 1


def test_e5_login_log_keeps_whatever_is_typed_in_the_login_field(app, fake_eios, caplog):
    """A person who pastes the password into the login field gets it into the log (EIOS rejects it, the log line stays)."""
    import logging
    with caplog.at_level(logging.WARNING, logger="ivitsh_portal.auth"):
        r = TestClient(app).post("/api/v1/auth/eios-login", json={"consent": True, "username": "MyS3cretPassw0rd", "password": "x"})
    assert r.status_code == 401
    lines = [x.getMessage() for x in caplog.records]
    print("\nE-5 auth log:", lines)
    assert any("MyS3cretPassw0rd" in l for l in lines)


# --- E-6: names from the institute's list and contacts of excluded people --------------------------------------

def test_e6_listed_leader_name_is_public_and_excluded_members_keep_their_contacts_visible(world, db):
    w = world
    bare = models.Association(name="Клуб без руководителя", description="d", leader_hint="Никитина Василиса")
    db.add(bare)
    db.commit()
    anon_list = w["anon"].get("/api/v1/associations").json()
    row = next(a for a in anon_list if a["name"] == "Клуб без руководителя")
    print("\nE-6 anonymous catalog row:", {"listed_leader": row["listed_leader"], "leaders": row["leaders"]})
    assert row["listed_leader"] == "Никитина Василиса"  # a student's name, shown to the open web, from a list kept in git

    # the leader excludes a member: the contacts stay in the leader's 'removed' list
    r = w["lead"].delete(f"/api/v1/associations/{w['assoc']}/members/{w['ids']['24-isbo-022']}", headers=CSRF)
    assert r.status_code == 200
    detail = w["lead"].get(f"/api/v1/associations/{w['assoc']}").json()
    print("E-6 removed list:", [{k: v for k, v in m.items() if k in ("full_name", "vk_url", "max_contact", "status")} for m in detail["removed"]])
    assert detail["removed"][0]["vk_url"] and detail["removed"][0]["max_contact"]
