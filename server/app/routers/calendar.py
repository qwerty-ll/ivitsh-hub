"""The student's calendar: EIOS lessons (with SDO course links), association meetings,
task deadlines and group homework, for a range of days."""
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
import app.models as models
import app.schemas as schemas
import app.core.security as security
from app.routers.homework import group_key
from app.services import sdo, timetable

logger = logging.getLogger("ivitsh_portal.calendar")

router = APIRouter(prefix="/api/v1", tags=["Calendar"])

MAX_DAYS = 42


def _courses(db: Session, user: models.User) -> List[Tuple[int, str]]:
    rows = db.query(models.SdoCourse).filter(models.SdoCourse.user_id == user.id).all()
    return sorted(((r.course_id, r.name) for r in rows), key=lambda c: c[1].casefold())


async def _lessons(user: models.User, start: date, end: date) -> Tuple[str, List[timetable.Lesson]]:
    if not (user.group_number or "").strip():
        return "no_group", []
    years = {timetable.academic_year(start), timetable.academic_year(end)}
    lessons: List[timetable.Lesson] = []
    stale = found_any = False
    try:
        for year in sorted(years):
            # The saved idGroup belongs to the academic year of the last sign-in; names do not change
            group_id = user.eios_group_id if year == timetable.academic_year(timetable.msk_now().date()) else None
            if not group_id:
                found = await timetable.find_group(user.group_number, year)
                if not found:
                    continue
                group_id = found["id"]
            found_any = True
            year_lessons, year_stale = await timetable.group_lessons(group_id, year)
            stale = stale or year_stale
            lessons.extend(l for l in year_lessons if start <= l.day <= end)
    except timetable.TimetableUnavailable:
        return "unavailable", []
    if not found_any:
        # A group EIOS does not know (typed by hand with a typo, or not a student)
        return "no_group", []
    return ("stale" if stale else "ok"), lessons


@router.get("/calendar", response_model=schemas.CalendarOut)
async def get_calendar(
    start: date = Query(..., description="First day, YYYY-MM-DD (Moscow time)"),
    days: int = Query(7, ge=1, le=MAX_DAYS),
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    end = start + timedelta(days=days - 1)
    # The range in Moscow days, as UTC instants
    since = datetime.combine(start, time(0), tzinfo=timetable.MSK).astimezone(timezone.utc)
    until = since + timedelta(days=days)
    items: List[Dict] = []

    status, lessons = await _lessons(user, start, end)
    courses = _courses(db, user)
    for i, lesson in enumerate(lessons):
        course = sdo.match_course(lesson.discipline, courses)
        items.append({
            "type": "lesson",
            "id": f"lesson-{lesson.day.isoformat()}-{lesson.start}-{i}",
            "title": lesson.discipline,
            "starts_at": lesson.starts_at,
            "ends_at": lesson.ends_at,
            "place": lesson.room,
            "kind": lesson.kind,
            "teacher": lesson.teacher,
            "subgroup": lesson.subgroup,
            "replaced": lesson.replaced,
            "course": {"id": course[0], "name": course[1], "url": sdo.course_url(course[0])} if course else None,
        })

    # Meetings of the associations the user belongs to or leads
    association_ids = [
        aid for (aid,) in db.query(models.Membership.association_id)
        .join(models.Association)
        .filter(models.Membership.user_id == user.id, models.Membership.status == "approved",
                models.Association.is_active.is_(True))
    ]
    if association_ids:
        meetings = (
            db.query(models.Meeting)
            .options(joinedload(models.Meeting.association))
            .filter(models.Meeting.association_id.in_(association_ids),
                    models.Meeting.starts_at < until, models.Meeting.ends_at > since)
            .all()
        )
        for m in meetings:
            items.append({
                "type": "meeting",
                "id": f"meeting-{m.id}",
                "ref_id": m.id,
                "title": m.title,
                "starts_at": m.starts_at,
                "ends_at": m.ends_at,
                "place": m.place or "",
                "text": m.agenda or "",
                "association": {"id": m.association.id, "name": m.association.name},
            })

    # My task cards with a deadline in range
    cards = (
        db.query(models.TaskAssignee)
        .join(models.Task)
        .options(joinedload(models.TaskAssignee.task).joinedload(models.Task.association))
        .filter(models.TaskAssignee.user_id == user.id, models.Task.due_at >= since, models.Task.due_at < until)
        .all()
    )
    for card in cards:
        task = card.task
        if task.association and not task.association.is_active:
            continue
        items.append({
            "type": "task",
            "id": f"task-{task.id}",
            "ref_id": task.id,
            "title": task.title,
            "starts_at": task.due_at,
            "status": card.status,
            "color": task.color,
            "association": {"id": task.association.id, "name": task.association.name} if task.association else None,
        })

    key = group_key(user.group_number)
    if key:
        entries = (
            db.query(models.GroupHomework)
            .filter(models.GroupHomework.group_key == key,
                    models.GroupHomework.due_at >= since, models.GroupHomework.due_at < until)
            .all()
        )
        for e in entries:
            items.append({
                "type": "homework",
                "id": f"homework-{e.id}",
                "ref_id": e.id,
                "title": e.subject or "Домашнее задание",
                "starts_at": e.due_at,
                "text": e.text,
            })

    items.sort(key=lambda it: (schemas.as_utc(it["starts_at"]), it["type"] != "lesson", it["id"]))
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "group": user.group_number,
        "lessons": status,
        "items": items,
    }


@router.get("/calendar/courses", response_model=List[schemas.SdoCourseItem])
def my_courses(
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    return [{"id": cid, "name": name, "url": sdo.course_url(cid)} for cid, name in _courses(db, user)]
