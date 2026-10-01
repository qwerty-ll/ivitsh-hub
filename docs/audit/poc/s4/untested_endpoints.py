"""List API routes that no test calls (routes of main.app diffed against literal URLs in server/tests/*.py).

Run from the repo root:  python docs/audit/poc/s4/untested_endpoints.py [--json]
Heuristic: a test "covers" a route when it contains  client.<method>("/api/v1/...")  whose path
(after replacing {..} placeholders and dropping the query string) matches the route template.
It says nothing about the quality of assertions; negative (403/404) cases are not distinguished.
"""
import json
import os
import re
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
SERVER = os.path.join(ROOT, "server")
TESTS = os.path.join(SERVER, "tests")

tmp = tempfile.mkdtemp(prefix="s4-routes-")
os.environ.update({
    "SECRET_KEY": "audit-secret-key-that-is-long-enough-123456",
    "DATABASE_URL": f"sqlite:///{tmp}/r.db",
    "UPLOAD_DIR": f"{tmp}/u",
    "ADMIN_USERNAME": "portal_admin",
    "ADMIN_PASSWORD": "x",
    "SDO_BASE_URL": "",
})
sys.path.insert(0, SERVER)
import main  # noqa: E402

# f-string placeholders may contain quotes: f"/api/v1/events/{ev['id']}/register"
CALL = re.compile(r"\.(get|post|put|patch|delete)\(\s*f?(?:\"(/api/v1(?:\{[^}]*\}|[^\"{])*)\"|'(/api/v1(?:\{[^}]*\}|[^'{])*)')")


def template_regex(path: str) -> re.Pattern:
    return re.compile("^" + re.sub(r"\{[^}]+\}", r"[^/]+", re.escape(path).replace(r"\{", "{").replace(r"\}", "}")) + "$")


def test_calls():
    calls = []  # (method, normalised path, file)
    for name in sorted(os.listdir(TESTS)):
        if not name.endswith(".py"):
            continue
        text = open(os.path.join(TESTS, name), encoding="utf-8").read()
        for method, dq, sq in CALL.findall(text):
            url = (dq or sq).split("?")[0]
            url = re.sub(r"\{[^}]*\}", "1", url)  # f-string placeholders -> a number
            calls.append((method.upper(), url, name))
    return calls


def main_():
    calls = test_calls()
    rows = []
    # FastAPI >= 0.14x keeps included routers lazy, so the OpenAPI schema is the reliable route list
    for path, item in sorted(main.app.openapi()["paths"].items()):
        if not path.startswith("/api/"):
            continue
        rx = re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(path)) + "$")
        for method, op in sorted(item.items()):
            if method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue
            method = method.upper()
            files = sorted({f for m, u, f in calls if m == method and rx.match(u)})
            rows.append({"method": method, "path": path, "tests": files, "endpoint": op.get("operationId", "")})
    untested = [r for r in rows if not r["tests"]]
    if "--json" in sys.argv:
        print(json.dumps({"total": len(rows), "untested": untested}, ensure_ascii=False, indent=1))
        return
    print(f"routes: {len(rows)}, without a test call: {len(untested)}\n")
    for r in untested:
        print(f"{r['method']:6} {r['path']:55} {r['endpoint']}")


if __name__ == "__main__":
    main_()
