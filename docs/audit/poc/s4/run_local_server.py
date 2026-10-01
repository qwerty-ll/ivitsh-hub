"""Local sandbox server for the S4 PoCs: the real app under uvicorn, with a fake EIOS (no network).

    python docs/audit/poc/s4/run_local_server.py PORT FORWARDED_ALLOW_IPS WORKDIR

Every EIOS login with password "pw" succeeds (identity derived from the username). SDO is off.
uvicorn gets the same flags as infrastructure/docker/Dockerfile.server (--proxy-headers --forwarded-allow-ips=*)
when FORWARDED_ALLOW_IPS is "*".
"""
import os
import sys

port, allow, workdir = int(sys.argv[1]), sys.argv[2], sys.argv[3]
os.makedirs(workdir, exist_ok=True)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
os.environ.update({
    "SECRET_KEY": "audit-secret-key-that-is-long-enough-123456",
    "DATABASE_URL": f"sqlite:///{workdir}/s4.db",
    "UPLOAD_DIR": f"{workdir}/uploads",
    "ADMIN_USERNAME": "portal_admin",
    "ADMIN_PASSWORD": "Adm1n-Test-Password!",
    "COOKIE_SECURE": "false",
    "GIGACHAT_AUTH_KEY": "",
    "SDO_BASE_URL": "",
    # nothing may leave the machine: EIOS points at a closed local port, no proxy for the server process
    "EIOS_BASE_URL": "http://127.0.0.1:9/api",
})
# optional overrides for a PoC:  S4_EXTRA_ENV="MAX_UPLOAD_MB=1,USER_UPLOAD_QUOTA_MB=1"
for _pair in filter(None, os.environ.get("S4_EXTRA_ENV", "").split(",")):
    os.environ[_pair.split("=", 1)[0]] = _pair.split("=", 1)[1]
for _name in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_name, None)
sys.path.insert(0, os.path.join(ROOT, "server"))
os.chdir(os.path.join(ROOT, "server"))

import uvicorn  # noqa: E402
from app.services import eios  # noqa: E402


async def fake_authenticate(username, password):
    if password != "pw":
        return None
    return eios.EiosIdentity(eios_id=str(abs(hash(username)) % 10**6), full_name="Тест Тестов Тестович", group="24-ИСбо-1", avatar_url=None)

eios.authenticate = fake_authenticate

import main  # noqa: E402

uvicorn.run(main.app, host="127.0.0.1", port=port, proxy_headers=True, forwarded_allow_ips=allow, log_level="warning")
