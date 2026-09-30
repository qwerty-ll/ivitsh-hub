import main
import app.models as models
from conftest import CSRF, login_admin, login_student


def _user_id(db, username):
    return db.query(models.User).filter_by(username=username).one().id


def test_delete_user(app, fake_eios, db):
    login_student(app, fake_eios)
    admin = login_admin(app)
    r = admin.delete(f"/api/v1/admin/users/{_user_id(db, '24-isbo-001')}", headers=CSRF)
    assert r.status_code == 200
    assert db.query(models.User).filter_by(username="24-isbo-001").count() == 0


def test_block_user_ends_session_and_prevents_login(app, fake_eios, db):
    student = login_student(app, fake_eios)
    admin = login_admin(app)
    r = admin.patch(f"/api/v1/admin/users/{_user_id(db, '24-isbo-001')}/block", json={"blocked": True}, headers=CSRF)
    assert r.status_code == 200 and r.json()["is_blocked"] is True
    assert student.get("/api/v1/auth/me").status_code == 401
    r = student.post("/api/v1/auth/eios-login", json={"consent": True, "username": "24-isbo-001", "password": "pw"})
    assert r.status_code == 403


def test_main_admin_is_protected(app, fake_eios, db):
    admin = login_admin(app)
    admin_id = _user_id(db, "portal_admin")
    student = login_student(app, fake_eios)
    student_id = _user_id(db, "24-isbo-001")
    assert admin.patch(f"/api/v1/admin/users/{student_id}/role", json={"role": "admin"}, headers=CSRF).status_code == 200
    # A second admin cannot remove the env-configured main administrator.
    assert student.delete(f"/api/v1/admin/users/{admin_id}", headers=CSRF).status_code == 400
    assert student.patch(f"/api/v1/admin/users/{admin_id}/role", json={"role": "student"}, headers=CSRF).status_code == 400
    assert admin.patch(f"/api/v1/admin/users/{student_id}/role", json={"role": "superuser"}, headers=CSRF).status_code == 422


def test_freshman_guide_api_is_gone(app, fake_eios):
    student = login_student(app, fake_eios)
    assert student.get("/api/v1/adaptation/me").status_code == 404
    admin = login_admin(app)
    assert admin.get("/api/v1/admin/adaptations").status_code == 404


def test_seed_keeps_teachers_added_by_admin(app, db):
    admin = login_admin(app)
    r = admin.post("/api/v1/admin/teachers", json={"name": "Новый Преподаватель", "department": "ИСиТ", "role": "Доцент"}, headers=CSRF)
    assert r.status_code == 200
    before = db.query(models.Teacher).count()
    main.seed_database()
    assert db.query(models.Teacher).count() == before
    admin.delete(f"/api/v1/admin/teachers/{r.json()['id']}", headers=CSRF)
