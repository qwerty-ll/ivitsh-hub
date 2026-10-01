"""S6 PoC: first-time EIOS sign-ins hash a throw-away bcrypt password inside `async def eios_login`,
i.e. on the event loop. While N new students sign in at once, even /health stalls.

    python docs/audit/poc/s6/poc_loop_block.py     (sandbox on :8766)
"""
import random
import threading
import time

import httpx

BASE = "http://127.0.0.1:8766"
H = {"X-Requested-With": "XMLHttpRequest"}
N = 20
base = random.randint(10000, 80000)
lat = []
stop = threading.Event()


def pinger():
    c = httpx.Client(base_url=BASE, timeout=60)
    while not stop.is_set():
        t = time.perf_counter()
        c.get("/api/v1/health")
        lat.append(time.perf_counter() - t)
        time.sleep(0.02)


def login(i):
    c = httpx.Client(base_url=BASE, headers=H, timeout=60)
    c.post("/api/v1/auth/eios-login", json={"username": f"st{base + i}", "password": "pw", "consent": True})


p = threading.Thread(target=pinger)
p.start()
time.sleep(0.5)
quiet = max(lat)
lat.clear()
t0 = time.perf_counter()
ts = [threading.Thread(target=login, args=(i,)) for i in range(N)]
[t.start() for t in ts]
[t.join() for t in ts]
total = time.perf_counter() - t0
stop.set()
p.join()
print(f"idle /health max latency: {quiet * 1000:.0f} ms")
print(f"{N} concurrent first sign-ins took {total:.1f} s; /health max latency during them: {max(lat) * 1000:.0f} ms (p50 {sorted(lat)[len(lat) // 2] * 1000:.0f} ms)")
import bcrypt
t = time.perf_counter(); bcrypt.hashpw(b"x", bcrypt.gensalt()); print(f"one bcrypt hash (rounds=12): {(time.perf_counter() - t) * 1000:.0f} ms of event-loop time per new user")
