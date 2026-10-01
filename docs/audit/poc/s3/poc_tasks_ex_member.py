"""S3 PoC: an excluded member keeps access to the association's task they had handed in ("На проверке").

Run: python docs/audit/poc/s3/poc_tasks_ex_member.py
Steps: leader sets a task for the member -> member moves the card to review -> leader excludes the member
-> the ex-member still reads the task (comments, attachments list), comments, adds a link and moves the card.
Also shows an assignee pulling an accepted ("Готово") card back.
"""
import common
from common import H, cookie, mk_assoc, mk_user

common.fresh_db()
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402

db = SessionLocal()
leader, member = mk_user(db, "leader"), mk_user(db, "member")
assoc = mk_assoc(db, "S3 assoc", leader=leader, members=[member])
ck_l, ck_m, aid, mid = cookie(leader), cookie(member), assoc.id, member.id
db.close()

with TestClient(main.app):
    L, M = TestClient(main.app, cookies=ck_l), TestClient(main.app, cookies=ck_m)
    t = L.post("/api/v1/tasks", headers=H, json={"title": "Задача", "description": "Внутренний регламент", "association_id": aid, "to_all": True}).json()
    tid = t["id"]
    print("member -> review:", M.patch(f"/api/v1/tasks/{tid}/status", headers=H, json={"status": "review"}).status_code)
    print("leader excludes member:", L.delete(f"/api/v1/associations/{aid}/members/{mid}", headers=H).status_code)
    print("ex-member GET task      :", M.get(f"/api/v1/tasks/{tid}").status_code)
    print("ex-member comment       :", M.post(f"/api/v1/tasks/{tid}/comments", headers=H, json={"text": "я всё ещё тут"}).status_code)
    print("ex-member add link      :", M.post(f"/api/v1/tasks/{tid}/links", headers=H, json={"url": "https://example.org", "title": "x"}).status_code)
    print("ex-member move to todo  :", M.patch(f"/api/v1/tasks/{tid}/status", headers=H, json={"status": "todo"}).status_code)
    # accepted card pulled back by its assignee (member is excluded here, so use a fresh member)
    db = SessionLocal(); m2 = mk_user(db, "member2"); mk = __import__("app.models", fromlist=["x"]); 
    import app.models as models
    db.add(models.Membership(user_id=m2.id, association_id=aid, role="member", status="approved")); db.commit()
    ck2, m2id = cookie(m2), m2.id; db.close()
    M2 = TestClient(main.app, cookies=ck2)
    t2 = L.post("/api/v1/tasks", headers=H, json={"title": "Задача 2", "association_id": aid, "assignee_ids": [m2id]}).json()
    M2.patch(f"/api/v1/tasks/{t2['id']}/status", headers=H, json={"status": "review"})
    L.patch(f"/api/v1/tasks/{t2['id']}/status", headers=H, json={"status": "done", "user_id": m2id})
    r = M2.patch(f"/api/v1/tasks/{t2['id']}/status", headers=H, json={"status": "in_progress"})
    print("assignee pulls an ACCEPTED card back to in_progress:", r.status_code, r.json().get("status"))
