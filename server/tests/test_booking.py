from datetime import datetime, timedelta

import pytest

import app.models as models
from app.db.database import SessionLocal
from app.services import timetable
from conftest import CSRF, login_admin, login_student


@pytest.fixture(autouse=True)
def empty_catalog(app):
    session = SessionLocal()
    session.query(models.Association).delete()
    session.commit()
    session.close()


DAY = (timetable.msk_now() + timedelta(days=2)).date()


def at(hm, day=DAY):
    return f"{day.isoformat()}T{hm}:00+03:00"


def _uid(db, n):
    return db.query(models.User).filter_by(username=f"24-isbo-{n:03d}").one().id


@pytest.fixture
def people(app, fake_eios, db):
    """(admin, association id, leader, other leader's association id, other leader, student)"""
    admin = login_admin(app)
    a1 = admin.post("/api/v1/admin/associations", json={"name": "Медиацентр"}, headers=CSRF).json()["id"]
    a2 = admin.post("/api/v1/admin/associations", json={"name": "Робототехника"}, headers=CSRF).json()["id"]
    leader = login_student(app, fake_eios, username="24-isbo-001", eios_id="501", full_name="Смирнов Макар Олегович")
    other = login_student(app, fake_eios, username="24-isbo-002", eios_id="502", full_name="Петрова Анна Сергеевна")
    student = login_student(app, fake_eios, username="24-isbo-003", eios_id="503", full_name="Ли Михаил Юрьевич")
    admin.put(f"/api/v1/admin/associations/{a1}/leaders/{_uid(db, 1)}", headers=CSRF)
    admin.put(f"/api/v1/admin/associations/{a2}/leaders/{_uid(db, 2)}", headers=CSRF)
    return admin, a1, leader, a2, other, student


def book(client, **data):
    return client.post("/api/v1/bookings", json=data, headers=CSRF)


def test_room_zones_collide_with_the_whole_room(people):
    admin, a1, leader, a2, other, student = people
    r = book(leader, resource="room", zone="top", starts_at=at("14:00"), ends_at=at("16:00"), association_id=a1, purpose="Съёмка")
    assert r.status_code == 201, r.text
    assert r.json()["association"]["name"] == "Медиацентр" and r.json()["can_cancel"]
    # The lower part is free at the same time; the whole room and the upper part are not
    assert book(other, resource="room", zone="bottom", starts_at=at("15:00"), ends_at=at("17:00"), association_id=a2).status_code == 201
    r = book(other, resource="room", zone="whole", starts_at=at("15:50"), ends_at=at("18:00"), association_id=a2)
    assert r.status_code == 409 and "с 14:00 до 16:00 (Медиацентр)" in r.json()["detail"]
    assert book(other, resource="room", zone="top", starts_at=at("15:55"), ends_at=at("16:30"), association_id=a2).status_code == 409
    # Back to back is fine
    assert book(other, resource="room", zone="top", starts_at=at("16:00"), ends_at=at("16:45"), association_id=a2).status_code == 201
    assert book(other, resource="room", zone="whole", starts_at=at("17:00"), ends_at=at("18:00"), association_id=a2).status_code == 201
    assert book(leader, resource="room", zone="bottom", starts_at=at("17:30"), ends_at=at("18:30"), association_id=a1).status_code == 409
    day = student.get("/api/v1/bookings", params={"day": DAY.isoformat()}).json()
    assert day["can_book"] is False and day["laptops_total"] == 5 and len(day["items"]) == 4


def test_laptops_never_exceed_five_at_once(people):
    admin, a1, leader, a2, other, student = people
    assert book(leader, resource="laptops", laptops=3, starts_at=at("10:00"), ends_at=at("12:00"), association_id=a1).status_code == 201
    assert book(other, resource="laptops", laptops=2, starts_at=at("11:00"), ends_at=at("13:00"), association_id=a2).status_code == 201
    r = book(other, resource="laptops", laptops=1, starts_at=at("11:30"), ends_at=at("11:45"), association_id=a2)
    assert r.status_code == 409 and "свободно ноутбуков: 0 из 5" in r.json()["detail"]
    # 3 are back at 12:00: two separate bookings overlapping the new one do not add up
    assert book(other, resource="laptops", laptops=3, starts_at=at("12:00"), ends_at=at("14:00"), association_id=a2).status_code == 201
    assert book(leader, resource="laptops", laptops=2, starts_at=at("09:00"), ends_at=at("10:30"), association_id=a1).status_code == 201
    assert book(leader, resource="laptops", laptops=6, starts_at=at("15:00"), ends_at=at("16:00"), association_id=a1).status_code == 400


