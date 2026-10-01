"""S3 PoC: parallel shop purchases / cancellations and parallel tournament start+finish against 2 uvicorn workers.

Run (PostgreSQL):  S3_DATABASE_URL=postgresql://postgres@127.0.0.1:54329/ivitsh python docs/audit/poc/s3/poc_shop_tribes_race.py
Checks (real code): stock 1 -> 1 order; per-user limit 1 -> 1 order; balance 100, price 60 -> 1 order;
user cancel || admin cancel -> stock returned once; double finish -> prizes paid once; double start -> one winner.
"""
import concurrent.futures as cf
import datetime as dt

import common
from common import H, BASE, cookie, mk_user, start_server, stop_server
import httpx


def par(n, fn):
    with cf.ThreadPoolExecutor(n) as ex:
        return list(ex.map(fn, range(n)))


def run(app_target, label):
    common.fresh_db()
    import app.models as models
    from app.db.database import SessionLocal
    db = SessionLocal()
    admin = mk_user(db, "admin", role="admin")
    buyers = [mk_user(db, f"buyer{i}") for i in range(30)]
    for b in buyers:
        db.add(models.BitsGrant(user_id=b.id, amount=100, reason="s3 poc seed", created_by_id=admin.id))
    items = [models.ShopItem(title="stock1", price=10, stock=1, per_user_limit=None),
             models.ShopItem(title="limit1", price=10, stock=None, per_user_limit=1),
             models.ShopItem(title="pricey", price=60, stock=None, per_user_limit=None),
             models.ShopItem(title="stock3", price=10, stock=3, per_user_limit=None)]
    db.add_all(items)
    db.commit()
    ids = [i.id for i in items]
    ck = [cookie(b) for b in buyers]
    cka = cookie(admin)
    bids = [b.id for b in buyers]
    db.close()
    srv = start_server(workers=2, app_target=app_target)
    out = {}
    try:
        buy = lambda item, k: httpx.post(f"{BASE}/api/v1/shop/items/{item}/buy", headers=H, cookies=ck[k], timeout=60).status_code
        r = par(30, lambda i: buy(ids[0], i))
        out["stock1_orders"] = r.count(200)
        r = par(40, lambda i: buy(ids[1], 5))
        out["limit1_orders_by_one_user"] = r.count(200)
        r = par(40, lambda i: buy(ids[2], 6))
        out["balance100_price60_orders"] = r.count(200)
        r = par(30, lambda i: buy(ids[3], i))
        out["stock3_orders"] = r.count(200)
        # cancel race: the buyer and the admin cancel the same new order at once
        o = httpx.post(f"{BASE}/api/v1/shop/items/{ids[3]}/buy", headers=H, cookies=ck[29]).json()
        if "order" not in o:  # stock 3 was sold out: reopen stock via DB for the cancel test
            db = SessionLocal(); db.query(models.ShopItem).filter_by(id=ids[3]).update({"stock": 1}); db.commit(); db.close()
            o = httpx.post(f"{BASE}/api/v1/shop/items/{ids[3]}/buy", headers=H, cookies=ck[29]).json()
        oid = o["order"]["id"]
        db = SessionLocal(); before = db.query(models.ShopItem).get(ids[3]).stock; db.close()

        def cancel(i):
            if i % 2:
                return httpx.post(f"{BASE}/api/v1/shop/orders/{oid}/cancel", headers=H, cookies=ck[29], timeout=60).status_code
            return httpx.patch(f"{BASE}/api/v1/shop/orders/{oid}", json={"status": "cancelled"}, headers=H, cookies=cka, timeout=60).status_code
        par(20, cancel)
        db = SessionLocal(); after = db.query(models.ShopItem).get(ids[3]).stock; db.close()
        out["stock_before_cancel_after_cancel"] = (before, after)
        # tournaments
        t = httpx.post(f"{BASE}/api/v1/tribes/tournaments", headers=H, cookies=cka, json={
            "title": "S3", "starts_on": (dt.date.today() - dt.timedelta(days=1)).isoformat(),
            "ends_on": (dt.date.today() + dt.timedelta(days=5)).isoformat(), "tribe_names": ["A", "B"]}).json()
        r = par(20, lambda i: httpx.post(f"{BASE}/api/v1/tribes/tournaments/{t['id']}/start", headers=H, cookies=cka, timeout=60).status_code)
        out["start_200s"] = r.count(200)
        r = par(20, lambda i: httpx.post(f"{BASE}/api/v1/tribes/tournaments/{t['id']}/finish", headers=H, cookies=cka, timeout=60).status_code)
        out["finish_200s"] = r.count(200)
        db = SessionLocal()
        out["prize_grants"] = db.query(models.BitsGrant).filter(models.BitsGrant.tournament_id == t["id"]).count()
        out["members"] = db.query(models.TribeMember).filter_by(tournament_id=t["id"]).count()
        # everything has 0 points here: all tribes share 1st place -> everybody is paid the 1st prize
        out["prize_grants_expected_if_paid_once_to_winner_only"] = out["members"] // 2
        db.close()
    finally:
        stop_server(srv)
    print(label, out)
    return out


if __name__ == "__main__":
    run("s3_app_nolock:app", "[NO advisory lock, 2 workers]")
    run("main:app", "[REAL code, 2 workers]")
