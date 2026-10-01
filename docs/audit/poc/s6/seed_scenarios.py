"""Seeds the S6 sandbox (local_server.py on :8766) with a small realistic state for the browser scenarios.
Users: st01 leader of «ВИТШ медиа»; st02, st03 members; st04 applicant; st05 plain student. Admin: portal_admin."""
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


a = login("portal_admin", "Adm1n-Local-Pass!", admin=True)
u = {n: login(n) for n in ("st01", "st02", "st03", "st04", "st05")}
assocs = {x["name"]: x["id"] for x in a.get("/api/v1/admin/associations").json()}
aid = assocs["ВИТШ медиа"]
a.put(f"/api/v1/admin/associations/{aid}/leaders/{u['st01'].me['id']}")
for n in ("st02", "st03", "st04"):
    u[n].post(f"/api/v1/associations/{aid}/apply", json={"message": "Хочу снимать видео"})
for n in ("st02", "st03"):
    u["st01"].post(f"/api/v1/associations/{aid}/members/{u[n].me['id']}/decision", json={"approve": True})
lead = u["st01"]
t1 = lead.post("/api/v1/tasks", json={"title": "Смонтировать ролик к Дню института", "description": "Хронометраж до 2 минут", "association_id": aid,
                                      "to_all": True, "due_at": iso(now + timedelta(days=1))}).json()
lead.post("/api/v1/tasks", json={"title": "Подготовить пресс-релиз", "association_id": aid, "assignee_ids": [u["st02"].me["id"]],
                                 "due_at": iso(now - timedelta(days=1))})
u["st02"].patch(f"/api/v1/tasks/{t1['id']}/status", json={"status": "in_progress"})
u["st02"].post("/api/v1/tasks", json={"title": "Купить кабель HDMI", "color": "green", "due_at": iso(now + timedelta(days=3))})
u["st02"].post(f"/api/v1/tasks/{t1['id']}/comments", json={"text": "Начал, пришлю черновик завтра"})
start = now + timedelta(days=2)
ev = a.post("/api/v1/events", json={"title": "День института", "scope": "institute", "starts_at": iso(start), "ends_at": iso(start + timedelta(hours=3)),
                                    "place": "Б-407", "participant_limit": 50, "volunteer_limit": 5, "description": "Ежегодный праздник."}).json()
u["st02"].post(f"/api/v1/events/{ev['id']}/register", json={"role": "participant"})
lead.post("/api/v1/events", json={"title": "Мастер-класс по видеомонтажу", "association_id": aid, "starts_at": iso(now + timedelta(days=5)),
                                  "ends_at": iso(now + timedelta(days=5, hours=2)), "place": "Б-108"})
lead.post(f"/api/v1/associations/{aid}/meetings", json={"title": "Планёрка", "starts_at": iso(now + timedelta(days=1, hours=2)),
                                                        "ends_at": iso(now + timedelta(days=1, hours=3)), "place": "Б-108", "agenda": "Планы на месяц"})
day = (now + timedelta(days=1)).astimezone(timezone(timedelta(hours=3))).date()
lead.post("/api/v1/bookings", json={"resource": "room", "zone": "top", "association_id": aid, "purpose": "Съёмка",
                                    "starts_at": f"{day}T12:00:00+03:00", "ends_at": f"{day}T14:00:00+03:00"})
a.post("/api/v1/shop/items", json={"title": "Футболка ИВИТШ", "price": 40, "stock": 3, "per_user_limit": 1, "description": "Размеры S-XL"})
a.post("/api/v1/shop/items", json={"title": "Приоритет брони", "kind": "privilege", "price": 120})
a.post("/api/v1/bits/grants", json={"user_id": u["st02"].me["id"], "amount": 100, "reason": "Приз олимпиады"})
q = u["st03"].post("/api/v1/forum/questions", json={"title": "Где пересдать физкультуру?", "content": "Подскажите, куда идти за допуском", "category": "Учеба"}).json()
u["st02"].post(f"/api/v1/forum/questions/{q['id']}/answers", json={"content": "В спорткомплексе, каб. 12"})
u["st02"].post("/api/v1/homework", json={"subject": "Базы данных", "text": "Лаба №3, до пятницы", "due_at": iso(now + timedelta(days=4))})
tour = a.post("/api/v1/tribes/tournaments", json={"title": "Осенний турнир", "starts_on": str((now - timedelta(days=1)).date()),
                                                  "ends_on": str((now + timedelta(days=30)).date()), "tribe_names": ["Альфа", "Бета"]}).json()
a.post(f"/api/v1/tribes/tournaments/{tour['id']}/start")
print("seeded: assoc", aid, "task", t1["id"], "event", ev["id"])
