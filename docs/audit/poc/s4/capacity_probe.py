"""Small local capacity probe (SQLite, empty data, fake EIOS, ONE uvicorn worker): per-request cost of typical calls.

NOT a prediction for production (PostgreSQL, real data, real network): it only gives the floor of the app itself
and a way to get requests/second per CPU core. Run from the repo root:  python docs/audit/poc/s4/capacity_probe.py
200 sequential + 200 requests at concurrency 20 per endpoint.
"""
import concurrent.futures as cf
import os
import statistics
import subprocess
import sys
import tempfile
import time

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8793
WORK = tempfile.mkdtemp(prefix="s4-cap-")
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "run_local_server.py"), str(PORT), "*", WORK],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
BASE = f"http://127.0.0.1:{PORT}/api/v1"
H = {"X-Requested-With": "XMLHttpRequest"}
try:
    for _ in range(60):
        try:
            if httpx.get(f"{BASE}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    c = httpx.Client(timeout=30, headers=H)
    assert c.post(f"{BASE}/auth/eios-login", json={"username": "24-isbo-001", "password": "pw", "consent": True}).status_code == 200
    # one shared client: creating a client per request costs ~40 ms of TLS-context setup on the client side
    shared = httpx.Client(timeout=30, headers=H, cookies=dict(c.cookies), limits=httpx.Limits(max_connections=40), verify=False)
    paths = ["/health", "/auth/me", "/associations", "/tasks/my", "/events?view=upcoming", "/forum/questions", "/progress", "/shop", "/teachers"]
    print(f"{'endpoint':28} {'seq p50':>8} {'seq p95':>8} {'conc20 req/s':>13} {'conc20 p95':>11}")
    for p in paths:
        def one(_=None):
            t = time.perf_counter()
            r = shared.get(BASE + p)
            return r.status_code, time.perf_counter() - t
        seq = [one() for _ in range(200)]
        t0 = time.perf_counter()
        with cf.ThreadPoolExecutor(20) as ex:
            conc = list(ex.map(one, range(200)))
        wall = time.perf_counter() - t0
        codes = {s for s, _ in seq + conc}
        d = sorted(x for _, x in seq); dc = sorted(x for _, x in conc)
        print(f"{p:28} {statistics.median(d)*1000:6.1f}ms {d[int(len(d)*.95)]*1000:6.1f}ms {200/wall:11.0f}   {dc[int(len(dc)*.95)]*1000:8.0f}ms  codes={sorted(codes)}")
finally:
    proc.terminate()
