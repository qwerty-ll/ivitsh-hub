"""R4: count SQL statements per cold GET /tribes/current for N members (SQLite, in-process; NOT a timing test)."""
import os, time
from datetime import date, timedelta
from sqlalchemy import event
from conftest import login_admin, CSRF, TestClient
import app.models as models
from app.db.database import engine, SessionLocal
from app.services import tribes as tribes_service

N = int(os.environ.get("R4_N", "200"))


def test_queries(app, fake_eios, db):
    admin = login_admin(app)
    users = [models.User(username=f"r4-{i}", full_name=f"Load {i}", hashed_password="x", role="student", group_number=f"24-ИСбо-{i % 6 + 1}",
                         auth_source="eios", sdo_id=str(i)) for i in range(N)]
    db.add_all(users); db.commit()
    t = admin.post("/api/v1/tribes/tournaments", headers=CSRF, json={"title": "r4", "starts_on": (date.today() - timedelta(days=1)).isoformat(),
                   "ends_on": (date.today() + timedelta(days=30)).isoformat(), "tribe_names": ["A", "B", "C", "D"]}).json()
    assert admin.post(f"/api/v1/tribes/tournaments/{t['id']}/start", headers=CSRF).status_code == 200
    from app.core import security
    uname = users[0].username
    c = TestClient(app)
    c.cookies.update({k: v for k, v in admin.cookies.items()})  # any logged-in user is enough to read; admin sees all members
    counter = {"n": 0}
    def cnt(*a, **k): counter["n"] += 1
    event.listen(engine, "before_cursor_execute", cnt)
    tribes_service.clear_cache(); counter["n"] = 0
    t0 = time.time(); r = c.get("/api/v1/tribes/current"); cold = time.time() - t0
    q_cold = counter["n"]
    counter["n"] = 0; t0 = time.time(); c.get("/api/v1/tribes/current"); warm = time.time() - t0
    print(f"N={N} cold: {q_cold} queries ({q_cold / N:.1f}/member) {cold:.2f}s sqlite; warm: {counter['n']} queries {warm:.3f}s")
