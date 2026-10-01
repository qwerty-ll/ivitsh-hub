"""S6 end-to-end scenario checks on the sandbox (after seed_scenarios.py). Prints what happens in cross-cutting cases."""
from datetime import datetime, timedelta, timezone

import httpx

BASE = "http://127.0.0.1:8766"
H = {"X-Requested-With": "XMLHttpRequest"}
now = datetime.now(timezone.utc)
iso = lambda d: d.isoformat()  # noqa: E731


def login(user, pw="pw", admin=False):
    c = httpx.Client(base_url=BASE, headers=H, timeout=60)
    path, body = ("/api/v1/auth/admin-login", {"username": user, "password": pw}) if admin else (
        "/api/v1/auth/eios-login", {"username": user, "password": pw, "consent": True})
    r = c.post(path, json=body)
    assert r.status_code == 200, r.text
    c.me = r.json()["user"]
    return c


import random

a = login("portal_admin", "Adm1n-Local-Pass!", admin=True)
lead = login("st01")
aid = next(x["id"] for x in a.get("/api/v1/admin/associations").json() if x["name"] == "ВИТШ медиа")
a.put(f"/api/v1/admin/associations/{aid}/leaders/{lead.me['id']}")


def member():
    c = login(f"st{random.randint(1000, 99999)}")
    c.post(f"/api/v1/associations/{aid}/apply", json={})
    lead.post(f"/api/v1/associations/{aid}/members/{c.me['id']}/decision", json={"approve": True})
    return c


m2, m3 = member(), member()

print("== 1. Task for ALL members is a snapshot: a member approved later never sees it")
t = lead.post("/api/v1/tasks", json={"title": "Задача всем (snapshot)", "association_id": aid, "to_all": True}).json()
late = login(f"st{random.randint(1000, 99999)}")
late.post(f"/api/v1/associations/{aid}/apply", json={})
lead.post(f"/api/v1/associations/{aid}/members/{late.me['id']}/decision", json={"approve": True})
titles = [c["title"] for c in late.get("/api/v1/tasks/my").json()]
print("   newcomer's board:", titles, "(the task form warns: 'Кто вступит позже, её не получит')")
print("   leader's progress line: total =", [x for x in lead.get("/api/v1/tasks/managed").json() if x["id"] == t["id"]][0]["total"], "(the newcomer is not counted, no hint in the UI)")

print("== 2. Excluding the only assignee leaves an empty task")
solo = lead.post("/api/v1/tasks", json={"title": "Только для st03", "association_id": aid, "assignee_ids": [m3.me["id"]]}).json()
lead.delete(f"/api/v1/associations/{aid}/members/{m3.me['id']}")
row = [x for x in lead.get("/api/v1/tasks/managed").json() if x["id"] == solo["id"]][0]
print("   task after exclusion: total =", row["total"], "counts =", row["counts"], "-> stays in the leader's list with 0 assignees")
print("   st03 board has it?:", any(c["id"] == solo["id"] for c in m3.get("/api/v1/tasks/my").json()))

print("== 3. Leader removed by admin while work waits for review: who can accept?")
t2 = lead.post("/api/v1/tasks", json={"title": "На проверке без руководителя", "association_id": aid, "assignee_ids": [m2.me["id"]]}).json()
m2.patch(f"/api/v1/tasks/{t2['id']}/status", json={"status": "review"})
a.delete(f"/api/v1/admin/associations/{aid}/leaders/{lead.me['id']}")
r = lead.patch(f"/api/v1/tasks/{t2['id']}/status", json={"status": "done", "user_id": m2.me["id"]})
print("   old leader accepts ->", r.status_code, r.json().get("detail"))
r = m2.patch(f"/api/v1/tasks/{t2['id']}/status", json={"status": "done"})
print("   student sets done ->", r.status_code, r.json().get("detail"))
a.put(f"/api/v1/admin/associations/{aid}/leaders/{lead.me['id']}")  # restore

print("== 4. Student can pull an accepted task back out of 'Готово' (acceptance is not final)")
t3 = lead.post("/api/v1/tasks", json={"title": "Принятая задача", "association_id": aid, "assignee_ids": [m2.me["id"]], "due_at": iso(now + timedelta(days=2))}).json()
m2.patch(f"/api/v1/tasks/{t3['id']}/status", json={"status": "review"})
lead.patch(f"/api/v1/tasks/{t3['id']}/status", json={"status": "done", "user_id": m2.me["id"]})
r = m2.patch(f"/api/v1/tasks/{t3['id']}/status", json={"status": "in_progress"})
print("   student moves done -> in_progress:", r.status_code, r.json().get("status"), "completed_at:", r.json().get("completed_at"))
r = m2.patch(f"/api/v1/tasks/{t3['id']}/status", json={"status": "review"})
print("   and back to review: completed_at is re-stamped ->", r.json().get("completed_at"))
a.delete(f"/api/v1/admin/associations/{aid}/leaders/{lead.me['id']}"); a.put(f"/api/v1/admin/associations/{aid}/leaders/{lead.me['id']}")

print("== 5. Deleting a user who leads an association")
u9 = login(f"st{random.randint(1000, 99999)}")
a.put(f"/api/v1/admin/associations/{aid}/leaders/{u9.me['id']}")
r = a.delete(f"/api/v1/admin/users/{u9.me['id']}")
leaders = [l["id"] for l in [x for x in a.get("/api/v1/admin/associations").json() if x["id"] == aid][0]["leaders"]]
print("   delete leader ->", r.status_code, "| leader ids now:", leaders, "(no warning to the admin that tasks/work lose their reviewer)")

print("== 6. Group typed at login is accepted when EIOS gives none (self-asserted group opens another group's homework)")
x = httpx.Client(base_url=BASE, headers=H, timeout=60)
print("   (needs EIOS profile failure: cannot be forced with the fake; code path auth.py:eios_login 'group = identity.group or req.group_number')")
