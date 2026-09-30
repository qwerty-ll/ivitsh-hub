from datetime import date, datetime, timedelta, timezone

import pytest

import app.models as models
from app.db.database import SessionLocal
from app.services import tribes as tribes_service
from conftest import CSRF, login_admin, login_student

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


@pytest.fixture(autouse=True)
def empty_catalog(app):
    session = SessionLocal()
    session.query(models.Association).delete()
    session.commit()
    session.close()
    tribes_service.clear_cache()


def _students(app, fake_eios, n, group="24-ИСбо-1", start=1):
    return [login_student(app, fake_eios, username=f"24-isbo-{i:03d}", eios_id=str(8000 + i),
                          full_name=f"Студент{chr(1040 + i % 30)} Имя Отчество", group=group)
            for i in range(start, start + n)]


def _tournament(admin, **extra):
    today = date.today()
    body = {"title": "Осенний турнир", "starts_on": (today - timedelta(days=1)).isoformat(),
            "ends_on": (today + timedelta(days=30)).isoformat(), "tribe_names": ["Альфа", "Бета", "Гамма"], **extra}
    r = admin.post("/api/v1/tribes/tournaments", json=body, headers=CSRF)
    assert r.status_code == 201, r.text
    return r.json()


def test_students_split_into_equal_mixed_tribes(app, fake_eios, db):
    admin = login_admin(app)
    _students(app, fake_eios, 7, group="24-ИСбо-1")
    _students(app, fake_eios, 4, group="25-ИБбо-1", start=20)
    t = _tournament(admin)
    assert t["status"] == "draft"
    r = admin.post(f"/api/v1/tribes/tournaments/{t['id']}/start", headers=CSRF)
    assert r.status_code == 200, r.text
    sizes = sorted(tr["members"] for tr in r.json()["tribes"])
    assert sizes == [3, 4, 4] and sum(sizes) == 11
    # Every group is spread: no tribe has more than its fair share of one group (±1)
    for tribe in db.query(models.Tribe).all():
        groups = [m.user.group_number for m in tribe.members]
        assert groups.count("25-ИБбо-1") in (1, 2)
    # Only one tournament at a time
    t2 = _tournament(admin, title="Второй")
    assert admin.post(f"/api/v1/tribes/tournaments/{t2['id']}/start", headers=CSRF).status_code == 409


def test_newcomers_join_the_smallest_tribe_and_students_see_the_standings(app, fake_eios, db):
    admin = login_admin(app)
    _students(app, fake_eios, 4)
    t = _tournament(admin, tribe_names=["Альфа", "Бета"])
    admin.post(f"/api/v1/tribes/tournaments/{t['id']}/start", headers=CSRF)
    late = login_student(app, fake_eios, username="24-isbo-050", eios_id="8050", full_name="Поздний Пётр Петрович")
    view = late.get("/api/v1/tribes/current").json()["tournament"]
    assert view["my_tribe_id"] is not None and sorted(tr["members"] for tr in view["tribes"]) == [2, 3]
    assert not view["can_manage"]
    # Nobody has points yet: every tribe shares the first place
    assert [tr["rank"] for tr in view["tribes"]] == [1, 1]
    # Students cannot run it
    assert late.post(f"/api/v1/tribes/tournaments/{t['id']}/finish", headers=CSRF).status_code == 403


def test_awards_penalties_and_prizes(app, fake_eios, db):
    admin = login_admin(app)
    students = _students(app, fake_eios, 4)
    t = _tournament(admin, tribe_names=["Альфа", "Бета"], prize_1=50, prize_2=20)
    started = admin.post(f"/api/v1/tribes/tournaments/{t['id']}/start", headers=CSRF).json()
    a, b = started["tribes"]
    r = admin.post(f"/api/v1/tribes/{a['id']}/awards", json={"points": 100, "reason": "Победа в хакатоне"}, headers=CSRF)
    admin.post(f"/api/v1/tribes/{b['id']}/awards", json={"points": -10, "reason": "Шум в коворкинге"}, headers=CSRF)
    view = r.json()
    assert view["tribes"][0]["name"] == a["name"] and view["tribes"][0]["points"] == 100
    assert students[0].post(f"/api/v1/tribes/{a['id']}/awards", json={"points": 5, "reason": "x"}, headers=CSRF).status_code == 403

    done = admin.post(f"/api/v1/tribes/tournaments/{t['id']}/finish", headers=CSRF).json()
    assert done["status"] == "finished" and [x["rank"] for x in done["tribes"]] == [1, 2]
    winners = {m.user_id for m in db.query(models.TribeMember).filter_by(tribe_id=a["id"])}
    grants = db.query(models.BitsGrant).all()
    assert {g.user_id for g in grants if g.amount == 50} == winners and len(grants) == 4
    past = students[0].get("/api/v1/tribes/tournaments").json()
    assert past[0]["winner"]["name"] == a["name"]
    # Finished: no more awards
    assert admin.post(f"/api/v1/tribes/{a['id']}/awards", json={"points": 5, "reason": "x"}, headers=CSRF).status_code == 400


