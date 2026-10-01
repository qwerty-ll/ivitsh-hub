"""S3 PoC (cross-check for the events owner): parallel self-registration against participant_limit (2 uvicorn workers).

Run: S3_DATABASE_URL=postgresql://postgres@127.0.0.1:54329/ivitsh python docs/audit/poc/s3/poc_event_limit_race.py
register() checks the limit with _check_place() and appends the row without any lock (events.py).
"""
import concurrent.futures as cf
import datetime as dt

import common
from common import H, BASE, cookie, mk_user, start_server, stop_server
import httpx

common.fresh_db()
import app.models as models
from app.db.database import SessionLocal
db = SessionLocal()
admin = mk_user(db, "admin", role="admin")
users = [mk_user(db, f"s{i}") for i in range(60)]
now = dt.datetime.now(dt.timezone.utc)
ev = models.Event(scope="institute", title="limit 3", starts_at=now + dt.timedelta(days=2), ends_at=now + dt.timedelta(days=2, hours=1),
                  participant_limit=3, created_by_id=admin.id)
db.add(ev)
db.commit()
eid = ev.id
cks = [cookie(u) for u in users]
db.close()
srv = start_server(workers=2)
try:
    with cf.ThreadPoolExecutor(60) as ex:
        codes = list(ex.map(lambda i: httpx.post(f"{BASE}/api/v1/events/{eid}/register", json={"role": "participant"}, headers=H, cookies=cks[i], timeout=60).status_code, range(60)))
    db = SessionLocal()
    n = db.query(models.EventRegistration).filter_by(event_id=eid).count()
    print(f"limit=3, 60 parallel registrations: 200={codes.count(200)} 409={codes.count(409)} other={sorted(set(codes) - {200, 409})} rows in DB={n}")
finally:
    stop_server(srv)
