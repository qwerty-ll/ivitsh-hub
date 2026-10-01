"""S3 PoC: parallel bookings of room 108 / laptops against 2 uvicorn workers.

Run (PostgreSQL):  S3_DATABASE_URL=postgresql://postgres@127.0.0.1:54329/ivitsh python docs/audit/poc/s3/poc_booking_race.py
  modes: with the real code (advisory lock) and with the advisory lock removed (process lock only).
Expected with the real code: exactly 1 room booking and laptops never above 5. Without the advisory lock
on 2 workers: several accepted bookings for the same slot (double booking).
"""
import concurrent.futures as cf
import datetime as dt
import sys

import common
from common import H, BASE, cookie, mk_assoc, mk_user, start_server, stop_server
import httpx


def run(app_target, label, n=60):
    common.fresh_db()
    from app.db.database import SessionLocal
    db = SessionLocal()
    admin = mk_user(db, "admin", role="admin")
    leaders = [mk_user(db, f"leader{i}") for i in range(4)]
    assocs = [mk_assoc(db, f"S3 assoc {i}", leader=l) for i, l in enumerate(leaders)]
    ck = [cookie(l) for l in leaders]
    aids = [a.id for a in assocs]
    db.close()
    srv = start_server(workers=2, app_target=app_target)
    try:
        day = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=3)).astimezone(dt.timezone(dt.timedelta(hours=3))).date()
        at = lambda hm: f"{day.isoformat()}T{hm}:00+03:00"

        def post(i, body):
            k = i % len(ck)
            r = httpx.post(BASE + "/api/v1/bookings", json=dict(body, association_id=aids[k]), headers=H, cookies=ck[k], timeout=60)
            return r.status_code

        with cf.ThreadPoolExecutor(n) as ex:
            room = list(ex.map(lambda i: post(i, dict(resource="room", zone="whole", starts_at=at("10:00"), ends_at=at("12:00"))), range(n)))
        print(f"[{label}] room 'whole' 10:00-12:00, {n} parallel requests: 201={room.count(201)} 409={room.count(409)} other={[c for c in room if c not in (201, 409)]}")
        # laptops: 5 total, each request wants 2 for the same slot -> at most 2 may succeed
        with cf.ThreadPoolExecutor(n) as ex:
            lap = list(ex.map(lambda i: post(i, dict(resource="laptops", laptops=2, starts_at=at("14:00"), ends_at=at("15:00"))), range(n)))
        ok = lap.count(201)
        print(f"[{label}] laptops x2 for 14:00-15:00, {n} parallel: 201={ok} (laptops granted={ok * 2} of 5) 409={lap.count(409)} other={[c for c in lap if c not in (201, 409)]}")
        return room.count(201), ok * 2
    finally:
        stop_server(srv)


if __name__ == "__main__":
    r1 = run("s3_app_nolock:app", "NO advisory lock, 2 workers")
    r2 = run("main:app", "REAL code, 2 workers")
    print("RESULT: real code ok =", r2 == (1, 4), "| without advisory lock double-booked =", r1[0] > 1 or r1[1] > 5)
