from datetime import datetime, timedelta, timezone

import pytest

import app.models as models
from app.core.config import settings
from app.db.database import SessionLocal
from app.services import eios, sdo, timetable
from conftest import CSRF, login_admin, login_student

NOW = datetime(2026, 9, 24, 10, 15, tzinfo=timetable.MSK)


def lesson(day, start, end, discipline, room="Б-305", **extra):
    return {"дата": f"{day}T00:00:00", "начало": start, "конец": end, "дисциплина": discipline, "аудитория": room,
            "группа": "24-ИСбо-1", "преподаватель": "Иванов И.И.", "номерПодгруппы": 0, "замена": False, **extra}


def ok(data):
    return {"state": 1, "data": data}


ANSWERS = {
    ("raspGrouplist", frozenset({"year": "2026-2027"}.items())): ok([{"id": 4242, "name": "24-ИСбо-1"}]),
    ("Rasp", frozenset({"year": "2026-2027", "idGroup": 4242}.items())): ok({"rasp": [
        lesson("2026-09-21", "08:30", "10:00", "лек Философия"),
        lesson("2026-09-24", "10:10", "11:40", "лаб Базы данных, п/г 2", room="Б-407"),
        lesson("2026-10-02", "08:30", "10:00", "лек Философия"),
    ]}),
}


@pytest.fixture(autouse=True)
def empty_catalog(app):
    session = SessionLocal()
    session.query(models.Association).delete()
    session.commit()
    session.close()


@pytest.fixture
def fake_timetable(monkeypatch):
    async def fetch_json(endpoint, params, timeout=5.0):
        return ANSWERS.get((endpoint, frozenset(params.items())))

    monkeypatch.setattr(eios, "fetch_json", fetch_json)
    monkeypatch.setattr(timetable, "msk_now", lambda: NOW)


def _student(app, fake_eios, n, full_name, group="24-ИСбо-1"):
    return login_student(app, fake_eios, username=f"24-isbo-{n:03d}", eios_id=str(3000 + n),
                         full_name=full_name, group=group)


def _uid(db, n):
    return db.query(models.User).filter_by(username=f"24-isbo-{n:03d}").one().id


@pytest.fixture
def club(app, fake_eios, db):
    """(association id, leader, member, outsider)"""
    admin = login_admin(app)
    aid = admin.post("/api/v1/admin/associations", json={"name": "Робототехника"}, headers=CSRF).json()["id"]
    leader = _student(app, fake_eios, 1, "Смирнов Макар Олегович")
    admin.put(f"/api/v1/admin/associations/{aid}/leaders/{_uid(db, 1)}", headers=CSRF)
    member = _student(app, fake_eios, 2, "Петрова Анна Сергеевна")
    member.post(f"/api/v1/associations/{aid}/apply", json={}, headers=CSRF)
    leader.post(f"/api/v1/associations/{aid}/members/{_uid(db, 2)}/decision", json={"approve": True}, headers=CSRF)
    outsider = _student(app, fake_eios, 3, "Ли Михаил Юрьевич", group="24-ИСбо-2")
    return aid, leader, member, outsider


def _iso(dt):
    return dt.isoformat()


def test_meetings_are_set_by_leaders_and_seen_by_members(club, db):
    aid, leader, member, outsider = club
    soon = datetime.now(timezone.utc) + timedelta(days=2)
    body = {"title": "  Сбор  команды ", "starts_at": _iso(soon), "ends_at": _iso(soon + timedelta(hours=1)),
            "place": "Б-108", "agenda": "План на семестр"}
    r = leader.post(f"/api/v1/associations/{aid}/meetings", json=body, headers=CSRF)
    assert r.status_code == 201, r.text
    meeting = r.json()
    assert meeting["title"] == "Сбор команды" and meeting["can_manage"]
    # Leaders are members too
    assert [a["full_name"] for a in meeting["attendance"]] == ["Петрова Анна Сергеевна", "Смирнов Макар Олегович"]

    seen = member.get(f"/api/v1/associations/{aid}/meetings").json()
    assert [m["place"] for m in seen] == ["Б-108"] and seen[0]["attendance"] == [] and not seen[0]["can_manage"]
    assert member.post(f"/api/v1/associations/{aid}/meetings", json=body, headers=CSRF).status_code == 403
    assert outsider.get(f"/api/v1/associations/{aid}/meetings").status_code == 403
    assert outsider.get(f"/api/v1/meetings/{meeting['id']}").status_code == 404

    # The end must come after the start
    bad = {**body, "ends_at": _iso(soon - timedelta(minutes=5))}
    assert leader.post(f"/api/v1/associations/{aid}/meetings", json=bad, headers=CSRF).status_code == 422
    # Attendance only once the meeting has started
    r = leader.put(f"/api/v1/meetings/{meeting['id']}/attendance", json={"user_ids": [_uid(db, 2)]}, headers=CSRF)
    assert r.status_code == 400


