"""Shared helpers for the S3 PoCs: local DB, users with ready cookies, a local uvicorn with N workers.

No external systems: users are inserted straight into the local DB and get a self-signed JWT cookie
(the same SECRET_KEY the local app uses); EIOS is never called.

DB: S3_DATABASE_URL (default: a SQLite file under S3_DIR or the system temp dir). For PostgreSQL use e.g.
    S3_DATABASE_URL=postgresql://postgres@127.0.0.1:54329/ivitsh
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SERVER = REPO / "server"
HERE = Path(__file__).resolve().parent
TMP = Path(os.environ.get("S3_DIR") or tempfile.mkdtemp(prefix="s3poc-"))
TMP.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("SECRET_KEY", "s3-poc-secret-key-long-enough-0123456789abcdef")
os.environ.setdefault("ADMIN_USERNAME", "s3_main_admin")
os.environ.setdefault("ADMIN_PASSWORD", "S3-poc-Admin-password-1")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("SDO_BASE_URL", "")
os.environ.setdefault("GIGACHAT_AUTH_KEY", "")
os.environ["DATABASE_URL"] = os.environ.get("S3_DATABASE_URL") or f"sqlite:///{TMP}/s3.db"
os.environ.setdefault("UPLOAD_DIR", str(TMP / "uploads"))
sys.path.insert(0, str(SERVER))
sys.path.insert(0, str(HERE))

H = {"X-Requested-With": "XMLHttpRequest"}
PORT = int(os.environ.get("S3_PORT", "8137"))
BASE = f"http://127.0.0.1:{PORT}"


def fresh_db():
    """Drop everything and migrate to head (local DB only)."""
    from sqlalchemy import text
    from app.db.database import engine, Base
    import app.models  # noqa: F401
    with engine.begin() as c:
        if engine.dialect.name == "postgresql":
            c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        else:
            pass
    if engine.dialect.name == "sqlite":
        engine.dispose()
        p = os.environ["DATABASE_URL"].replace("sqlite:///", "")
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(p + suffix):
                os.remove(p + suffix)
    from app.db.migrate import run_migrations
    run_migrations()


def mk_user(db, name, role="student", group="24-ИСбо-1", n=[0]):
    import app.models as models
    from app.core import security
    n[0] += 1
    u = models.User(username=f"s3-{name}-{n[0]}", full_name=f"S3 {name}", hashed_password="x", role=role,
                    group_number=group, auth_source="eios", sdo_id=str(9000 + n[0]))
    db.add(u)
    db.commit()
    return u


def cookie(u):
    from app.core import security
    return {"portal_token": security.create_access_token(u.username)}


def mk_assoc(db, name, leader=None, members=()):
    import app.models as models
    a = models.Association(name=name, is_active=True)
    db.add(a)
    db.commit()
    if leader:
        db.add(models.Membership(user_id=leader.id, association_id=a.id, role="leader", status="approved"))
    for m in members:
        db.add(models.Membership(user_id=m.id, association_id=a.id, role="member", status="approved"))
    db.commit()
    return a


def start_server(workers=2, app_target="main:app", extra_env=None):
    env = dict(os.environ, **(extra_env or {}))
    env["PYTHONPATH"] = os.pathsep.join([str(SERVER), str(HERE)])
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", app_target, "--host", "127.0.0.1", "--port", str(PORT),
                          "--workers", str(workers), "--log-level", "warning"], cwd=SERVER, env=env)
    import httpx
    for _ in range(80):
        try:
            if httpx.get(BASE + "/api/v1/health", timeout=1).status_code == 200:
                return p
        except Exception:
            time.sleep(0.5)
    p.terminate()
    raise RuntimeError("server did not start")


def stop_server(p):
    p.terminate()
    try:
        p.wait(10)
    except Exception:
        p.kill()
