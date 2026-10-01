"""PoC: per-student upload quota and per-item file limit are checked BEFORE the file is stored, so parallel uploads pass together.

routers/attachments.py:_store_file -> _check_limits() reads committed rows, then `await uploads.save(...)`; N requests started at
the same time all see "used = 0". Local server, quota lowered to 1 MB and 5 files per item to keep the run small
(defaults in production: 300 MB per student, 30 files per item).
Run from the repo root:  python docs/audit/poc/s4/poc_upload_quota_race.py
"""
import os
import subprocess
import sys
import tempfile
import threading
import time

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8795
WORK = tempfile.mkdtemp(prefix="s4-quota-")
env = {**os.environ, "S4_EXTRA_ENV": "MAX_UPLOAD_MB=1,USER_UPLOAD_QUOTA_MB=1,FILES_PER_ITEM=5"}
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "run_local_server.py"), str(PORT), "*", WORK], env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
B = f"http://127.0.0.1:{PORT}/api/v1"
H = {"X-Requested-With": "XMLHttpRequest"}
try:
    for _ in range(60):
        try:
            if httpx.get(f"{B}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    c = httpx.Client(timeout=60, headers=H)
    assert c.post(f"{B}/auth/eios-login", json={"username": "24-isbo-001", "password": "pw", "consent": True}).status_code == 200
    task = c.post(f"{B}/tasks", json={"title": "Личная", "color": "blue"}).json()["id"]
    body = b"%PDF-1.4\n" + b"0" * (900 * 1024)  # 0.9 MB
    codes = []

    def up(i):
        r = httpx.post(f"{B}/tasks/{task}/files", params={"name": f"f{i}.pdf"}, content=body, cookies=c.cookies, headers=H, timeout=60)
        codes.append(r.status_code)

    barrier = threading.Barrier(16)

    def go(i):
        barrier.wait()
        up(i)

    ts = [threading.Thread(target=go, args=(i,)) for i in range(16)]
    [t.start() for t in ts]; [t.join() for t in ts]
    stored = len([f for f in os.listdir(f"{WORK}/uploads") if f.endswith(".pdf")])
    print(f"16 parallel uploads of 0.9 MB, quota 1 MB, 5 files per task: accepted={codes.count(201)} rejected={sorted(set(codes) - {201})}"
          f" files on disk={stored} (~{stored * 0.9:.1f} MB)")
    seq = [httpx.post(f"{B}/tasks/{task}/files", params={"name": "again.pdf"}, content=body, cookies=c.cookies, headers=H).status_code]
    print("afterwards (sequential) the next upload is refused with", seq)
finally:
    proc.terminate()
