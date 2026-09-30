"""Events: of an association (its leaders create them, its members see them) or of the institute
(only administrators create them, every student sees them).

Students register themselves as participants or volunteers. Organizers add people one by one
(a leader only from their association's members); a whole academic group is enrolled only by an
administrator. After the event organizers mark attendance and attach orders and thank-you letters,
and participants rate it.
"""
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.database import get_db
import app.models as models
import app.schemas as schemas
import app.core.security as security
from app.routers.associations import _get_association, is_leader
from app.routers.homework import group_key
from app.routers.meetings import is_member
from app.routers.tasks import attachment_item
from app.services import pgas, timetable, uploads

router = APIRouter(prefix="/api/v1", tags=["Events"])

# Participants may rate an event for this long after it ended
FEEDBACK_WINDOW = timedelta(days=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_admin(user: Optional[models.User]) -> bool:
    return bool(user) and user.role == "admin"


def can_manage(db: Session, event: models.Event, user: Optional[models.User]) -> bool:
    if _is_admin(user):
        return True
    return bool(user) and event.association_id is not None and is_leader(db, user, event.association_id)


def can_see(db: Session, event: models.Event, user: Optional[models.User]) -> bool:
    if event.association and not event.association.is_active and not _is_admin(user):
        return False
    if event.scope == "institute":
        return True
    # Whoever is on the list sees it too (the administration may add people from outside the association)
    return bool(user) and (can_manage(db, event, user) or is_member(db, user, event.association_id)
                           or any(r.user_id == user.id for r in event.registrations))


def _load(db: Session, event_id: int) -> Optional[models.Event]:
    return (
        db.query(models.Event)
        .options(
            joinedload(models.Event.association),
            joinedload(models.Event.created_by),
            selectinload(models.Event.registrations).joinedload(models.EventRegistration.user),
            selectinload(models.Event.feedback),
            selectinload(models.Event.removals).joinedload(models.EventRemoval.user),
            selectinload(models.Event.attachments).joinedload(models.Attachment.uploaded_by),
        )
        .filter(models.Event.id == event_id)
        .first()
    )


def get_visible(db: Session, event_id: int, user: Optional[models.User]) -> models.Event:
    event = _load(db, event_id)
    if not event or not can_see(db, event, user):
        raise HTTPException(status_code=404, detail="Мероприятие не найдено")
    return event


def get_managed(db: Session, event_id: int, user: models.User) -> models.Event:
    event = get_visible(db, event_id, user)
    if not can_manage(db, event, user):
        raise HTTPException(status_code=403, detail="Управлять мероприятием могут его организаторы")
    return event


def _mine(event: models.Event, user: Optional[models.User]) -> Optional[models.EventRegistration]:
    return next((r for r in event.registrations if user and r.user_id == user.id), None)


def _counts(event: models.Event) -> Dict[str, int]:
    return {
        "participants": sum(r.role == "participant" for r in event.registrations),
        "volunteers": sum(r.role == "volunteer" for r in event.registrations),
    }


def card(db: Session, event: models.Event, user: Optional[models.User]) -> Dict:
    mine = _mine(event, user)
    return {
        "id": event.id,
        "title": event.title,
        "scope": event.scope,
        "association": {"id": event.association.id, "name": event.association.name} if event.association else None,
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
        "place": event.place or "",
        "participant_limit": event.participant_limit,
        "volunteer_limit": event.volunteer_limit,
        "registration_open": event.registration_open,
        "my_role": mine.role if mine else None,
        "can_manage": can_manage(db, event, user),
        **_counts(event),
    }


def _ended(event: models.Event) -> bool:
    return schemas.as_utc(event.ends_at) <= _now()


def _can_feedback(event: models.Event, mine: Optional[models.EventRegistration]) -> bool:
    return bool(mine) and mine.attended is not False and _ended(event) \
        and _now() - schemas.as_utc(event.ends_at) <= FEEDBACK_WINDOW


def detail(db: Session, event: models.Event, user: Optional[models.User]) -> Dict:
    item = card(db, event, user)
    manage = item["can_manage"]
    mine = _mine(event, user)
    my_feedback = next((f for f in event.feedback if user and f.user_id == user.id), None)
    item.update({
        "description": event.description or "",
        "created_by": event.created_by.full_name if event.created_by else None,
        "my_attended": mine.attended if mine else None,
        "my_feedback": {"rating": my_feedback.rating, "text": my_feedback.text} if my_feedback else None,
        "can_feedback": _can_feedback(event, mine),
        # Orders and thanks carry names: registered people and organizers only
        "attachments": [attachment_item(a, manage) for a in event.attachments] if (manage or mine) else [],
        "registrations": [],
        "removed": [],
        "feedback": None,
        "started": _started(event),
        # Whether the student may change their own registration: before the start, if they signed up themselves
        "my_source": mine.source if mine else None,
        "i_was_removed": bool(user) and not mine and _removed(event, user.id),
    })
    if manage:
        regs = sorted(event.registrations, key=lambda r: (r.role != "participant", r.user.full_name))
        item["registrations"] = [
            {
                "user_id": r.user_id, "full_name": r.user.full_name, "group_number": r.user.group_number,
                "role": r.role, "source": r.source, "attended": r.attended,
                "vk_url": r.user.vk_url, "max_contact": r.user.max_contact,
            }
            for r in regs
        ]
        item["removed"] = [
            {"id": r.user_id, "full_name": r.user.full_name, "group_number": r.user.group_number}
            for r in sorted(event.removals, key=lambda r: r.user.full_name)
        ]
        ratings = [f.rating for f in event.feedback]
        item["feedback"] = {
            "count": len(ratings),
            "average": round(sum(ratings) / len(ratings), 1) if ratings else None,
            "comments": [{"rating": f.rating, "text": f.text} for f in event.feedback if f.text],
        }
    return item


def _visible_query(db: Session, user: Optional[models.User]):
    """Events the user may see: every institute event, association events of their associations
    and any event they are on the list of."""
    query = db.query(models.Event).options(
        joinedload(models.Event.association),
        selectinload(models.Event.registrations),
    )
    if _is_admin(user):
        return query
    mine = []
    if user:
        mine = [
            aid for (aid,) in db.query(models.Membership.association_id).filter(
                models.Membership.user_id == user.id, models.Membership.status == "approved")
        ]
    scope = models.Event.scope == "institute"
    if mine:
        scope = scope | models.Event.association_id.in_(mine)
    if user:
        registered = db.query(models.EventRegistration.event_id).filter(models.EventRegistration.user_id == user.id)
        scope = scope | models.Event.id.in_(registered)
    return query.filter(scope)


def visible_events(db: Session, user: Optional[models.User]) -> List[models.Event]:
    return [e for e in _visible_query(db, user).all() if not (e.association and not e.association.is_active and not _is_admin(user))]


# --- Lists ---------------------------------------------------------------------------------------

@router.get("/events", response_model=List[schemas.EventCard])
def list_events(
    view: str = Query("upcoming", pattern="^(upcoming|past|mine|managed)$"),
    association_id: Optional[int] = Query(None, ge=1),
    user: Optional[models.User] = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    now = _now()
    events = visible_events(db, user)
    if association_id:
        events = [e for e in events if e.association_id == association_id]
    if view == "upcoming":
        events = sorted((e for e in events if schemas.as_utc(e.ends_at) > now), key=lambda e: schemas.as_utc(e.starts_at))
    elif view == "past":
        events = sorted((e for e in events if schemas.as_utc(e.ends_at) <= now), key=lambda e: schemas.as_utc(e.starts_at), reverse=True)[:50]
    elif view == "mine":
        if not user:
            return []
        events = sorted((e for e in events if _mine(e, user)), key=lambda e: schemas.as_utc(e.starts_at), reverse=True)
    else:
        if not user:
            return []
        events = sorted((e for e in events if can_manage(db, e, user)), key=lambda e: schemas.as_utc(e.starts_at), reverse=True)
    return [card(db, e, user) for e in events]


@router.get("/events/feedback/pending", response_model=List[schemas.EventCard])
def feedback_pending(
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    """Events the user took part in and has not rated yet: the survey after the event."""
    rated = {eid for (eid,) in db.query(models.EventFeedback.event_id).filter(models.EventFeedback.user_id == user.id)}
    regs = (
        db.query(models.EventRegistration)
        .options(joinedload(models.EventRegistration.event).joinedload(models.Event.association),
                 joinedload(models.EventRegistration.event).selectinload(models.Event.registrations))
        .filter(models.EventRegistration.user_id == user.id)
        .all()
    )
    events = [r.event for r in regs if r.event_id not in rated and _can_feedback(r.event, r)]
    return [card(db, e, user) for e in sorted(events, key=lambda e: schemas.as_utc(e.ends_at), reverse=True)]


@router.get("/events/export")
def export_all(
    start: date,
    end: date,
    format: str = Query("xlsx", pattern="^(xlsx|docx)$"),
    user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db),
):
    """Administrators: everyone registered for events of the period — who, which group, in what role, whether they came."""
    if end < start or (end - start).days > 400:
        raise HTTPException(status_code=400, detail="Неверный период (не больше года)")
    since = datetime.combine(start, time(0), tzinfo=timetable.MSK)
    until = datetime.combine(end + timedelta(days=1), time(0), tzinfo=timetable.MSK)
    events = (
        db.query(models.Event)
        .options(joinedload(models.Event.association),
                 selectinload(models.Event.registrations).joinedload(models.EventRegistration.user))
        .filter(models.Event.starts_at >= since, models.Event.starts_at < until)
        .order_by(models.Event.starts_at)
        .all()
    )
    rows = []
    for e in events:
        day = schemas.as_utc(e.starts_at).astimezone(timetable.MSK).date()
        for r in sorted(e.registrations, key=lambda r: (r.role != "participant", r.user.full_name)):
            rows.append({
                "day": day, "title": e.title,
                "level": "Институт" if e.scope == "institute" else "Объединение",
                "organizer": e.association.name if e.association else "Администрация ИВИТШ",
                "full_name": r.user.full_name, "group": r.user.group_number,
                "role": r.role, "source": r.source, "attended": r.attended,
            })
    if format == "xlsx":
        content, media = pgas.events_report_xlsx(start, end, rows), pgas.XLSX
    else:
        content, media = pgas.events_report_docx(start, end, rows, timetable.msk_now().date()), pgas.DOCX
    return Response(content, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="events-{start:%Y%m%d}-{end:%Y%m%d}.{format}"',
        "Cache-Control": "private, no-store",
    })


# --- One event -----------------------------------------------------------------------------------

def _check_rights_for(db: Session, data: schemas.EventIn, user: models.User) -> None:
    if data.scope == "institute" and not _is_admin(user):
        raise HTTPException(status_code=403, detail="Мероприятия уровня института создаёт администрация")
    if data.association_id:
        _get_association(db, data.association_id, include_inactive=_is_admin(user))
        if not (_is_admin(user) or is_leader(db, user, data.association_id)):
            raise HTTPException(status_code=403, detail="Создавать мероприятия объединения могут его руководители")


@router.post("/events", response_model=schemas.EventDetail, status_code=201)
def create_event(
    data: schemas.EventIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    _check_rights_for(db, data, user)
    event = models.Event(created_by_id=user.id, **data.model_dump())
    db.add(event)
    db.commit()
    return detail(db, _load(db, event.id), user)


@router.get("/events/{event_id}", response_model=schemas.EventDetail)
def get_event(
    event_id: int,
    user: Optional[models.User] = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    return detail(db, get_visible(db, event_id, user), user)


@router.put("/events/{event_id}", response_model=schemas.EventDetail)
def edit_event(
    event_id: int,
    data: schemas.EventIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    event = get_managed(db, event_id, user)
    if not _is_admin(user) and (data.scope != event.scope or data.association_id != event.association_id):
        raise HTTPException(status_code=403, detail="Уровень и организатора мероприятия меняет администрация")
    if _is_admin(user):
        _check_rights_for(db, data, user)
    counts = _counts(event)
    if data.participant_limit is not None and data.participant_limit < counts["participants"]:
        raise HTTPException(status_code=400, detail=f"Уже записано участников: {counts['participants']} — лимит не может быть меньше")
    if counts["volunteers"] and (data.volunteer_limit is None or data.volunteer_limit < counts["volunteers"]):
        raise HTTPException(status_code=400, detail=f"Уже записано волонтёров: {counts['volunteers']} — сначала уберите их или оставьте лимит не меньше")
    for field, value in data.model_dump().items():
        setattr(event, field, value)
    db.commit()
    return detail(db, _load(db, event_id), user)


@router.delete("/events/{event_id}", status_code=200)
def delete_event(
    event_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    event = get_managed(db, event_id, user)
    files = [a.stored_name for a in event.attachments if a.stored_name]
    db.delete(event)
    db.commit()
    uploads.delete(files)
    return {"ok": True}


# --- Registration --------------------------------------------------------------------------------

def _started(event: models.Event) -> bool:
    return schemas.as_utc(event.starts_at) <= _now()


def _removed(event: models.Event, user_id: int) -> bool:
    return any(r.user_id == user_id for r in event.removals)


def _check_place(event: models.Event, role: str, exclude_user: Optional[int] = None) -> None:
    taken = sum(r.role == role and r.user_id != exclude_user for r in event.registrations)
    if role == "volunteer":
        if event.volunteer_limit is None:
            raise HTTPException(status_code=400, detail="Волонтёры на это мероприятие не нужны")
        if taken >= event.volunteer_limit:
            raise HTTPException(status_code=409, detail="Места для волонтёров закончились")
    elif event.participant_limit is not None and taken >= event.participant_limit:
        raise HTTPException(status_code=409, detail="Места для участников закончились")


@router.post("/events/{event_id}/register", response_model=schemas.EventDetail)
def register(
    event_id: int,
    data: schemas.RegisterIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    event = get_visible(db, event_id, user)
    if _started(event):
        raise HTTPException(status_code=400, detail="Мероприятие уже началось — запись закрыта")
    if _removed(event, user.id):
        raise HTTPException(status_code=403, detail="Организаторы убрали вас из списка. Записаться снова можно только по их приглашению")
    if not event.registration_open:
        raise HTTPException(status_code=400, detail="Запись на мероприятие закрыта")
    mine = _mine(event, user)
    if mine and mine.role == data.role:
        return detail(db, event, user)
    if mine and mine.source != "self":
        raise HTTPException(status_code=403, detail="Вас записали организаторы — роль меняют они")
    _check_place(event, data.role, exclude_user=user.id)
    if mine:
        mine.role = data.role
    else:
        event.registrations.append(models.EventRegistration(user_id=user.id, role=data.role, source="self"))
    db.commit()
    return detail(db, _load(db, event_id), user)


@router.delete("/events/{event_id}/register", response_model=schemas.EventDetail)
def unregister(
    event_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    event = get_visible(db, event_id, user)
    mine = _mine(event, user)
    if mine:
        if _started(event):
            raise HTTPException(status_code=400, detail="Мероприятие уже началось — отменить запись нельзя")
        if mine.source != "self":
            raise HTTPException(status_code=403, detail="Вас записали организаторы — чтобы отказаться, напишите им")
        event.registrations.remove(mine)
        db.commit()
    return detail(db, _load(db, event_id), user)


@router.post("/events/{event_id}/registrations", response_model=schemas.EventDetail)
def add_people(
    event_id: int,
    data: schemas.AddPeopleIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    """Organizers add people by name: a leader only from the association's members."""
    event = get_managed(db, event_id, user)
    wanted = set(data.user_ids)
    if _is_admin(user):
        allowed = {uid for (uid,) in db.query(models.User.id).filter(models.User.id.in_(wanted))}
    else:
        allowed = {
            uid for (uid,) in db.query(models.Membership.user_id).filter(
                models.Membership.association_id == event.association_id,
                models.Membership.status == "approved",
                models.Membership.user_id.in_(wanted),
            )
        }
    if wanted - allowed:
        raise HTTPException(status_code=400, detail="Руководитель записывает только участников своего объединения")
    if data.role == "volunteer" and event.volunteer_limit is None:
        raise HTTPException(status_code=400, detail="Волонтёры на это мероприятие не нужны")
    have = {r.user_id: r for r in event.registrations}
    source = "admin" if _is_admin(user) else "leader"
    # Putting someone back is the organizers' call: it lifts the removal
    event.removals = [r for r in event.removals if r.user_id not in wanted]
    for uid in wanted:
        if uid in have:
            have[uid].role = data.role
        else:
            event.registrations.append(models.EventRegistration(user_id=uid, role=data.role, source=source))
    db.commit()
    return detail(db, _load(db, event_id), user)


@router.post("/events/{event_id}/groups")
def add_groups(
    event_id: int,
    data: schemas.AddGroupsIn,
    user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db),
):
    """Enroll whole academic groups: administrators only (protection from spam)."""
    event = get_managed(db, event_id, user)
    keys = {group_key(g) for g in data.groups} - {""}
    students = [
        u for u in db.query(models.User).filter(models.User.group_number.isnot(None), models.User.is_blocked.is_(False)).all()
        if group_key(u.group_number) in keys
    ]
    have = {r.user_id for r in event.registrations}
    removed = {r.user_id for r in event.removals}
    added = [u for u in students if u.id not in have and u.id not in removed]
    event.registrations.extend(
        models.EventRegistration(user_id=u.id, role=data.role, source="admin_group") for u in added
    )
    db.commit()
    found = {group_key(u.group_number) for u in students}
    return {
        "added": len(added),
        "already": sum(u.id in have for u in students),
        # Taken off this event by hand earlier: add them by name to bring them back
        "removed": sum(u.id in removed and u.id not in have for u in students),
        # Groups nobody from has signed in to the portal yet
        "unknown_groups": [g for g in data.groups if group_key(g) not in found],
    }


@router.delete("/events/{event_id}/registrations/{user_id}", response_model=schemas.EventDetail)
def remove_person(
    event_id: int,
    user_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    event = get_managed(db, event_id, user)
    reg = next((r for r in event.registrations if r.user_id == user_id), None)
    if not reg:
        raise HTTPException(status_code=404, detail="Этого человека нет в списке")
    event.registrations.remove(reg)
    if not _removed(event, user_id):
        event.removals.append(models.EventRemoval(user_id=user_id, removed_by_id=user.id))
    db.commit()
    return detail(db, _load(db, event_id), user)


@router.patch("/events/{event_id}/registrations/{user_id}", response_model=schemas.EventDetail)
def set_role(
    event_id: int,
    user_id: int,
    data: schemas.RegisterIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    """Organizers switch someone between participant and volunteer (at any time)."""
    event = get_managed(db, event_id, user)
    reg = next((r for r in event.registrations if r.user_id == user_id), None)
    if not reg:
        raise HTTPException(status_code=404, detail="Этого человека нет в списке")
    if data.role == "volunteer" and event.volunteer_limit is None:
        raise HTTPException(status_code=400, detail="Волонтёры на это мероприятие не нужны: включите их в настройках мероприятия")
    reg.role = data.role
    db.commit()
    return detail(db, _load(db, event_id), user)


@router.delete("/events/{event_id}/removals/{user_id}", response_model=schemas.EventDetail)
def allow_again(
    event_id: int,
    user_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    """Lets someone taken off the list register themselves again."""
    event = get_managed(db, event_id, user)
    event.removals = [r for r in event.removals if r.user_id != user_id]
    db.commit()
    return detail(db, _load(db, event_id), user)


@router.put("/events/{event_id}/attendance", response_model=schemas.EventDetail)
def set_attendance(
    event_id: int,
    data: schemas.AttendanceIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    event = get_managed(db, event_id, user)
    if schemas.as_utc(event.starts_at) > _now():
        raise HTTPException(status_code=400, detail="Присутствие отмечают, когда мероприятие началось")
    present = set(data.user_ids)
    unknown = present - {r.user_id for r in event.registrations}
    if unknown:
        raise HTTPException(status_code=400, detail="Отметить можно только записанных")
    for r in event.registrations:
        r.attended = r.user_id in present
    db.commit()
    return detail(db, _load(db, event_id), user)


@router.post("/events/{event_id}/feedback", response_model=schemas.EventDetail)
def leave_feedback(
    event_id: int,
    data: schemas.FeedbackIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    event = get_visible(db, event_id, user)
    mine = _mine(event, user)
    if not _can_feedback(event, mine):
        raise HTTPException(status_code=400, detail="Оценить можно мероприятие, в котором вы участвовали, после его окончания")
    existing = next((f for f in event.feedback if f.user_id == user.id), None)
    if existing:
        existing.rating, existing.text = data.rating, data.text
    else:
        event.feedback.append(models.EventFeedback(user_id=user.id, rating=data.rating, text=data.text))
    db.commit()
    return detail(db, _load(db, event_id), user)


@router.get("/events/{event_id}/export")
def export_participants(
    event_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    event = get_managed(db, event_id, user)
    starts = schemas.as_utc(event.starts_at).astimezone(timetable.MSK)
    regs = sorted(event.registrations, key=lambda r: (r.role != "participant", r.user.full_name))
    content = pgas.participants_xlsx(event.title, f"{starts:%d.%m.%Y %H:%M}{', ' + event.place if event.place else ''}", regs)
    return Response(
        content, media_type=pgas.XLSX,
        headers={"Content-Disposition": f"attachment; filename=\"event-{event.id}.xlsx\"", "Cache-Control": "private, no-store"},
    )
