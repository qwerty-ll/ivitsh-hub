"""Association meetings: set by leaders, seen by members in their calendar; attendance and a summary afterwards.

Rights: approved members see the association's meetings; its leaders and administrators manage them.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.database import get_db
import app.models as models
import app.schemas as schemas
import app.core.security as security
from app.routers.associations import _get_association, is_leader, require_manager

router = APIRouter(prefix="/api/v1", tags=["Meetings"])


def is_member(db: Session, user: models.User, association_id: int) -> bool:
    return db.query(models.Membership).filter(
        models.Membership.user_id == user.id,
        models.Membership.association_id == association_id,
        models.Membership.status == "approved",
    ).first() is not None


def _can_manage(db: Session, user: models.User, association_id: int) -> bool:
    return user.role == "admin" or is_leader(db, user, association_id)


def meeting_item(db: Session, meeting: models.Meeting, manage: bool) -> Dict:
    item = {
        "id": meeting.id,
        "title": meeting.title,
        "starts_at": meeting.starts_at,
        "ends_at": meeting.ends_at,
        "place": meeting.place or "",
        "agenda": meeting.agenda or "",
        "summary": meeting.summary or "",
        "association": {"id": meeting.association.id, "name": meeting.association.name},
        "created_by": meeting.created_by.full_name if meeting.created_by else None,
        "can_manage": manage,
        "attendance": [],
        "attended_count": None,
    }
    if manage:
        present = {a.user_id for a in meeting.attendance}
        members = (
            db.query(models.Membership)
            .options(joinedload(models.Membership.user))
            .filter(models.Membership.association_id == meeting.association_id, models.Membership.status == "approved")
            .all()
        )
        people = {m.user_id: m.user for m in members}
        # People who were marked and left the association since still count
        for uid in present - people.keys():
            user = db.get(models.User, uid)
            if user:
                people[uid] = user
        item["attendance"] = [
            {"user_id": u.id, "full_name": u.full_name, "group_number": u.group_number, "present": u.id in present}
            for u in sorted(people.values(), key=lambda u: u.full_name)
        ]
        item["attended_count"] = len(present)
    return item


def _load(db: Session, meeting_id: int, user: models.User) -> models.Meeting:
    """The meeting if the user may see it; 404 otherwise."""
    meeting = (
        db.query(models.Meeting)
        .options(joinedload(models.Meeting.association), joinedload(models.Meeting.created_by),
                 selectinload(models.Meeting.attendance))
        .filter(models.Meeting.id == meeting_id)
        .first()
    )
    if not meeting or not (
        _can_manage(db, user, meeting.association_id)
        or (meeting.association.is_active and is_member(db, user, meeting.association_id))
    ):
        raise HTTPException(status_code=404, detail="Собрание не найдено")
    return meeting


def _managed(db: Session, meeting_id: int, user: models.User) -> models.Meeting:
    meeting = _load(db, meeting_id, user)
    if not _can_manage(db, user, meeting.association_id):
        raise HTTPException(status_code=403, detail="Собрания назначают руководители объединения")
    return meeting


@router.get("/associations/{association_id}/meetings", response_model=List[schemas.MeetingItem])
def list_meetings(
    association_id: int,
    past: bool = Query(False, description="Past meetings (newest first) instead of upcoming ones"),
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    manage = _can_manage(db, user, association_id)
    _get_association(db, association_id, include_inactive=user.role == "admin")
    if not (manage or is_member(db, user, association_id)):
        raise HTTPException(status_code=403, detail="Собрания видят участники объединения")
    now = datetime.now(timezone.utc)
    query = (
        db.query(models.Meeting)
        .options(joinedload(models.Meeting.association), joinedload(models.Meeting.created_by),
                 selectinload(models.Meeting.attendance))
        .filter(models.Meeting.association_id == association_id)
    )
    if past:
        query = query.filter(models.Meeting.ends_at <= now).order_by(models.Meeting.starts_at.desc()).limit(30)
    else:
        query = query.filter(models.Meeting.ends_at > now).order_by(models.Meeting.starts_at)
    return [meeting_item(db, m, manage) for m in query.all()]


@router.post("/associations/{association_id}/meetings", response_model=schemas.MeetingItem, status_code=201)
def create_meeting(
    association_id: int,
    data: schemas.MeetingIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    require_manager(association_id, user, db)
    meeting = models.Meeting(association_id=association_id, created_by_id=user.id, **data.model_dump())
    db.add(meeting)
    db.commit()
    return meeting_item(db, _load(db, meeting.id, user), True)


@router.get("/meetings/{meeting_id}", response_model=schemas.MeetingItem)
def get_meeting(
    meeting_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    meeting = _load(db, meeting_id, user)
    return meeting_item(db, meeting, _can_manage(db, user, meeting.association_id))


@router.put("/meetings/{meeting_id}", response_model=schemas.MeetingItem)
def edit_meeting(
    meeting_id: int,
    data: schemas.MeetingIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    meeting = _managed(db, meeting_id, user)
    for field, value in data.model_dump().items():
        setattr(meeting, field, value)
    db.commit()
    return meeting_item(db, _load(db, meeting_id, user), True)


@router.delete("/meetings/{meeting_id}", status_code=200)
def delete_meeting(
    meeting_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    db.delete(_managed(db, meeting_id, user))
    db.commit()
    return {"ok": True}


@router.put("/meetings/{meeting_id}/attendance", response_model=schemas.MeetingItem)
def set_attendance(
    meeting_id: int,
    data: schemas.AttendanceIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    meeting = _managed(db, meeting_id, user)
    if meeting.starts_at and schemas.as_utc(meeting.starts_at) > datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Присутствие отмечают, когда собрание началось")
    allowed = {
        uid for (uid,) in db.query(models.Membership.user_id).filter(
            models.Membership.association_id == meeting.association_id, models.Membership.status == "approved")
    } | {a.user_id for a in meeting.attendance}
    wanted = set(data.user_ids)
    if wanted - allowed:
        raise HTTPException(status_code=400, detail="Отметить можно только участников объединения")
    meeting.attendance = [a for a in meeting.attendance if a.user_id in wanted]
    have = {a.user_id for a in meeting.attendance}
    meeting.attendance.extend(models.MeetingAttendance(user_id=uid) for uid in wanted - have)
    db.commit()
    return meeting_item(db, _load(db, meeting_id, user), True)