def test_shop_spends_bits_with_limits_and_refunds(app, fake_eios, db):
    admin = login_admin(app)
    buyer, other = _students(app, fake_eios, 2)
    uid = db.query(models.User).filter_by(username="24-isbo-001").one().id
    item = admin.post("/api/v1/shop/items", json={"title": "Стикерпак ИВИТШ", "price": 30, "stock": 1, "per_user_limit": 1}, headers=CSRF).json()
    hoodie = admin.post("/api/v1/shop/items", json={"title": "Худи", "price": 500}, headers=CSRF).json()
    assert buyer.post(f"/api/v1/shop/items/{item['id']}/buy", headers=CSRF).json()["detail"] == "Не хватает 30 бит"
    assert buyer.post("/api/v1/bits/grants", json={"user_id": uid, "amount": 100, "reason": "x"}, headers=CSRF).status_code == 403
    admin.post("/api/v1/bits/grants", json={"user_id": uid, "amount": 100, "reason": "Призёр олимпиады"}, headers=CSRF)

    r = buyer.post(f"/api/v1/shop/items/{item['id']}/buy", headers=CSRF)
    assert r.status_code == 200 and r.json()["balance"]["available"] == 70
    assert buyer.post(f"/api/v1/shop/items/{item['id']}/buy", headers=CSRF).status_code == 409  # sold out / limit
    assert buyer.post(f"/api/v1/shop/items/{hoodie['id']}/buy", headers=CSRF).json()["detail"] == "Не хватает 430 бит"
    shop = buyer.get("/api/v1/shop").json()
    assert shop["orders"][0]["status"] == "new" and shop["grants"][0]["reason"] == "Призёр олимпиады"
    oid = shop["orders"][0]["id"]
    # Cancelling gives the bits and the stock back
    assert buyer.post(f"/api/v1/shop/orders/{oid}/cancel", headers=CSRF).json()["balance"]["available"] == 100
    assert db.query(models.ShopItem).filter_by(id=item["id"]).one().stock == 1
    oid = buyer.post(f"/api/v1/shop/items/{item['id']}/buy", headers=CSRF).json()["order"]["id"]
    # The administration prepares and hands it out; then it is closed
    assert admin.patch(f"/api/v1/shop/orders/{oid}", json={"status": "ready", "comment": "Заберите в Б-209"}, headers=CSRF).json()["status_text"] == "Готов к выдаче"
    assert buyer.post(f"/api/v1/shop/orders/{oid}/cancel", headers=CSRF).status_code == 400
    admin.patch(f"/api/v1/shop/orders/{oid}", json={"status": "issued"}, headers=CSRF)
    assert admin.patch(f"/api/v1/shop/orders/{oid}", json={"status": "cancelled"}, headers=CSRF).status_code == 400
    orders = admin.get("/api/v1/shop/admin", params={"status": "all"}).json()["orders"]
    assert orders[0]["user"]["full_name"] and orders[0]["status"] == "issued"
    # A bought item is hidden, not deleted
    assert admin.delete(f"/api/v1/shop/items/{item['id']}", headers=CSRF).json() == {"hidden": True}
    assert [i["title"] for i in other.get("/api/v1/shop").json()["items"]] == ["Худи"]


def test_shop_pictures(app, fake_eios):
    admin = login_admin(app)
    item = admin.post("/api/v1/shop/items", json={"title": "Кружка", "price": 40}, headers=CSRF).json()
    assert admin.post(f"/api/v1/shop/items/{item['id']}/image", params={"name": "doc.pdf"}, content=b"%PDF-1.4", headers=CSRF).status_code == 415
    r = admin.post(f"/api/v1/shop/items/{item['id']}/image", params={"name": "mug.png"}, content=PNG, headers=CSRF)
    assert r.status_code == 200 and r.json()["image"]
    from fastapi.testclient import TestClient
    assert TestClient(app).get(f"/api/v1/shop/items/{item['id']}/image").content == PNG
