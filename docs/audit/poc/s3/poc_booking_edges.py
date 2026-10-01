"""S3 PoC: booking edge cases (in-process, SQLite by default or PostgreSQL via S3_DATABASE_URL).

Run: python docs/audit/poc/s3/poc_booking_edges.py
Prints the HTTP status the API gives for each probe, with what the rules suggest it should be.
"""
import concurrent.futures as cf
import datetime as dt

import common
from common import H, cookie, mk_assoc, mk_user

common.fresh_db()
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import app.models as models  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402

MSK = dt.timezone(dt.timedelta(hours=3))
db = SessionLocal()
leader = mk_user(db, "leader")
a1 = mk_assoc(db, "S3 active", leader=leader)
a2 = mk_assoc(db, "S3 inactive", leader=leader)
a2.is_active = False
db.commit()
ck, aid1, aid2 = cookie(leader), a1.id, a2.id
db.close()
now = dt.datetime.now(dt.timezone.utc)
day = (now + dt.timedelta(days=5)).astimezone(MSK).date()
at = lambda hm, d=day: f"{d.isoformat()}T{hm}+03:00"

with TestClient(main.app):
    c = TestClient(main.app, cookies=ck)
    def book(**kw):
        body = dict(resource="room", zone="top", association_id=aid1, purpose="p")
        body.update(kw)
        return c.post("/api/v1/bookings", json=body, headers=H)
    def show(label, r, expect):
        print(f"{label:62s} -> {r.status_code}  (expected {expect})")
    show("08:00-09:00 (opening)", book(starts_at=at("08:00:00"), ends_at=at("09:00:00")), 201)
    show("20:00-21:00 (closing)", book(starts_at=at("20:00:00"), ends_at=at("21:00:00")), 201)
    show("07:55-08:30", book(starts_at=at("07:55:00"), ends_at=at("08:30:00")), 400)
    show("20:30-21:05", book(starts_at=at("20:30:00"), ends_at=at("21:05:00")), 400)
    show("23:00 - 01:00 next day (over midnight)", book(starts_at=at("23:00:00"), ends_at=at("01:00:00", day + dt.timedelta(days=1))), 400)
    show("10:00:00.700 - 11:00:00.700 (sub-second)", book(zone="bottom", starts_at=at("10:00:00.700"), ends_at=at("11:00:00.700")), "400 or 201?")
    show("same slot top 12:00-13:00 twice (2nd)", (book(starts_at=at("12:00:00"), ends_at=at("13:00:00")), book(starts_at=at("12:00:00"), ends_at=at("13:00:00")))[1], 409)
    show("whole vs top, 1 minute overlap at 13:00 (end 13:00 vs start 12:59)", book(zone="whole", starts_at=at("12:55:00"), ends_at=at("13:15:00")), 409)
    show("naive datetime 14:00 (no offset) = treated as UTC=17:00 MSK", book(zone="top", starts_at=f"{day}T14:00:00", ends_at=f"{day}T15:00:00"), "400/ or MSK 14:00?")
    n = c.get("/api/v1/bookings", params={"day": day.isoformat()}).json()["items"]
    print("   stored naive-14:00 booking shows in MSK as:", [i["starts_at"] for i in n if i["starts_at"].startswith(f"{day}T14")] or [i["starts_at"] for i in n][-1:])
    # partially in the past (started one hour ago)
    t0 = now - dt.timedelta(hours=1)
    mt = t0.astimezone(MSK)
    in_hours = dt.time(8) <= mt.time() and (mt + dt.timedelta(hours=2)).time() <= dt.time(21) and mt.date() == (mt + dt.timedelta(hours=2)).date()
    r = book(zone="bottom", starts_at=mt.replace(minute=mt.minute // 5 * 5, second=0, microsecond=0).isoformat(),
             ends_at=(mt + dt.timedelta(hours=2)).replace(minute=mt.minute // 5 * 5, second=0, microsecond=0).isoformat())
    print(f"started ~1h ago, ends in ~1h (in working hours={in_hours}) -> {r.status_code} (a booking that already started is accepted: back-dating)")
    # 90 days
    d90 = (now + dt.timedelta(days=90)).astimezone(MSK).date()
    show("exactly +90 days 10:00-11:00 (start <= now+90d?)", book(zone="bottom", starts_at=at("10:00:00", d90), ends_at=at("11:00:00", d90)), "201 or 400 depending on time of day")
    d91 = d90 + dt.timedelta(days=1)
    show("+91 days", book(zone="bottom", starts_at=at("10:00:00", d91), ends_at=at("11:00:00", d91)), 400)
    show("booking for an INACTIVE association the user leads", book(zone="bottom", association_id=aid2, starts_at=at("15:00:00"), ends_at=at("16:00:00")), "403/404")
    # max-upcoming race: 40 parallel bookings of distinct 15-min slots by one leader (limit: 10 upcoming)
    d = day + dt.timedelta(days=2)
    def slot(i):
        h, m = divmod(8 * 60 + i * 15, 60)
        s = f"{h:02d}:{m:02d}:00"
        e = f"{(8 * 60 + i * 15 + 15) // 60:02d}:{(8 * 60 + i * 15 + 15) % 60:02d}:00"
        return TestClient(main.app, cookies=ck).post("/api/v1/bookings", headers=H, json=dict(resource="room", zone="top", association_id=aid1, starts_at=at(s, d), ends_at=at(e, d))).status_code
    db = SessionLocal(); before = db.query(models.Booking).filter_by(cancelled_at=None).count(); db.close()
    with cf.ThreadPoolExecutor(40) as ex:
        res = list(ex.map(slot, range(40)))
    db = SessionLocal(); total = db.query(models.Booking).filter_by(cancelled_at=None).count(); db.close()
    print(f"parallel 40 distinct slots by ONE leader: 201={res.count(201)} (limit LEADER_MAX_UPCOMING=10 incl. the {before} he already holds) -> upcoming now {total}")
