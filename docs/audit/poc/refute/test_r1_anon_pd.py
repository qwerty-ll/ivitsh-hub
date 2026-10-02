"""R1: what exactly does an anonymous visitor get from forum / catalog / other open endpoints."""
import json
from conftest import login_student, login_admin, CSRF, TestClient


def test_anon_json(app, fake_eios, db):
    s = login_student(app, fake_eios, "24-isbo-001", full_name="Смирнова Анна Олеговна", group="24-ИСбо-1")
    r = s.post("/api/v1/forum/questions", json={"title": "Как получить справку", "category": "Учёба", "content": "Подскажите пожалуйста как"}, headers=CSRF)
    assert r.status_code == 200, r.text
    qid = r.json()["id"]
    s2 = login_student(app, fake_eios, "24-isbo-002", eios_id="101", full_name="Петров Пётр Петрович", group="24-ИСбо-2")
    s2.post(f"/api/v1/forum/questions/{qid}/answers", json={"content": "Идите в деканат"}, headers=CSRF)
    anon = TestClient(app)
    for path in ["/api/v1/forum/questions", f"/api/v1/forum/questions/{qid}", f"/api/v1/forum/questions/{qid}/answers", "/api/v1/forum/questions?author_id=1",
                 "/api/v1/associations"]:
        r = anon.get(path)
        print(path, r.status_code, json.dumps(r.json(), ensure_ascii=False)[:400])
    # other open endpoints that might list people
    for path in ["/api/v1/teachers", "/api/v1/tribes", "/api/v1/tribes/standings", "/api/v1/events", "/api/v1/auth/me", "/api/v1/progress", "/api/v1/users", "/api/v1/admin/users"]:
        r = anon.get(path)
        print("OTHER", path, r.status_code, r.text[:120])
    # enumeration by author_id sequentially
    seen = {}
    for uid in range(1, 5):
        for q in anon.get(f"/api/v1/forum/questions?author_id={uid}").json():
            seen[q["author_id"]] = q["author_name"]
    print("ENUM", seen)
