import secrets
from datetime import datetime, timezone
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import false
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
import app.models as models
import app.schemas as schemas
import app.core.security as security
from app.core import locks
from app.routers import shop
from app.routers.associations import task_files
from app.services import audit, uploads

router = APIRouter(prefix="/api/v1", tags=["Admin"])


_MAIN_ADMIN_ONLY = "Права администратора выдаёт и снимает только Главный Администратор ИВИТШ"
DELETED_NAME = "Удалённый пользователь"
_ROLE_TEXT = {"student": "Студент", "moderator": "Модератор", "admin": "Администратор"}


def _get_manageable_user(db: Session, user_id: int, current_user: models.User) -> models.User:
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Это действие недоступно для собственной учётной записи")
    if security.is_protected_admin(target_user):
        raise HTTPException(status_code=400, detail="Это действие недоступно для Главного Администратора ИВИТШ")
    # Other administrators are managed by the main one only (the .env account)
    if target_user.role == "admin" and not security.is_protected_admin(current_user):
        raise HTTPException(status_code=403, detail=_MAIN_ADMIN_ONLY)
    return target_user


def _not_deleted(user: models.User) -> None:
    if user.auth_source == "deleted":
        raise HTTPException(status_code=400, detail="Учётная запись уже удалена")


@router.get("/admin/users", response_model=List[schemas.UserResponse])
def get_all_users(
    response: Response,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=1_000_000),
    q: str = Query("", max_length=100),
    role: Literal["", "student", "moderator", "admin"] = "",
    state: Literal["active", "blocked", "deleted", "all"] = "all",
    sort: Literal["new", "name", "group", "seen"] = "new",
    current_user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db)
):
    """Every account, page by page; X-Total-Count carries how many match. Anonymized ones only on request."""
    User = models.User
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if state == "deleted":
        query = query.filter(User.auth_source == "deleted")
    else:
        query = query.filter(User.auth_source != "deleted")
        if state == "active":
            query = query.filter(User.is_blocked.is_(False))
        elif state == "blocked":
            query = query.filter(User.is_blocked.is_(True))
    needle = q.strip().casefold()
    if needle:
        # Matched in Python (SQLite does not fold Cyrillic case), over three short columns only
        ids = [
            uid for uid, name, login, group in query.with_entities(User.id, User.full_name, User.username, User.group_number)
            if needle in f"{name} {login} {group or ''}".casefold()
        ]
        query = db.query(User).filter(User.id.in_(ids)) if ids else query.filter(false())
    order = {
        "new": (User.created_at.desc(), User.id.desc()),
        "name": (User.full_name.asc(), User.id.asc()),
        "group": (User.group_number.is_(None), User.group_number.asc(), User.full_name.asc()),
        "seen": (User.last_seen_at.is_(None), User.last_seen_at.desc(), User.id.desc()),
    }[sort]
    response.headers["X-Total-Count"] = str(query.count())
    return query.order_by(*order).limit(limit).offset(offset).all()


@router.patch("/admin/users/{user_id}/role", response_model=schemas.UserResponse)
def update_user_role(
    user_id: int,
    req: schemas.RoleUpdateSchema,
    current_user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db)
):
    target_user = _get_manageable_user(db, user_id, current_user)
    _not_deleted(target_user)
    if req.role == "admin" and not security.is_protected_admin(current_user):
        raise HTTPException(status_code=403, detail=_MAIN_ADMIN_ONLY)
    if target_user.role != req.role:
        audit.log(db, current_user, "role", target_user,
                  f"{_ROLE_TEXT.get(target_user.role, target_user.role)} → {_ROLE_TEXT[req.role]}")
        target_user.role = req.role
    db.commit()
    db.refresh(target_user)
    return target_user


