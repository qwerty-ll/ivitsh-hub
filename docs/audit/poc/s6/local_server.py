"""Local sandbox server for the S6 audit: the real app on a temp SQLite DB, a fake EIOS, the built SPA.

Run from the repo root:
    S6_DIR=<scratch>/s6 python docs/audit/poc/s6/local_server.py        (port 8766)
Accounts: any login "stNN"/"leadNN" with password "pw"; "main" admin: portal_admin / Adm1n-Local-Pass!
No real external system is contacted: eios.authenticate and eios.fetch_json are replaced with fakes.
GET /__fake/stats returns how many upstream EIOS calls the portal made (used by the PoCs).
"""
import os
import sys
from datetime import date, timedelta

S6 = os.environ.get("S6_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "_run")
os.makedirs(S6, exist_ok=True)
os.environ.update({
    "SECRET_KEY": "s6-local-secret-key-for-sandbox-only-0123456789",
    "DATABASE_URL": f"sqlite:///{S6}/s6.db",
    "UPLOAD_DIR": f"{S6}/uploads",
    "ADMIN_USERNAME": "portal_admin",
    "ADMIN_PASSWORD": "Adm1n-Local-Pass!",
    "COOKIE_SECURE": "false",
    "GIGACHAT_AUTH_KEY": "",
    "SDO_BASE_URL": "",
    "EIOS_BASE_URL": "http://127.0.0.1:9/api",  # fail closed: nothing real can be reached
})
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "server"))

from fastapi import Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402

import main  # noqa: E402
from app.services import eios  # noqa: E402

STATS = {"fetch_json": 0, "authenticate": 0}
DIST = os.path.join(S6, "dist")


async def fake_authenticate(username, password):
    STATS["authenticate"] += 1
    if password != "pw" or not username.lower().startswith(("st", "lead", "x")):
        return None
    n = "".join(ch for ch in username if ch.isdigit()) or "0"
    group = "24-ИСбо-1" if int(n) % 2 else "24-ИСбо-2"
    return eios.EiosIdentity(eios_id=str(9000 + int(n)), full_name=f"Тестов{chr(1040 + int(n) % 26)} Иван Иванович",
                             group=group, avatar_url=None, group_id=101 if int(n) % 2 else 102)


async def fake_fetch_json(endpoint, params, timeout=5.0):
    STATS["fetch_json"] += 1
    if endpoint == "raspGrouplist":
        return {"state": 1, "data": [{"id": 101, "name": "24-ИСбо-1"}, {"id": 102, "name": "24-ИСбо-2"}]}
    if endpoint == "Rasp":
        rows = []
        today = date.today()
        for i in range(-3, 14):
            d = today + timedelta(days=i)
            if d.weekday() < 6:
                rows.append({"дата": d.isoformat(), "начало": "08:30", "конец": "10:00", "дисциплина": "лек Базы данных",
                             "аудитория": "Б-407", "преподаватель": "Петров П. П.", "группа": "24-ИСбо-1", "номерПодгруппы": 0})
                rows.append({"дата": d.isoformat(), "начало": "10:10", "конец": "11:40", "дисциплина": "пр Python, п/г 1",
                             "аудитория": "Б-108", "преподаватель": "Сидоров С. С.", "группа": "24-ИСбо-1", "номерПодгруппы": 1})
        return {"state": 1, "data": {"rasp": rows}}
    if endpoint in ("raspTeacherlist", "raspAudlist", "Rasp/ListYears"):
        return {"state": 1, "data": []}
    return None


eios.authenticate = fake_authenticate
eios.fetch_json = fake_fetch_json


@main.app.get("/__fake/stats")
def fake_stats():
    return STATS


@main.app.get("/{path:path}", include_in_schema=False)
def spa(path: str, request: Request):
    if path.startswith("api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    target = os.path.join(DIST, path)
    if path and os.path.isfile(target):
        return FileResponse(target)
    return FileResponse(os.path.join(DIST, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(main.app, host="127.0.0.1", port=int(os.environ.get("S6_PORT", "8766")), log_level="warning")
