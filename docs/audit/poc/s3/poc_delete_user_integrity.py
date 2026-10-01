"""S3 PoC: what deleting a user does to bits, orders, tasks (PostgreSQL or SQLite).

Run: S3_DATABASE_URL=postgresql://postgres@127.0.0.1:54329/ivitsh python docs/audit/poc/s3/poc_delete_user_integrity.py
 1. delete a student who owns orders/grants/tribe seat/bookings/forum posts -> does it work, what disappears
 2. delete the LEADER who created a task that a member handed in on time -> member's on-time bits vanish
    (Task.created_by_id becomes NULL and `created_by_id != user.id` is NULL in SQL -> row filtered out)
"""
import datetime as dt

import common
from common import H, cookie, mk_assoc, mk_user

common.fresh_db()
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import app.models as models  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.services import progress  # noqa: E402

db = SessionLocal()
admin = mk_user(db, "admin", role="admin")
victim = mk_user(db, "victim")
leader = mk_user(db, "leader")
member = mk_user(db, "member")
asoc = mk_assoc(db, "S3 assoc", leader=leader, members=[member, victim])
item = models.ShopItem(title="mug", price=5, stock=3)
db.add(item)
db.flush()
db.add(models.BitsGrant(user_id=victim.id, amount=50, reason="seed", created_by_id=admin.id))
db.add(models.ShopOrder(user_id=victim.id, item_id=item.id, item_title="mug", price=5))
db.add(models.Booking(resource="room", zone="top", starts_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1),
                      ends_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1, hours=1), booked_by_id=victim.id, association_id=asoc.id))
q = models.ForumQuestion(author_id=victim.id, title="victim q", content="victim question text")
db.add(q)
db.flush()
db.add(models.ForumAnswer(question_id=q.id, author_id=member.id, content="answer of someone else"))
db.add(models.Vote(user_id=victim.id, question_id=q.id, vote_type=1))
# a task of the leader handed in on time by the member (created 2 days ago, due yesterday... completed 1.5 days ago)
now = dt.datetime.now(dt.timezone.utc)
t = models.Task(association_id=asoc.id, created_by_id=leader.id, title="t", created_at=now - dt.timedelta(days=3), due_at=now - dt.timedelta(days=1))
db.add(t)
db.flush()
db.add(models.TaskAssignee(task_id=t.id, user_id=member.id, status="done", completed_at=now - dt.timedelta(days=2)))
db.commit()
ck, vid, lid, mid, item_id = cookie(admin), victim.id, leader.id, member.id, item.id
db.close()

with TestClient(main.app):
    A = TestClient(main.app, cookies=ck)
    db = SessionLocal(); m = db.get(models.User, mid)
    print("member on_time before:", progress.facts(db, m)["on_time"]); db.close()
    r = A.delete(f"/api/v1/admin/users/{vid}", headers=H)
    print("delete victim ->", r.status_code, r.text[:120])
    db = SessionLocal()
    print("victim orders left:", db.query(models.ShopOrder).filter_by(user_id=vid).count(),
          "| grants left:", db.query(models.BitsGrant).filter_by(user_id=vid).count(),
          "| stock of item (3 initially, 1 order was open):", db.get(models.ShopItem, item_id).stock,
          "| questions:", db.query(models.ForumQuestion).count(), "| bookings:", [(b.booked_by_id) for b in db.query(models.Booking)])
    db.close()
    r = A.delete(f"/api/v1/admin/users/{lid}", headers=H)
    print("delete leader ->", r.status_code)
    db = SessionLocal(); m = db.get(models.User, mid)
    tk = db.query(models.Task).first()
    print("task.created_by_id after leader deleted:", tk.created_by_id, "| member on_time after:", progress.facts(db, m)["on_time"], "(1 before)")
    db.close()