def test_attendance_and_summary_after_the_meeting(club, db):
    aid, leader, member, outsider = club
    before = datetime.now(timezone.utc) - timedelta(days=1)
    mid = leader.post(f"/api/v1/associations/{aid}/meetings", json={
        "starts_at": _iso(before), "ends_at": _iso(before + timedelta(hours=1))}, headers=CSRF).json()["id"]
    r = leader.put(f"/api/v1/meetings/{mid}/attendance", json={"user_ids": [_uid(db, 3)]}, headers=CSRF)
    assert r.status_code == 400  # not a member
    r = leader.put(f"/api/v1/meetings/{mid}/attendance", json={"user_ids": [_uid(db, 2)]}, headers=CSRF)
    assert r.json()["attended_count"] == 1 and r.json()["attendance"][0]["present"]
    assert member.put(f"/api/v1/meetings/{mid}/attendance", json={"user_ids": []}, headers=CSRF).status_code == 403

    r = leader.put(f"/api/v1/meetings/{mid}", json={
        "title": "", "starts_at": _iso(before), "ends_at": _iso(before + timedelta(hours=1)),
        "summary": "Распределили роли"}, headers=CSRF)
    assert r.json()["title"] == "Собрание" and r.json()["summary"] == "Распределили роли"
    assert member.get(f"/api/v1/associations/{aid}/meetings").json() == []
    assert [m["summary"] for m in member.get(f"/api/v1/associations/{aid}/meetings", params={"past": True}).json()] == ["Распределили роли"]
    assert leader.delete(f"/api/v1/meetings/{mid}", headers=CSRF).status_code == 200
    assert db.query(models.MeetingAttendance).count() == 0


def test_group_homework_is_shared_within_the_group_only(app, fake_eios):
    a = _student(app, fake_eios, 5, "Волкова Дарья Андреевна")
    b = _student(app, fake_eios, 6, "Зайцев Кирилл Павлович", group="24-исбо-1")  # the same group, other case
    other = _student(app, fake_eios, 7, "Орлов Иван Петрович", group="24-ИСбо-2")
    r = a.post("/api/v1/homework", json={"subject": "Базы данных", "text": "Лаба 3, отчёт в СДО",
                                          "due_at": "2026-10-01T23:59:00+03:00"}, headers=CSRF)
    assert r.status_code == 201, r.text
    hw = r.json()
    assert hw["can_edit"] and hw["due_at"] == "2026-10-01T20:59:00+00:00"
    a.post("/api/v1/homework", json={"text": "Взять зачётку в пятницу"}, headers=CSRF)

    seen = b.get("/api/v1/homework").json()
    assert [h["subject"] for h in seen] == ["Базы данных", ""]  # the deadline first, then notes
    assert not seen[0]["can_edit"]
    assert b.put(f"/api/v1/homework/{hw['id']}", json={"text": "x"}, headers=CSRF).status_code == 403
    assert other.get("/api/v1/homework").json() == []
    assert other.delete(f"/api/v1/homework/{hw['id']}", headers=CSRF).status_code == 404
    assert a.post("/api/v1/homework", json={"text": "   "}, headers=CSRF).status_code == 422

    r = a.put(f"/api/v1/homework/{hw['id']}", json={"subject": "БД", "text": "Лаба 3 и 4"}, headers=CSRF)
    assert r.json()["updated_at"] and r.json()["due_at"] is None
    assert a.delete(f"/api/v1/homework/{hw['id']}", headers=CSRF).status_code == 200


