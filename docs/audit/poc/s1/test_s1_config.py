"""S1: config hardening PoC - the CORS setup of main.py with ALLOWED_ORIGINS='*' (nothing in config.py rejects it)."""
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core import security
from app.core.config import _list


def test_wildcard_origin_with_credentials_defeats_the_csrf_header_FINDING(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    origins = _list("ALLOWED_ORIGINS")  # config.py accepts it as is
    assert origins == ["*"]
    app = Starlette(routes=[Route("/", lambda r: PlainTextResponse("ok"))])
    # the same arguments as server/main.py:97-103
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Content-Type", "Accept", security.CSRF_HEADER_NAME])
    r = TestClient(app).options("/", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST",
                                              "Access-Control-Request-Headers": "X-Requested-With"})
    # a foreign site is allowed to send credentialed requests WITH the X-Requested-With header
    assert r.headers["access-control-allow-origin"] == "https://evil.example"
    assert r.headers["access-control-allow-credentials"] == "true"
