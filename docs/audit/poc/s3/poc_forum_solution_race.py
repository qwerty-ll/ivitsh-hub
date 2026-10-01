"""S3 PoC: parallel "mark as solution" on two answers of one question (PostgreSQL, 2 workers).

Run: S3_DATABASE_URL=postgresql://postgres@127.0.0.1:54329/ivitsh python docs/audit/poc/s3/poc_forum_solution_race.py
Looks for questions that end up with two solutions (each pays 5 bits to its author) and for 5xx answers.
"""
import concurrent.futures as cf

import common
from common import H, BASE, cookie, mk_user, start_server, stop_server
import httpx

common.fresh_db()
import app.models as models
from app.db.database import SessionLocal
db = SessionLocal()
asker, b = mk_user(db, "asker"), mk_user(db, "answerer")
qs = []
for i in range(40):
    q = models.ForumQuestion(author_id=asker.id, title=f"q{i}", content="content content")
    db.add(q)
    db.flush()
    a1 = models.ForumAnswer(question_id=q.id, author_id=b.id, content="a1")
    a2 = models.ForumAnswer(question_id=q.id, author_id=b.id, content="a2")
    db.add_all([a1, a2])
    db.flush()
    qs.append((q.id, a1.id, a2.id))
db.commit()
ck = cookie(asker)
db.close()
srv = start_server(workers=2)
try:
    codes = []
    def toggle(aid):
        return httpx.post(f"{BASE}/api/v1/forum/answers/{aid}/solution", headers=H, cookies=ck, timeout=60).status_code
    for q, a1, a2 in qs:
        with cf.ThreadPoolExecutor(2) as ex:
            codes += list(ex.map(toggle, [a1, a2]))
    db = SessionLocal()
    both = sum(1 for q, *_ in qs if db.query(models.ForumAnswer).filter_by(question_id=q, is_solution=True).count() > 1)
    print(f"requests={len(codes)} 200={codes.count(200)} 5xx={sum(c >= 500 for c in codes)} questions with 2 solutions={both}")
finally:
    stop_server(srv)
