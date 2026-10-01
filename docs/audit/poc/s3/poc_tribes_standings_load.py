"""S3 PoC: cost of the tribe standings (cache miss) with N students, and a stampede of parallel first requests.

Run: S3_DATABASE_URL=postgresql://postgres@127.0.0.1:54329/ivitsh python docs/audit/poc/s3/poc_tribes_standings_load.py [N=600] [PARALLEL=20]
One uvicorn worker (as deployed). Reports the time of one cold GET /tribes/current and of PARALLEL simultaneous cold requests,
plus how many other requests (GET /health) were slowed meanwhile.
"""
import concurrent.futures as cf
import datetime as dt
import sys
import time

import common
from common import H, BASE, cookie, mk_user, start_server, stop_server
import httpx

N = int(sys.argv[1]) if len(sys.argv) > 1 else 600
PAR = int(sys.argv[2]) if len(sys.argv) > 2 else 20
common.fresh_db()
import app.models as models
from app.db.database import SessionLocal
db = SessionLocal()
admin = mk_user(db, "admin", role="admin")
ck_admin = cookie(admin)
users = [models.User(username=f"s3-load-{i}", full_name=f"Load {i}", hashed_password="x", role="student", group_number=f"24-ИСбо-{i % 6 + 1}",
                     auth_source="eios", sdo_id=str(i)) for i in range(N)]
db.add_all(users)
db.commit()
ck_user = cookie(users[0])
db.close()
srv = start_server(workers=1)
try:
    t = httpx.post(f"{BASE}/api/v1/tribes/tournaments", headers=H, cookies=ck_admin, json={
        "title": "load", "starts_on": (dt.date.today() - dt.timedelta(days=1)).isoformat(),
        "ends_on": (dt.date.today() + dt.timedelta(days=30)).isoformat(), "tribe_names": ["A", "B", "C", "D"]}).json()
    t0 = time.time()
    r = httpx.post(f"{BASE}/api/v1/tribes/tournaments/{t['id']}/start", headers=H, cookies=ck_admin, timeout=300)
    print(f"N={N}: start -> {r.status_code} in {time.time() - t0:.1f}s (also computes standings once)")
    # cold cache again: finish clears it; instead restart-free trick: wait for TTL is 300s, so use a new tournament-free path:
    from_cache = time.time(); httpx.get(f"{BASE}/api/v1/tribes/current", cookies=ck_user, timeout=300); print(f"warm GET: {time.time() - from_cache:.2f}s")
    tribe_id = r.json()['tribes'][0]['id']
    # an admin award clears the cache and its response recomputes the standings: that call is a cold compute
    t0 = time.time()
    code = httpx.post(f"{BASE}/api/v1/tribes/{tribe_id}/awards", headers=H, cookies=ck_admin, json={"points": 1, "reason": "x"}, timeout=300).status_code
    print(f"cold compute (award response, includes standings): {code} in {time.time() - t0:.2f}s")
    # restart the worker: the cache is per process and now empty
    stop_server(srv)
    srv = start_server(workers=1)
    def cold(i):
        s = time.time()
        code = httpx.get(f"{BASE}/api/v1/tribes/current", cookies=ck_user, timeout=300).status_code
        return code, time.time() - s

    def probe(i):
        time.sleep(1.0)
        s = time.time()
        code = httpx.get(f"{BASE}/api/v1/forum/questions", timeout=300).status_code
        return code, time.time() - s
    t0 = time.time()
    with cf.ThreadPoolExecutor(PAR + 5) as ex:
        futs = [ex.submit(cold, i) for i in range(PAR)] + [ex.submit(probe, i) for i in range(5)]
        res = [f.result() for f in futs]
    print(f"{PAR} simultaneous cold requests: all done in {time.time() - t0:.1f}s; codes={sorted({c for c, _ in res[:PAR]})}; "
          f"slowest={max(x for _, x in res[:PAR]):.1f}s; unrelated forum list during the stampede: {[round(x, 1) for _, x in res[PAR:]]} s")
finally:
    stop_server(srv)