def _anonymize(db: Session, target: models.User, actor: models.User) -> List[str]:
    """Strip everything personal but keep the account row, so orders, bookings, attendance and forum
    threads stay. Returns stored files to remove from disk after the commit."""
    uid = target.id
    personal = (models.Task.association_id.is_(None)) & (models.Task.created_by_id == uid)
    files = task_files(db, personal) + [
        name for (name,) in db.query(models.Attachment.stored_name)
        .join(models.ManualAchievement, models.Attachment.achievement_id == models.ManualAchievement.id)
        .filter(models.ManualAchievement.user_id == uid, models.Attachment.stored_name.isnot(None))
    ]
    now = datetime.now(timezone.utc)
    db.query(models.Task).filter(personal).delete(synchronize_session=False)
    # Scans of orders with the student's name are personal data
    for achievement in db.query(models.ManualAchievement).filter(models.ManualAchievement.user_id == uid):
        db.delete(achievement)
    db.query(models.SdoCourse).filter(models.SdoCourse.user_id == uid).delete(synchronize_session=False)
    # Out of every association; unfinished task cards and upcoming registrations go, handed-in work stays
    db.query(models.Membership).filter(models.Membership.user_id == uid).delete(synchronize_session=False)
    db.query(models.TaskAssignee).filter(
        models.TaskAssignee.user_id == uid, models.TaskAssignee.status.in_(("todo", "in_progress")),
    ).delete(synchronize_session=False)
    upcoming = [eid for (eid,) in db.query(models.Event.id).filter(models.Event.starts_at > now)]
    if upcoming:
        db.query(models.EventRegistration).filter(
            models.EventRegistration.user_id == uid, models.EventRegistration.event_id.in_(upcoming),
        ).delete(synchronize_session=False)
    # Orders nobody will collect: the stock goes back (bits no longer matter)
    with locks.serialized(db, shop.LOCK_KEY):
        for order in (db.query(models.ShopOrder).options(joinedload(models.ShopOrder.item))
                      .filter(models.ShopOrder.user_id == uid, models.ShopOrder.status.in_(("new", "ready")))):
            shop._cancel(db, order, actor, "Пользователь удалён")
        label = f"{DELETED_NAME} #{uid}"
        # The journal keeps the fact, not the name
        db.query(models.AdminAction).filter(models.AdminAction.target_user_id == uid).update(
            {models.AdminAction.target_name: label}, synchronize_session=False)
        target.username = f"deleted-{uid}-{secrets.token_hex(4)}"
        target.full_name = DELETED_NAME
        target.email = target.group_number = target.eios_group_id = target.sdo_id = None
        if target.photo_name:
            files.append(target.photo_name)
        target.avatar_url = target.vk_url = target.max_contact = target.photo_name = None
        target.pd_consent_at = target.pd_consent_version = target.sdo_synced_at = None
        target.hashed_password = security.get_password_hash(secrets.token_urlsafe(32))
        target.role, target.auth_source, target.is_blocked = "student", "deleted", True
        db.add(models.AdminAction(actor_id=actor.id, actor_name=audit.user_label(actor), action="anonymize",
                                  target_user_id=uid, target_name=label))
        db.commit()
    return files


@router.delete("/admin/users/{user_id}", status_code=200)
def delete_user(
    user_id: int,
    purge: bool = False,
    current_user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db)
):
    """Deleting anonymizes the account: the history (orders, bookings, forum, attendance) stays without a name.
    purge=true erases an already anonymized account with everything tied to it."""
    target_user = _get_manageable_user(db, user_id, current_user)
    if not purge:
        _not_deleted(target_user)
        uploads.delete(_anonymize(db, target_user, current_user))
        return {"status": "anonymized", "id": user_id}
    if target_user.auth_source != "deleted":
        raise HTTPException(status_code=400, detail="Стереть полностью можно только уже удалённую учётную запись")
    audit.log(db, current_user, "purge", None, f"{DELETED_NAME} #{user_id}")
    db.delete(target_user)
    db.commit()
    return {"status": "deleted", "id": user_id}


@router.patch("/admin/users/{user_id}/block", response_model=schemas.UserResponse)
def set_user_blocked(
    user_id: int,
    req: schemas.BlockUpdateSchema,
    current_user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db)
):
    """Blocking (unlike deleting) survives the next EIOS login and invalidates existing sessions at once."""
    target_user = _get_manageable_user(db, user_id, current_user)
    _not_deleted(target_user)
    if target_user.is_blocked != req.blocked:
        audit.log(db, current_user, "block" if req.blocked else "unblock", target_user)
        target_user.is_blocked = req.blocked
    db.commit()
    db.refresh(target_user)
    return target_user


