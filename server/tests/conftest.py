import os
import sys
import tempfile

import pytest

_DB_DIR = tempfile.mkdtemp(prefix="portal-tests-")
os.environ.update({
    "SECRET_KEY": "test-secret-key-that-is-long-enough-1234567890",
    "DATABASE_URL": f"sqlite:///{_DB_DIR}/test.db",
    "UPLOAD_DIR": f"{_DB_DIR}/uploads",
    "MAX_UPLOAD_MB": "1",
    "ADMIN_USERNAME": "portal_admin",
    "ADMIN_PASSWORD": "Adm1n-Test-Password!",
    "COOKIE_SECURE": "false",
    "GIGACHAT_AUTH_KEY": "",
    "GIGACHAT_SECRET": "",
    "ALLOWED_ORIGINS": "",
    "SDO_BASE_URL": "",
})
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app.core import rate_limit  # noqa: E402
from app.db.database import Base, SessionLocal  # noqa: E402
from app.routers import schedule  # noqa: E402
from app.services import agent, eios, rag_service  # noqa: E402

CSRF = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture(scope="session")
def app():
    with TestClient(main.app):  # runs migrations and seeding once
        yield main.app


@pytest.fixture(autouse=True)
def clean_state(app):
    yield
    db = SessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name not in ("teachers", "subjects"):
            db.execute(table.delete())
    db.commit()
    db.close()
    rate_limit.reset_all()
    schedule.clear_cache()
    rag_service._state["cooldown_until"] = 0.0
    agent._state["functions_paused_until"] = 0.0


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def fake_eios(monkeypatch):
    """Maps username -> (password, EiosIdentity); anything else is rejected like wrong credentials."""
    accounts = {}
    calls = []

    async def authenticate(username, password):
        calls.append(username)
        entry = accounts.get(username.lower())
        if entry and entry[0] == password:
            return entry[1]
        return None

    monkeypatch.setattr(eios, "authenticate", authenticate)
    return accounts, calls


def add_eios_account(fake_eios, username, password="pw", eios_id="100", full_name="Иванов Иван Иванович", group="24-ИСбо-1", avatar_url=None, group_id=None):
    accounts, _ = fake_eios
    accounts[username.lower()] = (password, eios.EiosIdentity(eios_id=eios_id, full_name=full_name, group=group, avatar_url=avatar_url, group_id=group_id))


def login_student(app, fake_eios, username="24-isbo-001", **kwargs):
    add_eios_account(fake_eios, username, **kwargs)
    c = TestClient(app)
    r = c.post("/api/v1/auth/eios-login", json={"consent": True, "username": username, "password": kwargs.get("password", "pw")})
    assert r.status_code == 200, r.text
    return c


def login_admin(app):
    c = TestClient(app)
    r = c.post("/api/v1/auth/admin-login", json={"username": "portal_admin", "password": "Adm1n-Test-Password!"})
    assert r.status_code == 200, r.text
    return c
