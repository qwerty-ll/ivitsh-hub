"""S3 PoC: bits are recomputed from live data, so removing the source after a purchase leaves the goods and a negative balance.

Run: python docs/audit/poc/s3/poc_negative_balance.py
B earns 80 bits (answers that A marked as solutions), buys an 80-bit item; A then deletes the questions:
B keeps the order, balance becomes -80 (no clawback, no flag, nothing for the admin to see except the order).
"""
import common
from common import H, cookie, mk_user

common.fresh_db()
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import app.models as models  # noqa: E402
from app.core import rate_limit  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402

db = SessionLocal()
a, b = mk_user(db, "asker"), mk_user(db, "solver")
item = models.ShopItem(title="Худи", price=80, stock=5)
db.add(item)
db.commit()
ca, cb = cookie(a), cookie(b)
iid = item.id
db.close()
with TestClient(main.app):
    A, B = TestClient(main.app, cookies=ca), TestClient(main.app, cookies=cb)
    qs = [A.post("/api/v1/forum/questions", headers=H, json={"title": f"Вопрос {i}", "content": f"Текст вопроса номер {i}"}).json()["id"] for i in range(15)]
    for q in qs:
        ans = B.post(f"/api/v1/forum/questions/{q}/answers", headers=H, json={"content": "."}).json()
        A.post(f"/api/v1/forum/answers/{ans['id']}/solution", headers=H)
    print("balance before buying:", B.get("/api/v1/shop").json()["balance"])
    print("buy 80-bit item ->", B.post(f"/api/v1/shop/items/{iid}/buy", headers=H).status_code)
    for q in qs:
        A.delete(f"/api/v1/forum/questions/{q}", headers=H)
    shop = B.get("/api/v1/shop").json()
    print("after the questions were deleted: balance", shop["balance"], "| orders kept:", [(o["item_title"], o["status_text"]) for o in shop["orders"]])
