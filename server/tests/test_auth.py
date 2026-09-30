import asyncio
import base64
import json

import httpx
from fastapi.testclient import TestClient

import app.models as models
from app.core import security
from app.routers import auth
from app.services import eios
from conftest import CSRF, add_eios_account, login_admin, login_student


def test_admin_login_sets_httponly_cookie_and_returns_no_token(client):
    r = client.post("/api/v1/auth/admin-login", json={"username": "portal_admin", "password": "Adm1n-Test-Password!"})
    assert r.status_code == 200
    assert "access_token" not in r.json()
    cookie = r.headers["set-cookie"]
    assert "portal_token=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert client.get("/api/v1/auth/me").json()["role"] == "admin"


def test_admin_login_is_rate_limited(client):
    for _ in range(5):
        r = client.post("/api/v1/auth/admin-login", json={"username": "portal_admin", "password": "wrong"})
        assert r.status_code == 401
    r = client.post("/api/v1/auth/admin-login", json={"username": "portal_admin", "password": "Adm1n-Test-Password!"})
    assert r.status_code == 429


def test_eios_login_creates_student_bound_to_eios_id(app, fake_eios, db):
    c = login_student(app, fake_eios, "24-ISBO-001", eios_id="555")
    me = c.get("/api/v1/auth/me").json()
    assert me["username"] == "24-isbo-001"
    assert me["full_name"] == "Иванов Иван Иванович"
    user = db.query(models.User).filter_by(username="24-isbo-001").one()
    assert user.sdo_id == "555" and user.auth_source == "eios"


def test_eios_avatar_is_kept_for_later_page_loads(app, fake_eios):
    photo = "https://sdo.kosgos.ru/pluginfile.php/5/user/icon/f1"
    c = login_student(app, fake_eios, "24-isbo-001", avatar_url=photo)
    # /auth/me runs on every page load; it must still carry the EIOS picture
    assert c.get("/api/v1/auth/me").json()["userpictureurl"] == photo
    # A later login without a picture in the EIOS reply keeps the saved one
    c = login_student(app, fake_eios, "24-isbo-001", avatar_url=None)
    assert c.get("/api/v1/auth/me").json()["userpictureurl"] == photo


def test_eios_avatar_must_be_a_web_link(app, fake_eios):
    c = login_student(app, fake_eios, "24-isbo-001", avatar_url="javascript:alert(1)")
    assert c.get("/api/v1/auth/me").json()["userpictureurl"] is None


def test_eios_login_is_case_insensitive_for_existing_accounts(app, fake_eios, db):
    login_student(app, fake_eios, "24-isbo-001")
    login_student(app, fake_eios, "24-ISBO-001")
    assert db.query(models.User).count() == 1


def test_eios_login_rejects_wrong_password_and_rate_limits(client, fake_eios):
    add_eios_account(fake_eios, "24-isbo-002", password="right")
    for _ in range(5):
        assert client.post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-002", "password": "bad"}).status_code == 401
    r = client.post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-002", "password": "right"})
    assert r.status_code == 429


def test_eios_login_cannot_reach_local_admin(app, client, fake_eios):
    login_admin(app)
    accounts, calls = fake_eios
    add_eios_account(fake_eios, "portal_admin")
    r = client.post("/api/v1/auth/eios-login", json={"consent": True, "username": "portal_admin", "password": "pw"})
    assert r.status_code == 401
    assert calls == []


def test_admin_login_takes_over_an_old_account_never_bound_to_eios(app, client, db):
    # Earlier portal versions left such rows; migration 0002 marked them "eios"
    db.add(models.User(username="Portal_Admin", full_name="Администратор", hashed_password=security.get_password_hash("old"),
                       role="student", auth_source="eios"))
    db.commit()
    r = client.post("/api/v1/auth/admin-login", json={"username": "portal_admin", "password": "Adm1n-Test-Password!"})
    assert r.status_code == 200, r.text
    db.expire_all()
    admin = db.query(models.User).filter(models.User.username == "Portal_Admin").one()
    assert (admin.role, admin.auth_source) == ("admin", "local")
    # Its old password no longer opens the admin panel
    assert TestClient(app).post("/api/v1/auth/admin-login", json={"username": "portal_admin", "password": "old"}).status_code == 401