def test_hours_step_and_rights(people):
    admin, a1, leader, a2, other, student = people
    ok = dict(resource="room", zone="whole", association_id=a1)
    assert book(leader, starts_at=at("07:30"), ends_at=at("09:00"), **ok).json()["detail"].startswith("Коворкинг работает с 08:00 до 21:00")
    assert book(leader, starts_at=at("20:00"), ends_at=at("21:30"), **ok).status_code == 400
    assert "шагом 5 минут" in book(leader, starts_at=at("10:03"), ends_at=at("11:00"), **ok).json()["detail"]
    assert book(leader, starts_at=at("10:00"), ends_at=at("10:10"), **ok).status_code == 400
    yesterday = DAY - timedelta(days=3)
    assert book(leader, starts_at=at("10:00", yesterday), ends_at=at("11:00", yesterday), **ok).status_code == 400
    # A flexible step: 08:05–20:55 is fine
    assert book(leader, starts_at=at("08:05"), ends_at=at("08:50"), **ok).status_code == 201
    assert book(student, starts_at=at("12:00"), ends_at=at("13:00"), **ok).status_code == 403
    assert book(leader, starts_at=at("12:00"), ends_at=at("13:00"), resource="room", zone="top", association_id=a2).status_code == 403
    assert book(leader, starts_at=at("12:00"), ends_at=at("13:00"), resource="room", zone="top").status_code == 400
    # The administration books without an association
    r = book(admin, starts_at=at("13:00"), ends_at=at("14:00"), resource="room", zone="whole", purpose="Совет института")
    assert r.status_code == 201 and r.json()["association"] is None


def test_cancelling(people):
    admin, a1, leader, a2, other, student = people
    bid = book(leader, resource="room", zone="whole", starts_at=at("10:00"), ends_at=at("12:00"), association_id=a1).json()["id"]
    assert other.post(f"/api/v1/bookings/{bid}/cancel", json={}, headers=CSRF).status_code == 403
    r = admin.post(f"/api/v1/bookings/{bid}/cancel", json={"reason": "Проверка пожарной безопасности"}, headers=CSRF)
    assert r.json()["cancelled_by"] == "Администратор ИВИТШ КГУ"
    # The slot is free again; the author sees the cancellation and the reason
    assert book(other, resource="room", zone="top", starts_at=at("10:00"), ends_at=at("11:00"), association_id=a2).status_code == 201
    mine = leader.get("/api/v1/bookings/mine").json()
    assert [(b["cancel_reason"], b["can_cancel"]) for b in mine] == [("Проверка пожарной безопасности", False)]
    assert [b["id"] for b in leader.get("/api/v1/bookings", params={"day": DAY.isoformat()}).json()["items"]] != [bid]


def test_my_bookings_in_the_calendar(people):
    admin, a1, leader, a2, other, student = people
    book(leader, resource="laptops", laptops=2, starts_at=at("10:00"), ends_at=at("12:00"), association_id=a1)
    items = leader.get("/api/v1/calendar", params={"start": DAY.isoformat(), "days": 1}).json()["items"]
    assert [(i["type"], i["title"]) for i in items if i["type"] == "booking"] == [("booking", "Ноутбуки: 2")]
    assert [i for i in other.get("/api/v1/calendar", params={"start": DAY.isoformat(), "days": 1}).json()["items"] if i["type"] == "booking"] == []


def test_a_finished_booking_cannot_be_cancelled(people, db):
    admin, a1, leader, a2, other, student = people
    from datetime import timezone
    past = datetime.now(timezone.utc) - timedelta(days=1)
    b = models.Booking(resource="room", zone="top", starts_at=past, ends_at=past + timedelta(hours=1),
                       association_id=a1, booked_by_id=_uid(db, 1))
    db.add(b)
    db.commit()
    assert leader.post(f"/api/v1/bookings/{b.id}/cancel", json={}, headers=CSRF).status_code == 400
