"""S3 PoC: the ПГАС summary lists an ended event the student merely signed up for (attendance never marked).

Run: python docs/audit/poc/s3/poc_portfolio_unmarked.py
Bits are NOT paid for it (progress.facts needs attended=True), but /portfolio and /portfolio/export print it as participation.
"""
import datetime as dt

import common
from common import cookie, mk_user

common.fresh_db()
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import app.models as models  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402

db = SessionLocal()
admin, st = mk_user(db, "admin", role="admin"), mk_user(db, "student")
now = dt.datetime.now(dt.timezone.utc)
ev = models.Event(scope="institute", title="Круглый стол (на нём никого не отмечали)", starts_at=now - dt.timedelta(days=3, hours=1),
                  ends_at=now - dt.timedelta(days=3), created_by_id=admin.id)
db.add(ev)
db.flush()
# the student self-registered earlier (source=self) and nobody marked attendance afterwards: attended stays NULL
db.add(models.EventRegistration(event_id=ev.id, user_id=st.id, role="participant", source="self", attended=None))
db.commit()
ck = cookie(st)
db.close()
with TestClient(main.app):
    c = TestClient(main.app, cookies=ck)
    rows = c.get("/api/v1/portfolio").json()["rows"]
    print("portfolio rows:", [(r["title"], r["role"]) for r in rows])
    print("bits for it:", c.get("/api/v1/progress").json()["facts"]["events"])
    x = c.get("/api/v1/portfolio/export", params={"format": "xlsx"})
    print("xlsx export:", x.status_code, len(x.content), "bytes")