def test_admin_login_never_takes_over_an_eios_student(app, client, fake_eios, db):
    login_student(app, fake_eios, "portal_admin_x", eios_id="77")
    student = db.query(models.User).filter(models.User.username == "portal_admin_x").one()
    student.username = "portal_admin"
    db.commit()
    r = client.post("/api/v1/auth/admin-login", json={"username": "portal_admin", "password": "Adm1n-Test-Password!"})
    assert r.status_code == 409
    db.expire_all()
    assert db.query(models.User).filter(models.User.username == "portal_admin").one().role == "student"


def test_eios_login_rejects_different_eios_identity(app, client, fake_eios):
    login_student(app, fake_eios, "24-isbo-003", eios_id="1")
    add_eios_account(fake_eios, "24-isbo-003", eios_id="2")
    r = client.post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-003", "password": "pw"})
    assert r.status_code == 409


def test_eios_unavailable_returns_503(client, monkeypatch):
    async def down(username, password):
        raise eios.EiosUnavailable()
    monkeypatch.setattr(eios, "authenticate", down)
    r = client.post("/api/v1/auth/eios-login", json={"consent": True, "username": "x", "password": "y"})
    assert r.status_code == 503


def test_logout_revokes_token(app, fake_eios):
    c = login_student(app, fake_eios)
    token = c.cookies.get(security.AUTH_COOKIE_NAME)
    assert c.post("/api/v1/auth/logout", headers=CSRF).status_code == 200
    stolen = TestClient(app)
    stolen.cookies.set(security.AUTH_COOKIE_NAME, token)
    assert stolen.get("/api/v1/auth/me").status_code == 401


def test_cookie_writes_require_csrf_header(app, fake_eios):
    c = login_student(app, fake_eios)
    body = {"title": "Где столовая?", "category": "Учеба", "content": "Подскажите, где поесть рядом"}
    assert c.post("/api/v1/forum/questions", json=body).status_code == 403
    assert c.post("/api/v1/forum/questions", json=body, headers=CSRF).status_code == 200


def test_eios_group_and_its_timetable_id_are_saved(app, fake_eios, db):
    c = login_student(app, fake_eios, group="24-ИСбо-1", group_id=4242)
    me = c.get("/api/v1/auth/me").json()
    assert me["group_number"] == "24-ИСбо-1" and me["eios_group_id"] == 4242
    # A group EIOS confirmed decides group homework and group enrollment: not edited by hand
    r = c.patch("/api/v1/auth/me", json={"group_number": "25-ИВТбо-1"}, headers=CSRF)
    assert r.status_code == 400
    assert c.get("/api/v1/auth/me").json()["group_number"] == "24-ИСбо-1"


def test_full_name_is_not_user_editable(app, fake_eios):
    c = login_student(app, fake_eios)
    r = c.patch("/api/v1/auth/me", json={"full_name": "Администратор ИВИТШ", "group_number": "25-ИВТбо-1"}, headers=CSRF)
    assert r.status_code == 200
    assert r.json()["full_name"] == "Иванов Иван Иванович"
    assert r.json()["group_number"] == "25-ИВТбо-1"


def test_password_hashing_rejects_legacy_sha256():
    hashed = security.get_password_hash("secret-password")
    assert security.verify_password("secret-password", hashed)
    assert not security.verify_password("wrong", hashed)
    legacy = "2bb80d537b1da3e38bd30361aa855686bde0eacd7162fef6a25fe97bf527a25b"  # sha256("secret")
    assert not security.verify_password("secret", legacy)


def test_parse_auth_response():
    ok = {"state": 1, "accessToken": "t", "data": {"user": {"userID": 7, "shortFIO": "Иванов И. И."}}}
    identity = eios.parse_auth_response(ok)
    assert identity.eios_id == "7" and identity.full_name == "Иванов И. И."
    assert eios.parse_auth_response({"state": 0, "accessToken": "t", "data": {"user": {"userID": 7}}}) is None
    assert eios.parse_auth_response({"data": {"user": {"userID": 7}}}) is None
    assert eios.parse_auth_response({"state": 1}) is None
    assert eios.parse_auth_response("error") is None


def _jwt(claims):
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{body}.signature"


_CLAIMS = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/"
TOKEN = _jwt({_CLAIMS + "name": "student@example.com", _CLAIMS + "surname": "Иванов И. И.", _CLAIMS + "sid": "-12345"})
TOKENAUTH_OK = {"state": 1, "msg": "", "data": {"data": {
    "userName": "student@example.com", "accessToken": TOKEN, "refreshToken": "r", "id": -12345, "expiresIn": 10980,
}}}
_RealAsyncClient = httpx.AsyncClient
STUDENT_OK = {"state": 1, "msg": "", "data": {
    "studentID": 12345, "fullName": "Иванов Иван Иванович", "surname": "Иванов", "name": "Иван", "middleName": "Иванович",
    "group": {"item1": "24-ИСбо-1", "item2": 4242, "formID": 1}, "course": 2, "photoLink": "https://example.com/p.jpg",
}}


