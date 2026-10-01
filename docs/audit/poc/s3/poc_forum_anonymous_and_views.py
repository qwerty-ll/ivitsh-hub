"""S3 PoC: forum is readable without signing in (author full names), and views_count grows on every anonymous GET.

Run: python docs/audit/poc/s3/poc_forum_anonymous_and_views.py
"""
import common
from common import H, cookie, mk_user

common.fresh_db()
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402

db = SessionLocal()
u = mk_user(db, "asker")
ck = cookie(u)
db.close()
with TestClient(main.app):
    qid = TestClient(main.app, cookies=ck).post("/api/v1/forum/questions", headers=H, json={"title": "Вопрос", "content": "Текст вопроса для проверки"}).json()["id"]
    anon = TestClient(main.app)
    r = anon.get("/api/v1/forum/questions")
    print("anonymous list ->", r.status_code, [(q["author_id"], q["author_name"]) for q in r.json()])
    TestClient(main.app, cookies=ck).post(f"/api/v1/forum/questions/{qid}/answers", headers=H, json={"content": "ответ"})
    print("anonymous answers ->", anon.get(f"/api/v1/forum/questions/{qid}/answers").status_code)
    for _ in range(50):
        anon.get(f"/api/v1/forum/questions/{qid}")
    print("views_count after 50 anonymous GETs:", anon.get(f"/api/v1/forum/questions/{qid}").json()["views_count"])
