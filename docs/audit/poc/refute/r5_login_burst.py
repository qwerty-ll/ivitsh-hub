"""R5: parallel wrong-password bursts at /auth/admin-login against a local single-worker uvicorn (SQLite, no external calls).
Usage: python r5_login_burst.py [primed|fresh] P
 primed = the env admin already logged in once (a DB row exists -> every wrong guess costs one bcrypt check)
 fresh  = admin never logged in (no DB row -> guess is a plain compare_digest, no bcrypt)"""
import concurrent.futures as cf, os, sys, time, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "s3"))
os.environ["EIOS_BASE_URL"] = "http://127.0.0.1:9"  # never a real host
import common
from common import H, BASE, start_server, stop_server
import httpx
mode, P = sys.argv[1], int(sys.argv[2])
common.fresh_db()
srv = start_server(workers=1)
try:
    url = f"{BASE}/api/v1/auth/admin-login"
    if mode == "primed":
        r = httpx.post(url, headers=H, json={"username": os.environ["ADMIN_USERNAME"], "password": os.environ["ADMIN_PASSWORD"]})
        assert r.status_code == 200, r.status_code
    def guess(i):
        s = time.time()
        r = httpx.post(url, headers=H, json={"username": os.environ["ADMIN_USERNAME"], "password": f"wrong-{i}"}, timeout=120)
        return r.status_code, time.time() - s
    t0 = time.time()
    with cf.ThreadPoolExecutor(P) as ex:
        res = list(ex.map(guess, range(P)))
    el = time.time() - t0
    c = collections.Counter(code for code, _ in res)
    print(f"{mode} P={P}: {dict(c)} in {el:.1f}s -> {c[401]} guesses actually evaluated (limit would allow 5); {c[401] / el:.1f} guesses/s")
finally:
    stop_server(srv)
