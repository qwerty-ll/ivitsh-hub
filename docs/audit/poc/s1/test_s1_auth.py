"""S1: authentication / session / rate-limit PoCs (area A).

`*_ok` tests assert a protection that holds; `*_FINDING` tests pass when the weakness is PRESENT.
"""
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

import app.models as models
import main
from app.core import rate_limit, security
from app.core.config import settings
from app.services import eios
from srv_conftest import CSRF, add_eios_account, login_admin, login_student


def _tok(claims, key=None, alg="HS256"):
    return jwt.encode(claims, key or settings.SECRET_KEY, algorithm=alg)


def _claims(sub, **kw):
    now = datetime.now(timezone.utc)
    base = {"sub": sub, "iat": now, "exp": now + timedelta(hours=1), "jti": "poc-jti"}
    base.update(kw)
    return base


# --- JWT -------------------------------------------------------------------------------------------

def test_jwt_forgery_variants_are_rejected_ok(app, fake_eios):
    login_student(app, fake_eios)
    forged = {
        "alg_none": jwt.encode(_claims("24-isbo-001"), key="", algorithm="none"),
        "wrong_key": _tok(_claims("24-isbo-001"), key="x" * 40),
        "expired": _tok(_claims("24-isbo-001", exp=datetime.now(timezone.utc) - timedelta(seconds=5))),
        "no_exp": _tok({k: v for k, v in _claims("24-isbo-001").items() if k != "exp"}),
        "no_jti": _tok({k: v for k, v in _claims("24-isbo-001").items() if k != "jti"}),
        "hs512_same_key": _tok(_claims("24-isbo-001"), alg="HS512"),
    }
    for name, token in forged.items():
        c = TestClient(app, cookies={security.AUTH_COOKIE_NAME: token})
        assert c.get("/api/v1/auth/me").status_code == 401, name
    good = TestClient(app, cookies={security.AUTH_COOKIE_NAME: _tok(_claims("24-isbo-001"))})
    assert good.get("/api/v1/auth/me").status_code == 200  # sanity: a correctly signed token works


def test_cookie_flags_ok(app, fake_eios):
    add_eios_account(fake_eios, "24-isbo-001")
    r = TestClient(app).post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-001", "password": "pw"})
    sc = r.headers["set-cookie"].lower()
    print(sc.split("=", 1)[0], "...", sc.split(";", 1)[1])
    assert "httponly" in sc and "samesite=lax" in sc and "path=/" in sc and "max-age=86400" in sc
    # Secure is off only because the test env sets COOKIE_SECURE=false; the code default is True
    import os
    assert os.environ["COOKIE_SECURE"] == "false"


def test_csrf_only_checked_for_cookie_auth_ok(app, fake_eios):
    c = login_student(app, fake_eios)
    assert c.patch("/api/v1/auth/me", json={"vk_url": "ivan"}).status_code == 403  # cookie, no header
    assert c.patch("/api/v1/auth/me", json={"vk_url": "ivan"}, headers=CSRF).status_code == 200
    # Authorization header disables the check, but cross-site pages cannot set it without a preflight
    tok = c.cookies.get(security.AUTH_COOKIE_NAME)
    bare = TestClient(app)
    assert bare.patch("/api/v1/auth/me", json={"vk_url": "ivan2"}, headers={"Authorization": f"Bearer {tok}"}).status_code == 200


def test_block_and_role_change_take_effect_on_next_request_ok(app, fake_eios, db):
    s = login_student(app, fake_eios)
    admin = login_admin(app)
    uid = db.query(models.User).filter_by(username="24-isbo-001").one().id
    admin.patch(f"/api/v1/admin/users/{uid}/role", json={"role": "admin"}, headers=CSRF)
    assert s.get("/api/v1/admin/users").status_code == 200
    admin.patch(f"/api/v1/admin/users/{uid}/role", json={"role": "student"}, headers=CSRF)
    assert s.get("/api/v1/admin/users").status_code == 403
    admin.patch(f"/api/v1/admin/users/{uid}/block", json={"blocked": True}, headers=CSRF)
    assert s.get("/api/v1/auth/me").status_code == 401
    # unblocking resurrects the SAME old token (nothing is revoked on block): not a vulnerability, but notable
    admin.patch(f"/api/v1/admin/users/{uid}/block", json={"blocked": False}, headers=CSRF)
    assert s.get("/api/v1/auth/me").status_code == 200


