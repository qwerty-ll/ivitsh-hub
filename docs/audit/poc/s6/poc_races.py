"""S6 PoC: concurrent requests against the local sandbox (docs/audit/poc/s6/local_server.py on :8766).

    python docs/audit/poc/s6/poc_races.py [event|apply|shop|booking|amplify|all]

Prints what the server did; every check says OK or BUG. Only the local sandbox is contacted.
"""
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone

import httpx

BASE = "http://127.0.0.1:8766"
H = {"X-Requested-With": "XMLHttpRequest"}
RUN = uuid.uuid4().hex[:4]


def client() -> httpx.Client:
    return httpx.Client(base_url=BASE, headers=H, timeout=60)


def student(name: str) -> httpx.Client:
    c = client()
    r = c.post("/api/v1/auth/eios-login", json={"username": name, "password": "pw", "consent": True})
    assert r.status_code == 200, r.text
    return c


def admin() -> httpx.Client:
    c = client()
    r = c.post("/api/v1/auth/admin-login", json={"username": "portal_admin", "password": "Adm1n-Local-Pass!"})
    assert r.status_code == 200, r.text
    return c


def burst(fn, n, *args):
    out, barrier = [None] * n, threading.Barrier(n)

    def run(i):
        barrier.wait()
        try:
            out[i] = fn(i, *args)
        except Exception as exc:  # noqa: BLE001
            out[i] = f"EXC {exc}"

    ts = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return out


def codes(rs):
    d = {}
    for r in rs:
        k = r.status_code if hasattr(r, "status_code") else str(r)
        d[k] = d.get(k, 0) + 1
    return d


def event_race():
    """participant_limit=3, 25 students register at once; plus one student double-clicking."""
    a = admin()
    start = datetime.now(timezone.utc) + timedelta(days=2)
    ev = a.post("/api/v1/events", json={"title": f"race-{RUN}", "scope": "institute", "starts_at": start.isoformat(),
                                        "ends_at": (start + timedelta(hours=2)).isoformat(), "participant_limit": 3}).json()
    users = [student(f"st{RUN[:2]}{i:02d}".replace("a", "1").replace("b", "2").replace("c", "3").replace("d", "4").replace("e", "5").replace("f", "6")) for i in range(25)]
    rs = burst(lambda i: users[i].post(f"/api/v1/events/{ev['id']}/register", json={"role": "participant"}), 25)
    got = a.get(f"/api/v1/events/{ev['id']}").json()
    print("register codes:", codes(rs), "| registered participants:", got["participants"], "(limit 3)")
    print("  ->", "OK" if got["participants"] <= 3 else "BUG: participant_limit exceeded")
    # double click by one student
    dbl = student(f"st{int(RUN, 16) % 90 + 10}")
    ev2 = a.post("/api/v1/events", json={"title": f"dbl-{RUN}", "scope": "institute", "starts_at": start.isoformat(),
                                         "ends_at": (start + timedelta(hours=2)).isoformat()}).json()
    rs = burst(lambda i: dbl.post(f"/api/v1/events/{ev2['id']}/register", json={"role": "participant"}), 12)
    print("double-click register codes:", codes(rs))
    print("  ->", "OK" if all(getattr(r, "status_code", 0) < 500 for r in rs) else "BUG: 5xx on a duplicate registration (unique constraint not handled)")


def apply_race():
    a = admin()
    assoc = a.post("/api/v1/admin/associations", json={"name": f"Клуб {RUN}"}).json()
    u = student(f"st{int(RUN, 16) % 80 + 100}")
    rs = burst(lambda i: u.post(f"/api/v1/associations/{assoc['id']}/apply", json={}), 12)
    print("double-click apply codes:", codes(rs))
    print("  ->", "OK" if all(getattr(r, "status_code", 0) < 500 for r in rs) else "BUG: 5xx on duplicate application")


def shop_race():
    a = admin()
    item = a.post("/api/v1/shop/items", json={"title": f"Кружка {RUN}", "price": 10, "stock": 1, "per_user_limit": 1}).json()
    users = [student(f"st{300 + i}") for i in range(10)]
    ids = [u.get("/api/v1/auth/me").json()["id"] for u in users]
    for uid in ids:
        a.post("/api/v1/bits/grants", json={"user_id": uid, "amount": 100, "reason": "poc"})
    rs = burst(lambda i: users[i].post(f"/api/v1/shop/items/{item['id']}/buy"), 10)
    sold = [x for x in a.get("/api/v1/shop/admin?status=all").json()["items"] if x["id"] == item["id"]][0]
    print("buy codes:", codes(rs), "| sold:", sold["sold"], "stock left:", sold["stock"])
    print("  ->", "OK (stock 1 sold once)" if sold["sold"] == 1 and sold["stock"] == 0 else "BUG: oversold")


def booking_race():
    a = admin()
    day = (datetime.now(timezone.utc) + timedelta(days=5)).astimezone(timezone(timedelta(hours=3))).date()
    body = {"resource": "room", "zone": "top", "starts_at": f"{day}T09:00:00+03:00", "ends_at": f"{day}T10:00:00+03:00", "purpose": RUN}
    rs = burst(lambda i: a.post("/api/v1/bookings", json=body), 15)
    print("booking codes:", codes(rs))
    print("  ->", "OK" if codes(rs).get(201, 0) == 1 else "BUG: double booking")


def amplify():
    """Anonymous GETs with distinct sdate values each cost one upstream EIOS request."""
    c = httpx.Client(base_url=BASE, timeout=30)
    before = c.get("/__fake/stats").json()["fetch_json"]
    for i in range(200):
        d = (datetime(2026, 1, 1) + timedelta(days=i)).date().isoformat()
        c.get("/api/v1/schedule/rasp", params={"idGroup": 101, "year": "2026-2027", "sdate": d})
    after = c.get("/__fake/stats").json()["fetch_json"]
    print(f"200 anonymous requests -> {after - before} upstream EIOS calls (no login, no per-IP app limit)")
    print("  ->", "BUG: caller controls the cache key" if after - before > 150 else "OK")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in (("event", event_race), ("apply", apply_race), ("shop", shop_race), ("booking", booking_race), ("amplify", amplify)):
        if which in (name, "all"):
            print(f"== {name}")
            fn()
