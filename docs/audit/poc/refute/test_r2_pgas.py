"""R2: self-registration (before start) -> time passes (DB rows shifted, as if the clock moved) -> nobody marks -> summary."""
import io
from datetime import datetime, timedelta, timezone
from openpyxl import load_workbook
from conftest import login_student, login_admin, CSRF
import app.models as models


def test_unmarked(app, fake_eios, db):
    admin = login_admin(app)
    st = login_student(app, fake_eios, "24-isbo-001", full_name="Лентяев Лентяй Лентяевич")
    now = datetime.now(timezone.utc)
    iso = lambda d: d.isoformat()
    ids = []
    for i in range(3):
        r = admin.post("/api/v1/events", json={"title": f"Событие {i}", "scope": "institute", "starts_at": iso(now + timedelta(days=1)),
                                               "ends_at": iso(now + timedelta(days=1, hours=2)), "participant_limit": 50}, headers=CSRF)
        assert r.status_code in (200, 201), r.text
        ids.append(r.json()["id"])
        assert st.post(f"/api/v1/events/{ids[-1]}/register", json={}, headers=CSRF).status_code == 200
    # the clock moves 3 days forward: shift event times back in the DB (no organizer action)
    for e in db.query(models.Event).all():
        e.starts_at = e.starts_at - timedelta(days=4); e.ends_at = e.ends_at - timedelta(days=4)
    db.commit()
    rows = st.get("/api/v1/portfolio").json()["rows"]
    print("PORTFOLIO rows:", [(r["title"], r["role"]) for r in rows])
    ws = load_workbook(io.BytesIO(st.get("/api/v1/portfolio/export", params={"format": "xlsx"}).content)).active
    print("XLSX:", [[c.value for c in row] for row in ws.iter_rows(min_row=1, max_row=9)])
    pr = st.get("/api/v1/progress").json()
    print("BITS earned (progress):", {k: v for k, v in pr.items() if k in ("balance", "points", "total", "bits")})
    # admin-side report keeps the distinction
    s, e = (now - timedelta(days=30)).date().isoformat(), (now + timedelta(days=30)).date().isoformat()
    for path in ("/api/v1/events/report", "/api/v1/events/summary", "/api/v1/admin/events/report"):
        r = admin.get(path, params={"format": "xlsx", "start": s, "end": e})
        print("ADMIN", path, r.status_code, r.headers.get("content-type"))
        if r.status_code == 200:
            w = load_workbook(io.BytesIO(r.content)).active
            print([[c.value for c in row] for row in w.iter_rows(min_row=1, max_row=8)])
            break