def test_no_session_revocation_for_a_compromised_account_FINDING(app, fake_eios, db):
    """There is no 'sign out everywhere' / token_version: a stolen cookie of an admin lives 24 h even after the
    admin changes his password in EIOS (the portal never re-checks EIOS) - only block/delete or rotating SECRET_KEY helps."""
    s = login_student(app, fake_eios)
    stolen = s.cookies.get(security.AUTH_COOKIE_NAME)
    s.post("/api/v1/auth/logout", headers=CSRF)  # logout revokes only the presented jti
    thief = TestClient(app, cookies={security.AUTH_COOKIE_NAME: stolen})
    assert thief.get("/api/v1/auth/me").status_code == 401  # this one jti is revoked
    # a second login yields a different jti; revoking the first does nothing to it
    s2 = TestClient(app)
    s2.post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-001", "password": "pw"})
    t2 = s2.cookies.get(security.AUTH_COOKIE_NAME)
    s.post("/api/v1/auth/logout", headers=CSRF)
    assert TestClient(app, cookies={security.AUTH_COOKIE_NAME: t2}).get("/api/v1/auth/me").status_code == 200
    ttl = jwt.decode(t2, options={"verify_signature": False})
    assert ttl["exp"] - ttl["iat"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60 == 86400
    cols = {c.name for c in models.User.__table__.columns}
    assert not ({"token_version", "tokens_valid_after", "session_epoch"} & cols)


# --- login limits ----------------------------------------------------------------------------------

def test_login_errors_do_not_enumerate_users_ok(client, fake_eios):
    add_eios_account(fake_eios, "24-isbo-001", password="right")
    a = client.post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-001", "password": "wrong"})
    b = client.post("/api/v1/auth/eios-login", json={"consent": True, "username": "nobody-at-all", "password": "wrong"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()
    c = client.post("/api/v1/auth/admin-login", json={"username": "portal_admin", "password": "wrong"})
    d = client.post("/api/v1/auth/admin-login", json={"username": "nobody", "password": "wrong"})
    assert c.status_code == d.status_code == 401 and c.json() == d.json()


def test_admin_username_probe_via_eios_login_skips_eios_FINDING(client, fake_eios):
    """eios-login answers the ADMIN_USERNAME locally (EIOS is not called): a timing oracle for the admin login name."""
    accounts, calls = fake_eios
    r1 = client.post("/api/v1/auth/eios-login", json={"consent": True, "username": "someone", "password": "x"})
    r2 = client.post("/api/v1/auth/eios-login", json={"consent": True, "username": settings.ADMIN_USERNAME, "password": "x"})
    assert r1.status_code == r2.status_code == 401 and r1.json() == r2.json()
    assert calls == ["someone"]  # EIOS was asked about 'someone' only; real EIOS adds 100+ ms to that branch


def test_eios_failure_limit_is_bypassed_by_parallel_requests_FINDING(app, monkeypatch):
    """The 5-failures-per-account limit is checked BEFORE the awaited EIOS call and counted AFTER it, so a burst of
    parallel guesses all pass the check. EIOS (the real password oracle) gets N >> 5 guesses in one burst."""
    seen = []

    async def slow_authenticate(username, password):
        seen.append(password)
        await asyncio.sleep(0.3)  # a real EIOS round trip
        return None

    monkeypatch.setattr(eios, "authenticate", slow_authenticate)
    rate_limit.reset_all()

    async def burst(n):
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
            rs = await asyncio.gather(*(ac.post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-001", "password": f"guess{i}"})
                                        for i in range(n)))
        return [r.status_code for r in rs]

    codes = asyncio.run(burst(60))
    print("EIOS saw", len(seen), "password guesses; statuses:", {c: codes.count(c) for c in set(codes)})
    assert len(seen) > 5 * 5  # limit is 5 per account / 15 min; here the whole burst reached EIOS
    # after the burst the account is locked, as designed
    again = TestClient(app).post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-001", "password": "late"})
    assert again.status_code == 429


def test_admin_login_failure_limit_is_exceeded_by_parallel_requests_FINDING(app, monkeypatch):
    """admin-login: limit 5/account, 10/IP per 15 min, counted after a ~0.3 s bcrypt check -> a parallel burst gets far more tries."""
    login_admin(app)  # creates the local admin row, so wrong passwords go through bcrypt
    rate_limit.reset_all()
    calls = []
    real = security.verify_password

    def counting(plain, hashed):
        calls.append(1)
        return real(plain, hashed)

    monkeypatch.setattr(security, "verify_password", counting)

    def attempt(i):
        c = TestClient(app)
        return c.post("/api/v1/auth/admin-login", json={"username": "portal_admin", "password": f"wrong{i}"}).status_code

    with ThreadPoolExecutor(30) as pool:
        codes = list(pool.map(attempt, range(30)))
    print("bcrypt checks of wrong passwords:", len(calls), {c: codes.count(c) for c in set(codes)})
    assert len(calls) > 10  # nominal budget is 5 (account) / 10 (IP)


def test_campus_nat_lockout_by_100_failures_FINDING(client, fake_eios):
    """Failures are counted per IP (100 / 15 min); the whole campus shares one NAT address, so one person (or an honest
    start-of-semester wave of typos) blocks ALL sign-ins from that address for up to 15 minutes."""
    add_eios_account(fake_eios, "24-isbo-050", password="right")
    for i in range(100):
        r = client.post("/api/v1/auth/eios-login", json={"consent": True, "username": f"nobody-{i}", "password": "x"})
        assert r.status_code == 401, (i, r.status_code)
    victim = client.post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-050", "password": "right"})
    assert victim.status_code == 429  # a student with the CORRECT password is refused


def test_targeted_account_lockout_FINDING(client, fake_eios):
    """5 wrong passwords for someone else's login name lock that person out (correct password -> 429) for 15 min."""
    add_eios_account(fake_eios, "24-isbo-051", password="right")
    for _ in range(5):
        assert client.post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-051", "password": "no"}).status_code == 401
    assert client.post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-051", "password": "right"}).status_code == 429
    # same for the main administrator: only the login name (ADMIN_USERNAME) must be guessed
    for _ in range(5):
        client.post("/api/v1/auth/admin-login", json={"username": settings.ADMIN_USERNAME, "password": "no"})
    r = client.post("/api/v1/auth/admin-login", json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD})
    assert r.status_code == 429


def test_passwords_never_reach_logs_or_responses_ok(client, fake_eios, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    client.post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-060", "password": "SuperSecret-PoC-123"})
    client.post("/api/v1/auth/admin-login", json={"username": "portal_admin", "password": "AnotherSecret-PoC-456"})
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "SuperSecret-PoC-123" not in text and "AnotherSecret-PoC-456" not in text


def test_partial_eios_outage_overwrites_stored_name_and_group_FINDING(app, fake_eios, db):
    """If tokenauth works but UserInfo/Student does not (eios.fetch_student_profile -> None) the identity has no real
    name/group; eios_login still overwrites users.full_name with a placeholder and a hand-typed group wins, losing eios_group_id."""
    accounts, _ = fake_eios
    add_eios_account(fake_eios, "24-isbo-070", full_name="Иванов Иван Иванович", group="24-ИСбо-1", group_id=4242)
    c = TestClient(app)
    assert c.post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-070", "password": "pw"}).status_code == 200
    u = db.query(models.User).filter_by(username="24-isbo-070").one()
    assert (u.full_name, u.group_number, u.eios_group_id) == ("Иванов Иван Иванович", "24-ИСбо-1", 4242)
    # next login: EIOS answers, but the student card request failed -> identity without name and group
    accounts["24-isbo-070"] = ("pw", eios.EiosIdentity(eios_id="100", full_name=None, group=None, avatar_url=None))
    r = TestClient(app).post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-070", "password": "pw", "group_number": "99-ХХХ-9"})
    assert r.status_code == 200
    db.expire_all()
    u = db.query(models.User).filter_by(username="24-isbo-070").one()
    print("after degraded login:", u.full_name, u.group_number, u.eios_group_id)
    assert u.full_name == "Студент 24-isbo-070"  # real name lost (shown to leaders, on the forum, in exports)
    assert u.group_number == "99-ХХХ-9" and u.eios_group_id is None  # typed group replaces the confirmed one
