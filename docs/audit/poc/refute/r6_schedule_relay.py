"""R6: anonymous /schedule/* -> how many calls reach a LOCAL fake upstream (127.0.0.1 counter, no real EIOS).
Local single-worker uvicorn (SQLite); EIOS_BASE_URL points at the counter."""
import concurrent.futures as cf, http.server, json, os, sys, threading, time, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "s3"))
UP = 8199
os.environ["EIOS_BASE_URL"] = f"http://127.0.0.1:{UP}/api"
import common
from common import BASE, start_server, stop_server
import httpx
hits = collections.Counter(); lock = threading.Lock()
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        with lock: hits[self.path] += 1
        body = json.dumps({"state": 1, "data": [{"id": 1, "name": "x"}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
srv_up = http.server.ThreadingHTTPServer(("127.0.0.1", UP), H); threading.Thread(target=srv_up.serve_forever, daemon=True).start()
common.fresh_db()
srv = start_server(workers=1)
try:
    def burst(label, urls, par=50):
        before = sum(hits.values()); t0 = time.time()
        with cf.ThreadPoolExecutor(par) as ex:
            codes = collections.Counter(ex.map(lambda u: httpx.get(BASE + u, timeout=60).status_code, urls))
        el = time.time() - t0
        print(f"{label}: {len(urls)} anon requests -> {dict(codes)}; upstream calls={sum(hits.values()) - before}; {len(urls) / el:.0f} req/s", flush=True)
    burst("same URL x200 (cache works)", ["/api/v1/schedule/rasp?idGroup=5&year=2026-2027"] * 200)
    burst("distinct idGroup x600 (nonexistent groups)", [f"/api/v1/schedule/rasp?idGroup={i}&year=2026-2027" for i in range(1000, 1600)])
    burst("distinct sdate x300 (same group)", [f"/api/v1/schedule/rasp?idGroup=5&year=2026-2027&sdate=2026-{1 + i // 28 % 12:02d}-{1 + i % 28:02d}&idAud={i}" for i in range(300)])
    burst("distinct year x300", [f"/api/v1/schedule/groups?year={2000 + i // 10 % 100}-{2001 + i // 10 % 100}" for i in range(300)])
finally:
    stop_server(srv); srv_up.shutdown()
