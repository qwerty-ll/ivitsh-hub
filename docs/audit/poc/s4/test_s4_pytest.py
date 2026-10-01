"""S4 PoCs (input/output/files/external calls). A PASS means "behaviour confirmed as described in the finding";
tests marked  # OK-CHECK  document controls that work, so they keep guarding them.

Run from the repo root:
    cd server && python -m pytest ../docs/audit/poc/s4/test_s4_pytest.py -q -p no:cacheprovider
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "server", "tests"))
from conftest import CSRF, app, clean_state, client, db, fake_eios, login_admin, login_student  # noqa: E402,F401

from app.core.config import settings  # noqa: E402
from app.services import eios, timetable  # noqa: E402

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


# --- K / C: the public schedule endpoints are an open relay to EIOS ---------------------------------------

@pytest.fixture
def eios_calls(monkeypatch):
    calls = []
    answer = {"data": {"rasp": []}, "state": 1}

    async def fetch_json(endpoint, params, timeout=5.0):
        calls.append((endpoint, tuple(sorted(params.items()))))
        return answer if answer is not None else None

    monkeypatch.setattr(eios, "fetch_json", fetch_json)
    return calls


def test_anonymous_requests_with_distinct_ids_each_cost_one_eios_call(client, eios_calls):
    for i in range(1, 301):
        assert client.get("/api/v1/schedule/rasp", params={"idGroup": i}).status_code == 200  # no cookie, no limit
    assert len(eios_calls) == 300  # one outbound EIOS request per anonymous request: only nginx's 50 r/s per IP stands in the way


def test_failed_eios_answers_are_never_cached(client, monkeypatch):
    calls = []

    async def failing(endpoint, params, timeout=5.0):
        calls.append(1)
        return None

    monkeypatch.setattr(eios, "fetch_json", failing)
    for _ in range(50):
        assert client.get("/api/v1/schedule/rasp", params={"idGroup": 7}).status_code == 503
    assert len(calls) == 50  # EIOS down or rejecting: every visitor request still goes out (no negative cache, no breaker)


def test_anonymous_visitor_can_evict_the_shared_group_list_from_the_cache(client, eios_calls):
    assert client.get("/api/v1/schedule/groups").status_code == 200
    assert client.get("/api/v1/schedule/groups").status_code == 200
    assert len(eios_calls) == 1  # second answer came from the cache
    for i in range(1, timetable._MAX_CACHE_ENTRIES + 50):
        client.get("/api/v1/schedule/rasp", params={"idGroup": i})
    before = len(eios_calls)
    assert client.get("/api/v1/schedule/groups").status_code == 200
    assert len(eios_calls) == before + 1  # the list everybody shares was pushed out (oldest entry goes first)


# --- C: uploads -------------------------------------------------------------------------------------------

@pytest.fixture
def task_id(app, fake_eios, db):
    c = login_student(app, fake_eios, "24-isbo-901")
    r = c.post("/api/v1/tasks", json={"title": "Личная", "color": "blue"}, headers=CSRF)
    assert r.status_code in (200, 201), r.text
    return c, r.json()["id"]


def test_download_is_attachment_nosniff_and_private(task_id):  # OK-CHECK
    c, tid = task_id
    html_polyglot = b"%PDF-1.4\n<html><script>alert(1)</script></html>"
    r = c.post(f"/api/v1/tasks/{tid}/files", params={"name": 'evil";x=".pdf'}, content=html_polyglot, headers=CSRF)
    assert r.status_code == 201, r.text
    d = c.get(f"/api/v1/attachments/{r.json()['id']}")
    assert d.status_code == 200
    assert d.headers["content-type"] == "application/pdf"
    assert d.headers["content-disposition"].startswith("attachment")
    assert d.headers["x-content-type-options"] == "nosniff"
    assert d.headers["cache-control"] == "private, no-store"
    assert d.headers["content-disposition"] == "attachment; filename*=utf-8''evil_%3Bx%3D_.pdf"  # quote -> "_", RFC 5987 encoding, no CR/LF


@pytest.mark.parametrize("name,body,code", [
    ("shell.svg", b"<svg onload=alert(1)>", 415),
    ("page.html", b"<html>", 415),
    ("a.pdf", b"<html><script>", 415),            # extension says PDF, bytes do not
    ("../../etc/passwd.pdf", PDF, 201),           # path part is dropped, stored under a random name
    ("x.pdf\x00.exe", PDF, 415),                   # NUL replaced -> extension .exe
    ("noext", PDF, 415),
    ("bomb.zip", b"PK\x03\x04" + b"\x00" * 100, 201),  # signature only; content is never opened server-side
])
def test_upload_name_and_signature_rules(task_id, name, body, code):  # OK-CHECK (+ documents the weak spots)
    c, tid = task_id
    r = c.post(f"/api/v1/tasks/{tid}/files", params={"name": name}, content=body, headers=CSRF)
    assert r.status_code == code, r.text
    if code == 201:
        stored = os.listdir(settings.UPLOAD_DIR)
        assert all("/" not in s and ".." not in s for s in stored)


def test_oversize_chunked_upload_is_cut_and_leaves_nothing(task_id):  # OK-CHECK
    c, tid = task_id
    big = (b"%PDF" + b"0" * 1024 for _ in range(1100))  # > MAX_UPLOAD_MB=1 and no Content-Length (chunked)
    r = c.post(f"/api/v1/tasks/{tid}/files", params={"name": "big.pdf"}, content=big, headers=CSRF)
    assert r.status_code == 413
    assert not [f for f in os.listdir(settings.UPLOAD_DIR) if f.endswith(".part")]


def test_signature_check_looks_only_at_the_first_bytes(task_id):
    c, tid = task_id
    # a real PNG header followed by an HTML page is accepted as "image/png" (it is only ever served as an attachment)
    body = b"\x89PNG\r\n\x1a\n" + b"<html><script>alert(1)</script></html>"
    r = c.post(f"/api/v1/tasks/{tid}/files", params={"name": "pic.png"}, content=body, headers=CSRF)
    assert r.status_code == 201


def test_shop_image_endpoint_is_public_and_inline(app, fake_eios):
    admin = login_admin(app)
    item = admin.post("/api/v1/shop/items", json={"title": "Кружка", "kind": "merch", "price": 10, "stock": 1}, headers=CSRF)
    assert item.status_code in (200, 201), item.text
    iid = item.json()["id"] if "id" in item.json() else item.json()["item"]["id"]
    r = admin.post(f"/api/v1/shop/items/{iid}/image", params={"name": "m.png"}, content=b"\x89PNG\r\n\x1a\n" + b"x" * 20, headers=CSRF)
    assert r.status_code == 200, r.text
    from fastapi.testclient import TestClient
    anon = TestClient(app).get(f"/api/v1/shop/items/{iid}/image")
    assert anon.status_code == 200 and "content-disposition" not in anon.headers  # served inline, no auth (by design: no PD)
    assert anon.headers["cache-control"] == "public, max-age=604800"  # a replaced photo stays stale for a week


# --- C: headers / docs / CORS -----------------------------------------------------------------------------

def test_docs_and_openapi_are_off_by_default(client):  # OK-CHECK
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_backend_itself_sets_no_security_headers_nginx_does(client):
    r = client.get("/api/v1/health")
    for h in ("strict-transport-security", "x-content-type-options", "content-security-policy", "cache-control", "referrer-policy"):
        assert h not in r.headers  # all of them come from nginx snippets; direct access to :8000 gets none (and no no-store on API data)


def test_no_cors_headers_without_allowed_origins(client):  # OK-CHECK
    r = client.options("/api/v1/auth/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers


def test_validation_error_echoes_submitted_password_back(client):
    r = client.post("/api/v1/auth/eios-login", json={"username": "u", "password": "p" * 200, "consent": True}, headers=CSRF)
    assert r.status_code == 422
    assert "p" * 200 in r.text  # FastAPI puts the rejected input into the 422 body (same user, over TLS; nothing is logged by the app)


# --- K: EIOS behaviour -------------------------------------------------------------------------------------

def test_concurrent_cache_misses_all_go_to_eios(app, monkeypatch):
    """No single-flight in timetable.cached(): N simultaneous visitors after a TTL expiry = N EIOS requests."""
    import asyncio
    import httpx

    calls = []

    async def slow_fetch(endpoint, params, timeout=5.0):
        calls.append(1)
        await asyncio.sleep(0.2)
        return {"data": {"rasp": []}, "state": 1}

    monkeypatch.setattr(eios, "fetch_json", slow_fetch)

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await asyncio.gather(*(c.get("/api/v1/schedule/rasp", params={"idGroup": 5}) for _ in range(40)))

    results = asyncio.run(run())
    assert all(r.status_code == 200 for r in results)
    assert len(calls) == 40  # should be 1


@pytest.mark.parametrize("status", [401, 403, 404, 429])
def test_eios_client_errors_are_reported_as_wrong_password(monkeypatch, status):
    """eios.authenticate(): any non-200 below 500 (rate limit, WAF, moved endpoint) == "wrong credentials"."""
    import asyncio
    import httpx

    real = httpx.AsyncClient
    monkeypatch.setattr(eios.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(lambda req: httpx.Response(status)), **kw))
    assert asyncio.run(eios.authenticate("24-isbo-001", "right-password")) is None


def test_failed_logins_caused_by_eios_429_lock_the_student_out(app, monkeypatch):
    """Same thing through the route: 5 requests while EIOS answers 429 -> 6th is blocked by the portal for 15 minutes."""
    import httpx
    from fastapi.testclient import TestClient

    real = httpx.AsyncClient
    monkeypatch.setattr(eios.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(lambda req: httpx.Response(429)), **kw))
    c = TestClient(app)
    codes = [c.post("/api/v1/auth/eios-login", json={"username": "24-isbo-777", "password": "right", "consent": True}, headers=CSRF).status_code for _ in range(6)]
    assert codes == [401, 401, 401, 401, 401, 429]


# --- C: rate limit keys (per account, per IP) ---------------------------------------------------------------

def test_anyone_can_lock_a_students_account_and_the_main_admin_for_15_minutes(app, fake_eios):
    from fastapi.testclient import TestClient
    from conftest import add_eios_account

    add_eios_account(fake_eios, "24-isbo-555", password="right")
    attacker = TestClient(app)
    for _ in range(5):  # wrong password for somebody else's login
        assert attacker.post("/api/v1/auth/eios-login", json={"username": "24-isbo-555", "password": "x", "consent": True}, headers=CSRF).status_code == 401
    victim = TestClient(app)  # a different client / IP: the lock is keyed by the login only
    r = victim.post("/api/v1/auth/eios-login", json={"username": "24-isbo-555", "password": "right", "consent": True}, headers=CSRF)
    assert r.status_code == 429

    for _ in range(5):  # the same for the main administrator (login name from .env)
        attacker.post("/api/v1/auth/admin-login", json={"username": "portal_admin", "password": "x"}, headers=CSRF)
    r = TestClient(app).post("/api/v1/auth/admin-login", json={"username": "portal_admin", "password": "Adm1n-Test-Password!"}, headers=CSRF)
    assert r.status_code == 429


def test_allowed_origins_star_would_reflect_any_origin_with_cookies():
    """main.py passes ALLOWED_ORIGINS straight to CORSMiddleware(allow_credentials=True); config.py does not reject "*"."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.testclient import TestClient

    import app.core.security as security

    probe = FastAPI()
    probe.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,  # same kwargs as server/main.py:97-103
                         allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                         allow_headers=["Content-Type", "Accept", security.CSRF_HEADER_NAME])

    @probe.get("/x")
    def x():
        return {}

    r = TestClient(probe).options("/x", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST",
                                                  "Access-Control-Request-Headers": "x-requested-with"})
    assert r.headers["access-control-allow-origin"] == "https://evil.example" and r.headers["access-control-allow-credentials"] == "true"
