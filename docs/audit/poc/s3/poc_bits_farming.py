"""S3 PoC: how many bits can be minted without any real activity (SQLite, in-process, no EIOS).

Run: python docs/audit/poc/s3/poc_bits_farming.py
Scenarios (all within one semester, API calls only, nothing is edited in the DB except seeding users):
  A. one ordinary student, no rights: 10 junk homework entries + 15 junk answers to other people's questions
  B. a leader of an association with 3 friends: 12 "meetings" started a minute ago, 8 association events
     back-dated by 2 hours; the leader marks himself and the friends present
  D. an administrator who may not grant bits to himself: institute events (uncapped) + a tribe prize
  C. two students: A asks 15 questions, B answers each with "." and A marks them as solutions
Prints /api/v1/progress points per account.
"""
import datetime as dt

import common
from common import H, cookie, mk_assoc, mk_user

common.fresh_db()
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.core import rate_limit  # noqa: E402

db = SessionLocal()
a = mk_user(db, "solo")
q_author = mk_user(db, "asker")
leader = mk_user(db, "leader")
friends = [mk_user(db, f"friend{i}") for i in range(3)]
b = mk_user(db, "colluder_b")
c = mk_user(db, "colluder_a")
assoc = mk_assoc(db, "S3 fake assoc", leader=leader, members=friends)
ids = {u.username: u.id for u in [a, q_author, leader, b, c, *friends]}
cks = {u.username: cookie(u) for u in [a, q_author, leader, b, c, *friends]}
fid = [f.id for f in friends]
lid, aid_ = leader.id, assoc.id
names = {u.username: u for u in [a, q_author, leader, b, c, *friends]}
db.close()


def cl(user):
    cli = TestClient(main.app, cookies=cks[user.username])
    return cli


now = dt.datetime.now(dt.timezone.utc)
iso = lambda t: t.isoformat()
with TestClient(main.app):
    def points(user):
        r = cl(user).get("/api/v1/progress")
        return r.json()["points"], r.json()["facts"]

    # --- A: junk homework + junk answers (needs questions of other people)
    asker = cl(q_author)
    qids = []
    for i in range(15):
        r = asker.post("/api/v1/forum/questions", json={"title": f"Вопрос {i}", "content": "Просто вопрос для проверки " + str(i)}, headers=H)
        qids.append(r.json()["id"])
    rate_limit.reset_all()
    solo = cl(a)
    for i in range(10):
        assert solo.post("/api/v1/homework", json={"text": "x", "subject": ""}, headers=H).status_code in (200, 201)
    for qid in qids:
        assert solo.post(f"/api/v1/forum/questions/{qid}/answers", json={"content": "."}, headers=H).status_code == 200
    print("A. solo student, junk only        ->", points(a))

    # --- C: collusion: B answers A's questions, A marks them as solutions
    rate_limit.reset_all()
    asker_c = cl(c)
    qc = [asker_c.post("/api/v1/forum/questions", json={"title": f"Вопрос C {i}", "content": "Просто вопрос для проверки C" + str(i)}, headers=H).json()["id"] for i in range(15)]
    bcl = cl(b)
    for qid in qc:
        ans = bcl.post(f"/api/v1/forum/questions/{qid}/answers", json={"content": "."}, headers=H).json()
        assert asker_c.post(f"/api/v1/forum/answers/{ans['id']}/solution", headers=H).status_code == 200
    print("C. colluder B (answers+solutions) ->", points(b))

    # --- B: leader + 3 friends: fake meetings and events, back-dated by hours
    rate_limit.reset_all()
    lead = cl(leader)
    ok = 0
    for i in range(12):
        m = lead.post(f"/api/v1/associations/{aid_}/meetings", headers=H, json={
            "title": f"Собрание {i}", "starts_at": iso(now - dt.timedelta(minutes=1)), "ends_at": iso(now + dt.timedelta(minutes=30))})
        assert m.status_code == 201, m.text
        r = lead.put(f"/api/v1/meetings/{m.json()['id']}/attendance", json={"user_ids": [lid, *fid]}, headers=H)
        ok += r.status_code == 200
    print("B. meetings created+marked:", ok)
    for i in range(8):
        e = lead.post("/api/v1/events", headers=H, json={
            "title": f"Мероприятие {i}", "scope": "association", "association_id": aid_,
            "starts_at": iso(now - dt.timedelta(hours=3)), "ends_at": iso(now - dt.timedelta(hours=2))})
        assert e.status_code == 201, e.text
        eid = e.json()["id"]
        assert lead.post(f"/api/v1/events/{eid}/registrations", json={"user_ids": [lid, *fid], "role": "participant"}, headers=H).status_code == 200
        assert lead.put(f"/api/v1/events/{eid}/attendance", json={"user_ids": [lid, *fid]}, headers=H).status_code == 200
    print("B. leader (self-marked)           ->", points(leader))
    print("B. friend (marked by the leader)  ->", points(friends[0]))

    # --- D: the admin "may not grant bits to himself" (POST /bits/grants -> 403), but:
    rate_limit.reset_all()
    from app.db.database import SessionLocal as SL
    db = SL()
    adm = mk_user(db, "admin2", role="admin")
    ck_adm = cookie(adm)
    admid = adm.id
    db.close()
    A = TestClient(main.app, cookies=ck_adm)
    print("D0. admin grants bits to himself via /bits/grants ->", A.post("/api/v1/bits/grants", headers=H, json={"user_id": admid, "amount": 100, "reason": "x"}).status_code)
    for i in range(20):
        e = A.post("/api/v1/events", headers=H, json={"title": f"Институтское {i}", "scope": "institute",
                   "starts_at": iso(now - dt.timedelta(days=2 + i)), "ends_at": iso(now - dt.timedelta(days=2 + i) + dt.timedelta(hours=1))})
        assert e.status_code == 201, e.text
        eid = e.json()["id"]
        assert A.post(f"/api/v1/events/{eid}/registrations", json={"user_ids": [admid], "role": "participant"}, headers=H).status_code == 200
        assert A.put(f"/api/v1/events/{eid}/attendance", json={"user_ids": [admid]}, headers=H).status_code == 200
    r = A.get("/api/v1/progress").json()
    print("D1. admin, 20 own institute events (no cap on institute events) -> points", r["points"], "available to spend:", r["balance"]["available"])

    # --- D2: the same admin joins a tribe, awards it points and finishes the tournament: prize paid to him
    t = A.post("/api/v1/tribes/tournaments", headers=H, json={"title": "S3", "starts_on": (dt.date.today() - dt.timedelta(days=1)).isoformat(),
               "ends_on": (dt.date.today() + dt.timedelta(days=5)).isoformat(), "tribe_names": ["A", "B"], "prize_1": 500}).json()
    started = A.post(f"/api/v1/tribes/tournaments/{t['id']}/start", headers=H).json()
    tribe_id = started["tribes"][0]["id"]
    print("D2. admin moved into tribe:", A.put(f"/api/v1/tribes/tournaments/{t['id']}/members/{admid}", headers=H, json={"tribe_id": tribe_id}).status_code,
          "| awards his tribe +100:", A.post(f"/api/v1/tribes/{tribe_id}/awards", headers=H, json={"points": 100, "reason": "x"}).status_code)
    A.post(f"/api/v1/tribes/tournaments/{t['id']}/finish", headers=H)
    r = A.get("/api/v1/shop").json()
    print("D2. admin grants log after finish:", [(g["amount"], g["reason"][:40]) for g in r["grants"]])
