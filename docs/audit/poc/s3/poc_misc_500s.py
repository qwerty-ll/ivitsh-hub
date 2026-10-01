"""S3 PoC: unhandled 500s in the business endpoints (SQLite, in-process).

Run: python docs/audit/poc/s3/poc_misc_500s.py
 1. admin books the room for a non-existent association_id -> FK violation
 2. two requests of the same new student auto-joining a running tournament at once -> unique violation
"""
import concurrent.futures as cf
import datetime as dt

import common
from common import H, cookie, mk_user

common.fresh_db()
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402

db = SessionLocal()
admin = mk_user(db, "admin", role="admin")
base = [mk_user(db, f"s{i}") for i in range(4)]
ca = cookie(admin)
db.close()
now = dt.datetime.now(dt.timezone.utc)
day = (now + dt.timedelta(days=3)).astimezone(dt.timezone(dt.timedelta(hours=3))).date()
with TestClient(main.app, raise_server_exceptions=False) as _:
    A = TestClient(main.app, cookies=ca, raise_server_exceptions=False)
    r = A.post("/api/v1/bookings", headers=H, json={"resource": "room", "zone": "top", "association_id": 99999,
                                                    "starts_at": f"{day}T10:00:00+03:00", "ends_at": f"{day}T11:00:00+03:00"})
    print("1. booking for association 99999 ->", r.status_code)
    t = A.post("/api/v1/tribes/tournaments", headers=H, json={"title": "t", "starts_on": (dt.date.today() - dt.timedelta(days=1)).isoformat(),
               "ends_on": (dt.date.today() + dt.timedelta(days=5)).isoformat(), "tribe_names": ["A", "B"]}).json()
    print("   start:", A.post(f"/api/v1/tribes/tournaments/{t['id']}/start", headers=H).status_code)
    db = SessionLocal(); late = mk_user(db, "late"); lc = cookie(late); db.close()
    def hit(_):
        return TestClient(main.app, cookies=lc, raise_server_exceptions=False).get("/api/v1/tribes/current").status_code
    codes = []
    for _ in range(5):  # repeat: the race needs the two requests to overlap
        db = SessionLocal(); late = mk_user(db, "late"); lc = cookie(late); db.close()
        with cf.ThreadPoolExecutor(8) as ex:
            codes += list(ex.map(hit, range(8)))
    print("2. 5 x 8 parallel first visits of /tribes/current by a newcomer:", {c: codes.count(c) for c in set(codes)})