def _run_login(monkeypatch, student_reply):
    """eios.authenticate against a fake EIOS; student_reply(request) answers UserInfo/Student."""
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("/tokenauth"):
            return httpx.Response(200, json=TOKENAUTH_OK)
        return student_reply(request)

    monkeypatch.setattr(eios.httpx, "AsyncClient", lambda **kw: _RealAsyncClient(transport=httpx.MockTransport(handler), **kw))
    return asyncio.run(eios.authenticate("student@example.com", "pw")), seen


def test_authenticate_takes_name_and_group_from_the_student_card(monkeypatch):
    identity, seen = _run_login(monkeypatch, lambda request: httpx.Response(200, json=STUDENT_OK))
    assert identity.full_name == "Иванов Иван Иванович"
    assert identity.group == "24-ИСбо-1" and identity.group_id == 4242
    assert identity.eios_id == "-12345"  # unchanged: existing accounts stay bound to it
    card = seen[1]
    assert card.url.path.endswith("/UserInfo/Student") and card.url.params["studentID"] == "-12345"
    assert card.headers["Authorization"] == f"Bearer {TOKEN}"


def test_authenticate_retries_the_card_with_a_bare_token(monkeypatch):
    def reply(request):
        if request.headers["Authorization"].startswith("Bearer "):
            return httpx.Response(401)
        return httpx.Response(200, json=STUDENT_OK)

    identity, _ = _run_login(monkeypatch, reply)
    assert identity.full_name == "Иванов Иван Иванович" and identity.group_id == 4242


def test_authenticate_falls_back_to_the_token_name(monkeypatch):
    # EIOS answers 200 with state -1 for errors
    identity, _ = _run_login(monkeypatch, lambda request: httpx.Response(200, json={"state": -1, "msg": "Не найдено", "data": None}))
    assert identity.full_name == "Иванов И. И." and identity.group is None and identity.group_id is None

    def down(request):
        raise httpx.ConnectError("unreachable")

    identity, _ = _run_login(monkeypatch, down)
    assert identity is not None and identity.full_name == "Иванов И. И."


def test_parse_student_profile():
    assert eios.parse_student_profile(STUDENT_OK) == eios.StudentProfile("Иванов Иван Иванович", "24-ИСбо-1", 4242)
    parts = {"state": 1, "data": {"surname": "Петров", "name": "Пётр", "middleName": None, "group": {"item1": " 25-ИВТбо-2 ", "item2": "77"}}}
    assert eios.parse_student_profile(parts) == eios.StudentProfile("Петров Пётр", "25-ИВТбо-2", 77)
    odd_id = {"state": 1, "data": {"fullName": "Петров Пётр", "group": {"item1": "25-ИВТбо-2", "item2": True}}}
    assert eios.parse_student_profile(odd_id).group_id is None
    assert eios.parse_student_profile({"state": -1, "data": STUDENT_OK["data"]}) is None
    assert eios.parse_student_profile({"state": 1, "data": {}}) is None
    assert eios.parse_student_profile([]) is None


def test_jwt_claims_tolerate_garbage():
    assert eios.jwt_claims(TOKEN)[_CLAIMS + "sid"] == "-12345"
    for bad in (None, "", "no-dots", "a.!!!.c", "a.bm90IGpzb24.c"):
        assert eios.jwt_claims(bad) == {}


def test_eios_login_needs_consent_and_records_it(client, fake_eios, db):
    _, calls = fake_eios
    add_eios_account(fake_eios, "24-isbo-050")
    r = client.post("/api/v1/auth/eios-login", json={"username": "24-isbo-050", "password": "pw"})
    assert r.status_code == 400 and "согласие" in r.json()["detail"]
    assert calls == []  # nothing is sent to EIOS without consent
    r = client.post("/api/v1/auth/eios-login", json={"username": "24-isbo-050", "password": "pw", "consent": True})
    assert r.status_code == 200
    user = db.query(models.User).filter(models.User.username == "24-isbo-050").one()
    assert user.pd_consent_at is not None and user.pd_consent_version == auth.PD_CONSENT_VERSION
