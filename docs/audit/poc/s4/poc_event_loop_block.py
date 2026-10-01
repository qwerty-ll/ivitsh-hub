"""PoC / small local measurement: first-time EIOS sign-ins block the whole single-worker server.

routers/auth.py:eios_login is `async def` and, for a new student, calls security.get_password_hash() (bcrypt, ~300 ms of
CPU) and synchronous SQLAlchemy right on the event loop. While N new students sign in, even /api/v1/health stalls.
Safe: local server, fake EIOS, 16 logins + ~100 health probes.
Run from the repo root:  python docs/audit/poc/s4/poc_event_loop_block.py
"""
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8792
WORK = tempfile.mkdtemp(prefix="s4-loop-")
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "run_local_server.py"), str(PORT), "*", WORK],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
BASE = f"http://127.0.0.1:{PORT}/api/v1"
H = {"X-Requested-With": "XMLHttpRequest"}


def probe(stop, out):
    with httpx.Client(timeout=30) as c:
        while not stop.is_set():
            t = time.perf_counter()
            c.get(f"{BASE}/health")
            out.append(time.perf_counter() - t)
            time.sleep(0.05)


try:
    for _ in range(60):
        try:
            if httpx.get(f"{BASE}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.5)

    def login(name, results):
        t = time.perf_counter()
        r = httpx.post(f"{BASE}/auth/eios-login", json={"username": name, "password": "pw", "consent": True}, headers=H, timeout=60)
        results.append((r.status_code, time.perf_counter() - t))

    for label, n, repeat in (("idle", 0, False), ("16 NEW students at once", 16, False), ("same 16 again (already registered)", 16, True)):
        lat, res, stop = [], [], threading.Event()
        pt = threading.Thread(target=probe, args=(stop, lat)); pt.start()
        time.sleep(0.5)
        t0 = time.perf_counter()
        threads = [threading.Thread(target=login, args=(f"24-isbo-{i:03d}", res)) for i in range(n)]
        [t.start() for t in threads]; [t.join() for t in threads]
        time.sleep(0.5); stop.set(); pt.join()
        wall = time.perf_counter() - t0
        print(f"{label:38} health probes={len(lat):3d} median={statistics.median(lat)*1000:6.0f} ms max={max(lat)*1000:6.0f} ms"
              + (f" | logins ok={sum(1 for s, _ in res if s == 200)}/{n} slowest={max(d for _, d in res):.1f}s wall={wall:.1f}s" if n else ""))
finally:
    proc.terminate()