def test_calendar_puts_everything_together(club, db, fake_timetable):
    aid, leader, member, _ = club
    db.add(models.SdoCourse(user_id=_uid(db, 2), course_id=4321, name="Базы данных (2026-2027)"))
    db.commit()
    leader.post(f"/api/v1/associations/{aid}/meetings", json={
        "title": "Сбор", "starts_at": "2026-09-23T18:00:00+03:00", "ends_at": "2026-09-23T19:30:00+03:00",
        "place": "Б-108"}, headers=CSRF)
    member.post("/api/v1/tasks", json={"title": "Эссе", "color": "pink", "due_at": "2026-09-25T12:00:00+03:00"}, headers=CSRF)
    member.post("/api/v1/tasks", json={"title": "Потом", "due_at": "2026-10-20T12:00:00+03:00"}, headers=CSRF)
    member.post("/api/v1/homework", json={"subject": "Философия", "text": "Конспект",
                                          "due_at": "2026-09-27T00:00:00+03:00"}, headers=CSRF)

    r = member.get("/api/v1/calendar", params={"start": "2026-09-21", "days": 7})
    assert r.status_code == 200, r.text
    cal = r.json()
    assert cal["lessons"] == "ok" and cal["group"] == "24-ИСбо-1"
    assert [(i["type"], i["title"]) for i in cal["items"]] == [
        ("lesson", "Философия"), ("meeting", "Сбор"), ("lesson", "Базы данных"),
        ("task", "Эссе"), ("homework", "Философия"),
    ]
    db_lesson = cal["items"][2]
    assert db_lesson["subgroup"] == 2 and db_lesson["kind"] == "лабораторная" and db_lesson["place"] == "Б-407"
    assert db_lesson["course"]["url"].endswith("/course/view.php?id=4321")
    assert cal["items"][0]["course"] is None
    assert cal["items"][0]["starts_at"] == "2026-09-21T08:30:00+03:00"
    assert cal["items"][3]["color"] == "pink" and cal["items"][3]["status"] == "todo"

    # The leader sees the meeting, not the member's own tasks and homework
    other = leader.get("/api/v1/calendar", params={"start": "2026-09-21"}).json()
    assert [i["type"] for i in other["items"]] == ["lesson", "meeting", "lesson", "homework"]
    assert member.get("/api/v1/calendar", params={"start": "2026-09-21", "days": 60}).status_code == 422
    assert member.get("/api/v1/calendar/courses").json()[0]["name"] == "Базы данных (2026-2027)"


def test_calendar_without_a_group_or_eios(app, fake_eios, monkeypatch):
    admin = login_admin(app)
    admin.patch("/api/v1/auth/me", json={"group_number": ""}, headers=CSRF)
    c = _student(app, fake_eios, 8, "Карпов Олег Игоревич", group="99-НЕТ-1")

    async def down(endpoint, params, timeout=5.0):
        return None

    monkeypatch.setattr(eios, "fetch_json", down)
    assert c.get("/api/v1/calendar", params={"start": "2026-09-21"}).json()["lessons"] == "unavailable"
    monkeypatch.setattr(eios, "fetch_json", lambda *a, **k: _answer(ANSWERS, *a))
    assert c.get("/api/v1/calendar", params={"start": "2026-09-21"}).json()["lessons"] == "no_group"


async def _answer(answers, endpoint, params, timeout=5.0):
    return answers.get((endpoint, frozenset(params.items())))


def test_sdo_courses_refresh_at_sign_in(app, fake_eios, monkeypatch, db):
    seen = []

    async def fetch_courses(username, password):
        seen.append((username, password))
        return [(4321, "Базы данных"), (77, "Философия")]

    monkeypatch.setattr(settings, "SDO_BASE_URL", "https://sdo.example")
    monkeypatch.setattr(sdo, "fetch_courses", fetch_courses)
    c = _student(app, fake_eios, 9, "Белова Ирина Олеговна")
    assert seen == [("24-isbo-009", "pw")]
    courses = c.get("/api/v1/calendar/courses").json()
    assert [x["name"] for x in courses] == ["Базы данных", "Философия"]
    assert courses[0]["url"] == "https://sdo.example/course/view.php?id=4321"
    assert db.query(models.User).filter_by(username="24-isbo-009").one().sdo_synced_at

    # SDO down: the old list stays, the sign-in still works
    async def broken(username, password):
        return None

    monkeypatch.setattr(sdo, "fetch_courses", broken)
    c = _student(app, fake_eios, 9, "Белова Ирина Олеговна")
    assert len(c.get("/api/v1/calendar/courses").json()) == 2


def test_course_list_parsing_and_matching():
    parsed = sdo.parse_courses([
        {"id": 12, "fullname": "Базы данных (2026-2027)"},
        {"id": 13, "fullname": "Скрытый", "hidden": 1},
        {"id": 1, "fullname": "Главная страница"},
        {"id": "x", "fullname": "Мусор"},
        {"id": 14, "fullname": "<b>Философия</b> &amp; логика"},
    ])
    assert parsed == [(12, "Базы данных (2026-2027)"), (14, "Философия & логика")]
    assert sdo.parse_courses({"exception": "x"}) == []
    courses = [(1, "Базы данных (2026-2027)"), (2, "Программирование на Python. Часть 1"), (3, "Английский язык")]
    assert sdo.match_course("Базы данных", courses)[0] == 1
    assert sdo.match_course("Программирование на Python", courses)[0] == 2
    assert sdo.match_course("Английский", courses)[0] == 3
    assert sdo.match_course("Базы", courses) is None  # too short to guess
    assert sdo.match_course("Физкультура", courses) is None
