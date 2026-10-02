"""R4: cold-cache stampede on GET /tribes/current, one uvicorn worker, local PostgreSQL (own instance on 127.0.0.1).
Usage: S3_DATABASE_URL=postgresql://postgres@127.0.0.1:54339/r4 python r4_load.py N P1,P2,...
Different from S3 PoC: several parallelism levels, and the cache is made cold the way production does it (a new student's first visit -> _auto_join -> clear_cache)."""
import concurrent.futures as cf, datetime as dt, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "s3"))
import common
from common import H, BASE, cookie, mk_user, start_server, stop_server
import httpx

N = int(sys.argv[1]); LEVELS = [int(x) for x in sys.argv[2].split(",")]
common.fresh_db()
import app.models as models
from app.db.database import SessionLocal
db = SessionLocal()
admin = mk_user(db, "admin", role="admin"); ck_admin = cookie(admin)
users = [models.User(username=f"r4-load-{i}", full_name=f"Load {i}", hashed_password="x", role="student", group_number=f"24-ИСбо-{i % 6 + 1}",
                     auth_source="eios", sdo_id=str(i)) for i in range(N)]
db.add_all(users); db.commit()
cks = [cookie(u) for u in users[:60]]
db.close()
srv = start_server(workers=1)
try:
    t = httpx.post(f"{BASE}/api/v1/tribes/tournaments", headers=H, cookies=ck_admin, json={"title": "r4", "starts_on": (dt.date.today() - dt.timedelta(days=1)).isoformat(),
        "ends_on": (dt.date.today() + dt.timedelta(days=30)).isoformat(), "tribe_names": ["A", "B", "C", "D"]}).json()
    r = httpx.post(f"{BASE}/api/v1/tribes/tournaments/{t['id']}/start", headers=H, cookies=ck_admin, timeout=300)
    tribe_id = r.json()["tribes"][0]["id"]
    for P in LEVELS:
        # an award clears the cache (response itself recomputes -> warm); then clear again by restarting is costly, so use a second award + discard:
        httpx.post(f"{BASE}/api/v1/tribes/{tribe_id}/awards", headers=H, cookies=ck_admin, json={"points": 1, "reason": "x"}, timeout=300)
        # that call computed the standings. To get a *cold* state, add a student that is not yet a member? (auto_join clears)
        db = SessionLocal()
        nu = models.User(username=f"r4-new-{P}-{time.time_ns()}", full_name="New", hashed_password="x", role="student", group_number="24-ИСбо-1", auth_source="eios", sdo_id=f"n{time.time_ns()}")
        db.add(nu); db.commit(); newck = cookie(nu); db.close()
        # the new student opens the tribe page: _auto_join clears the cache, then recomputes (this is request #0 and is cold)
        def cold(i):
            s = time.time(); ck = newck if i == 0 else cks[i % len(cks)]
            code = httpx.get(f"{BASE}/api/v1/tribes/current", cookies=ck, timeout=300).status_code
            return code, time.time() - s
        def probe(i):
            time.sleep(0.5); s = time.time(); code = httpx.get(f"{BASE}/api/v1/forum/questions", timeout=300).status_code
            return code, time.time() - s
        t0 = time.time()
        with cf.ThreadPoolExecutor(P + 4) as ex:
            futs = [ex.submit(cold, i) for i in range(P)] + [ex.submit(probe, i) for i in range(4)]
            res = [f.result() for f in futs]
        print(f"N={N} P={P}: all done {time.time() - t0:.1f}s; tribes slowest {max(x for _, x in res[:P]):.1f}s; forum probes {[round(x, 1) for _, x in res[P:]]}", flush=True)
finally:
    stop_server(srv)
