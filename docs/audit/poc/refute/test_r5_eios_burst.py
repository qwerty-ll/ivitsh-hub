"""R5b: parallel wrong guesses at /auth/eios-login with a fake EIOS that answers in 300 ms; counts upstream calls."""
import asyncio, concurrent.futures as cf, collections, time
from conftest import CSRF, TestClient
from app.services import eios


def test_burst(app, monkeypatch):
    calls = []
    async def authenticate(u, p):
        calls.append(p); await asyncio.sleep(0.3); return None
    monkeypatch.setattr(eios, "authenticate", authenticate)
    for P in (11, 61, 200):
        calls.clear()
        from app.core import rate_limit; rate_limit.reset_all()
        def one(i):
            return TestClient(app).post("/api/v1/auth/eios-login", headers=CSRF, json={"consent": True, "username": "24-isbo-777", "password": f"g{i}"}).status_code
        t0 = time.time()
        with cf.ThreadPoolExecutor(P) as ex:
            codes = collections.Counter(ex.map(one, range(P)))
        print(f"P={P}: {dict(codes)}; upstream (fake EIOS) calls={len(calls)} (limit 5); {time.time() - t0:.1f}s")
