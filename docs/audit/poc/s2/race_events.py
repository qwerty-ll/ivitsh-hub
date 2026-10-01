"""S2 PoC: races on event registration limits and on upload quotas, against a real uvicorn process.

Run from the repo root (SQLite, default):
    python docs/audit/poc/s2/race_events.py
PostgreSQL (needs a throw-away database, never a real one):
    S2_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/s2 python docs/audit/poc/s2/race_events.py

It seeds users straight into the DB and signs their JWTs with a test SECRET_KEY, so no EIOS is contacted.
"""
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..'))
SERVER = os.path.join(ROOT, "server")
WORK = tempfile.mkdtemp(prefix="s2-race-")
DB_URL = os.environ.get("S2_DATABASE_URL") or f"sqlite:///{WORK}/race.db"
PORT = int(os.environ.get("S2_PORT", "8765"))
ENV = {
    **os.environ,
    "SECRET_KEY": "audit-s2-secret-key-that-is-long-enough-123456",
    "DATABASE_URL": DB_URL, "UPLOAD_DIR": f"{WORK}/uploads", "COOKIE_SECURE": "false",
    "ADMIN_USERNAME": "portal_admin", "ADMIN_PASSWORD": "Adm1n-Test-Password!",
    "MAX_UPLOAD_MB": "1", "USER_UPLOAD_QUOTA_MB": "2", "FILES_PER_ITEM": "5", "SDO_BASE_URL": "",
    "GIGACHAT_AUTH_KEY": "", "ALLOWED_ORIGINS": "",
}
os.environ.update(ENV)
sys.path.insert(0, SERVER)

import httpx  # noqa: E402

N = int(os.environ.get("S2_N", "30"))


def start_server():
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(PORT), "--workers", "1"],
                            cwd=SERVER, env=ENV, stdout=subprocess.DEVNULL, stderr=open(f"{WORK}/uvicorn.log", "w"))
    for _ in range(80):
        try:
            if httpx.get(f"http://127.0.0.1:{PORT}/api/v1/health", timeout=1).status_code == 200:
                return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("server did not start, see " + WORK + "/uvicorn.log")


def seed():
    import app.models as models
    from app.core import security
    from app.db.database import SessionLocal
    db = SessionLocal()
    users = []
    for i in range(N + 2):
        u = models.User(username=f"race-{i:03d}", full_name=f"Гонкин Тест{i:03d} Тестович", hashed_password="x",
                        role="admin" if i == 0 else "student", group_number="24-ИСбо-1", auth_source="eios")
        db.add(u)
        users.append(u)
    db.commit()
    tokens = [security.create_access_token(u.username) for u in users]
    ids = [u.id for u in users]
    db.close()
    return ids, tokens


def client(token):
    return httpx.Client(base_url=f"http://127.0.0.1:{PORT}", headers={"Authorization": f"Bearer {token}"}, timeout=60)


def blast(fn, workers):
    """Run fn(i) for every worker at once; returns the list of results."""
    barrier, out = threading.Barrier(len(workers)), [None] * len(workers)

    def run(i):
        barrier.wait()
        try:
            out[i] = fn(workers[i])
        except Exception as exc:  # noqa: BLE001
            out[i] = f"EXC {exc!r}"

    threads = [threading.Thread(target=run, args=(i,)) for i in range(len(workers))]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return out


def when(days, hours=2):
    s = datetime.now(timezone.utc) + timedelta(days=days)
    return {"starts_at": s.isoformat(), "ends_at": (s + timedelta(hours=hours)).isoformat()}


def main():
    print("database:", DB_URL.split("@")[-1] if "@" in DB_URL else "sqlite (temp file)")
    proc = start_server()
    try:
        ids, tokens = seed()
        admin = client(tokens[0])
        students = tokens[1:N + 1]

        # R1: participant limit
        ev = admin.post("/api/v1/events", json={"title": "Гонка", "scope": "institute", "participant_limit": 3,
                                                 "volunteer_limit": 2, **when(2)}).json()
        res = blast(lambda t: client(t).post(f"/api/v1/events/{ev['id']}/register", json={"role": "participant"}).status_code, students)
        got = admin.get(f"/api/v1/events/{ev['id']}").json()
        print(f"R1 participant_limit=3, {N} parallel self-registrations: statuses={sorted(set(map(str, res)))} "
              f"-> registered participants={got['participants']}  {'OVERSOLD' if got['participants'] > 3 else 'ok'}")

        # R2: volunteer limit
        ev2 = admin.post("/api/v1/events", json={"title": "Гонка В", "scope": "institute", "participant_limit": 100,
                                                  "volunteer_limit": 2, **when(2)}).json()
        res = blast(lambda t: client(t).post(f"/api/v1/events/{ev2['id']}/register", json={"role": "volunteer"}).status_code, students)
        got = admin.get(f"/api/v1/events/{ev2['id']}").json()
        print(f"R2 volunteer_limit=2: statuses={sorted(set(map(str, res)))} -> volunteers={got['volunteers']}  "
              f"{'OVERSOLD' if got['volunteers'] > 2 else 'ok'}")

        # R3: one student double-submits the same registration (unique constraint)
        ev3 = admin.post("/api/v1/events", json={"title": "Двойной клик", "scope": "institute", **when(2)}).json()
        res = blast(lambda t: client(t).post(f"/api/v1/events/{ev3['id']}/register", json={}).status_code, [students[0]] * 8)
        print(f"R3 same student, 8 parallel registrations: statuses={sorted(set(map(str, res)))} (500 = IntegrityError surfaced)")

        # R4: quota / per-item file cap on uploads (MAX 1 MB, quota 2 MB, 5 files per item)
        body = b"%PDF-1.4\n" + b"0" * (900 * 1024)
        evu = admin.post("/api/v1/events", json={"title": "Файлы", "scope": "institute", **when(2)}).json()
        # a student must be a manager to attach to an event: use the admin quota-free path for per-item, and a
        # student's own manual achievement for the per-user quota
        c = client(students[1])
        ach = c.post("/api/v1/achievements", json={"title": "Скан", "day": "2026-01-01"}).json()
        res = blast(lambda t: client(t).post(f"/api/v1/achievements/{ach['id']}/files", params={"name": "s.pdf"}, content=body).status_code,
                    [students[1]] * 12)
        got = c.get("/api/v1/achievements").json()[0]
        print(f"R4 per-item cap 5 files / quota 2 MB: 12 parallel 0.9 MB uploads: statuses={sorted(set(map(str, res)))} "
              f"-> files stored={len(got['attachments'])} ({len(got['attachments']) * 0.9:.1f} MB)  "
              f"{'CAP EXCEEDED' if len(got['attachments']) > 5 else 'ok'}")
        res = blast(lambda t: client(t).post(f"/api/v1/events/{evu['id']}/files", params={"name": "o.pdf"}, content=body).status_code,
                    [tokens[0]] * 12)
        got = admin.get(f"/api/v1/events/{evu['id']}").json()
        print(f"R4b admin, per-item cap 5, 12 parallel uploads: statuses={sorted(set(map(str, res)))} -> files={len(got['attachments'])}  "
              f"{'CAP EXCEEDED' if len(got['attachments']) > 5 else 'ok'}")
    finally:
        proc.terminate()
        print("server log tail:")
        try:
            print("".join(open(f"{WORK}/uvicorn.log").readlines()[-6:]))
        except Exception:
            pass


if __name__ == "__main__":
    main()