@router.get("/admin/actions", response_model=List[schemas.AdminActionResponse])
def admin_actions(
    response: Response,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
    _: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(models.AdminAction)
    response.headers["X-Total-Count"] = str(query.count())
    rows = query.order_by(models.AdminAction.created_at.desc(), models.AdminAction.id.desc()).limit(limit).offset(offset)
    return [
        schemas.AdminActionResponse(
            id=a.id, actor_name=a.actor_name, action=a.action, action_text=audit.ACTION_TEXT.get(a.action, a.action),
            target_name=a.target_name, details=a.details, created_at=a.created_at,
        )
        for a in rows
    ]


# --- Teachers ---
@router.get("/teachers", response_model=List[schemas.TeacherResponse])
def get_teachers(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    return db.query(models.Teacher).limit(limit).offset(offset).all()


@router.post("/admin/teachers", response_model=schemas.TeacherResponse)
def create_teacher(
    t_in: schemas.TeacherCreate,
    current_user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db)
):
    new_t = models.Teacher(**t_in.model_dump())
    db.add(new_t)
    db.commit()
    db.refresh(new_t)
    return new_t


@router.delete("/admin/teachers/{teacher_id}", status_code=200)
def delete_teacher(
    teacher_id: int,
    current_user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db)
):
    t = db.query(models.Teacher).filter(models.Teacher.id == teacher_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Преподаватель не найден")
    db.delete(t)
    db.commit()
    return {"status": "deleted"}


# --- Announcements ---
@router.get("/announcements", response_model=List[schemas.AnnouncementResponse])
def get_announcements(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    return (
        db.query(models.Announcement)
        .order_by(models.Announcement.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )


@router.post("/admin/announcements", response_model=schemas.AnnouncementResponse)
def create_announcement(
    a_in: schemas.AnnouncementCreate,
    current_user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db)
):
    new_a = models.Announcement(**a_in.model_dump())
    db.add(new_a)
    db.commit()
    db.refresh(new_a)
    return new_a


@router.delete("/admin/announcements/{announcement_id}", status_code=200)
def delete_announcement(
    announcement_id: int,
    current_user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db)
):
    a = db.query(models.Announcement).filter(models.Announcement.id == announcement_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Объявление не найдено")
    db.delete(a)
    db.commit()
    return {"status": "deleted"}


@router.put("/admin/announcements/{announcement_id}", response_model=schemas.AnnouncementResponse)
def update_announcement(
    announcement_id: int,
    a_in: schemas.AnnouncementCreate,
    current_user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db)
):
    """FIX (A-06): Atomic update endpoint — prevents the delete+create split-brain pattern."""
    a = db.query(models.Announcement).filter(models.Announcement.id == announcement_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Объявление не найдено")
    for key, value in a_in.model_dump().items():
        setattr(a, key, value)
    db.commit()
    db.refresh(a)
    return a


# --- FAQ ---
@router.get("/faq", response_model=List[schemas.FaqItemResponse])
def get_faq_items(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    return (
        db.query(models.FaqItem)
        .order_by(models.FaqItem.order_index.asc())
        .limit(limit)
        .offset(offset)
        .all()
    )


@router.post("/admin/faq", response_model=schemas.FaqItemResponse)
def create_faq_item(
    f_in: schemas.FaqItemCreate,
    current_user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db)
):
    new_f = models.FaqItem(**f_in.model_dump())
    db.add(new_f)
    db.commit()
    db.refresh(new_f)
    return new_f


@router.delete("/admin/faq/{faq_id}", status_code=200)
def delete_faq_item(
    faq_id: int,
    current_user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db)
):
    f = db.query(models.FaqItem).filter(models.FaqItem.id == faq_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="FAQ элемент не найден")
    db.delete(f)
    db.commit()
    return {"status": "deleted"}


@router.put("/admin/faq/{faq_id}", response_model=schemas.FaqItemResponse)
def update_faq_item(
    faq_id: int,
    f_in: schemas.FaqItemCreate,
    current_user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db)
):
    """FIX (A-07): Atomic update endpoint — prevents data loss from delete+create partial failure."""
    f = db.query(models.FaqItem).filter(models.FaqItem.id == faq_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="FAQ элемент не найден")
    for key, value in f_in.model_dump().items():
        setattr(f, key, value)
    db.commit()
    db.refresh(f)
    return f


# --- Subjects ---
@router.get("/subjects", response_model=List[schemas.SubjectResponse])
def get_subjects(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    return (
        db.query(models.Subject)
        .order_by(models.Subject.semester.asc(), models.Subject.id.asc())
        .limit(limit)
        .offset(offset)
        .all()
    )


@router.post("/admin/subjects", response_model=schemas.SubjectResponse, status_code=201)
def create_subject(
    s_in: schemas.SubjectCreate,
    current_user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db)
):
    # FIX: Return 409 Conflict instead of silently upsert-ing an existing subject.
    existing = db.query(models.Subject).filter(models.Subject.subject_code == s_in.subject_code).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Предмет с кодом '{s_in.subject_code}' уже существует. Используйте PUT для обновления."
        )
    new_s = models.Subject(**s_in.model_dump())
    db.add(new_s)
    db.commit()
    db.refresh(new_s)
    return new_s


@router.put("/admin/subjects/{subject_id}", response_model=schemas.SubjectResponse)
def update_subject(
    subject_id: int,
    s_in: schemas.SubjectCreate,
    current_user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db)
):
    s = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Предмет не найден")
    for key, value in s_in.model_dump().items():
        setattr(s, key, value)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/admin/subjects/{subject_id}", status_code=200)
def delete_subject(
    subject_id: int,
    current_user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db)
):
    s = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Предмет не найден")
    db.delete(s)
    db.commit()
    return {"status": "deleted"}
