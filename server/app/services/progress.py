"""Achievements and points ("биты", after the «8 бит» coworking) computed from what the student did on the portal.

Nothing here is stored: everything is counted from confirmed facts (attendance marked or not denied,
work handed in, answers the asker chose), so there is nothing to farm by clicking. Only the student sees theirs.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

import app.models as models
from app.services import pgas, timetable

# What each confirmed action is worth
POINTS = {
    "event": 10,          # took part in an event (not marked absent)
    "volunteer": 15,      # helped as a volunteer
    "meeting": 3,         # marked present at an association meeting
    "task_on_time": 5,    # handed in by the deadline
    "task_late": 2,       # handed in after it
    "homework": 2,        # an entry in the group's homework
    "answer": 2,          # an answer on the forum
    "solution": 5,        # ... that the asker marked as the solution
    "organized": 20,      # a leader's event that took place with people
}
# Counted per semester at most: cheap actions cannot be farmed
CAPS = {"homework": 10, "answer": 15}

LEVELS: List[Tuple[int, str]] = [
    (0, "Новичок"),
    (50, "Вливается"),
    (150, "Активист"),
    (300, "Опора ИВИТШ"),
    (600, "Легенда ИВИТШ"),
]


@dataclass
class Badge:
    id: str
    title: str
    # One line per level: what it takes
    hint: str
    thresholds: Tuple[int, ...]
    icon: str  # a lucide icon name the client knows


BADGES = [
    Badge("events", "Участник мероприятий", "Побывать на мероприятиях: {n}", (1, 5, 15), "PartyPopper"),
    Badge("volunteer", "Волонтёр", "Помочь волонтёром: {n}", (1, 3, 10), "HandHeart"),
    Badge("meetings", "В команде", "Прийти на собрания объединения: {n}", (3, 10, 25), "Users"),
    Badge("on_time", "Точно в срок", "Сдать задачи вовремя: {n}", (1, 10, 30), "Clock"),
    Badge("homework", "Спасатель группы", "Записать ДЗ для группы: {n}", (1, 5, 20), "NotebookPen"),
    Badge("answers", "Знаток", "Решить вопрос на форуме (ответ выбран лучшим): {n}", (1, 5, 15), "MessageCircle"),
    Badge("associations", "Командный игрок", "Состоять в объединениях: {n}", (1, 2, 3), "Handshake"),
    Badge("organized", "Организатор", "Провести мероприятие объединения: {n}", (1, 3, 10), "Megaphone"),
]


def _msk_bounds(start: date, end: date) -> Tuple[datetime, datetime]:
    return (datetime.combine(start, time(0), tzinfo=timetable.MSK),
            datetime.combine(end + timedelta(days=1), time(0), tzinfo=timetable.MSK))


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _in(value: Optional[datetime], bounds: Optional[Tuple[datetime, datetime]]) -> bool:
    if bounds is None:
        return True
    value = _as_utc(value)
    return value is not None and bounds[0] <= value < bounds[1]


def facts(db: Session, user: models.User, bounds: Optional[Tuple[datetime, datetime]] = None) -> Dict[str, int]:
    """Counts of confirmed actions, overall or within a period."""
    now = datetime.now(timezone.utc)
    regs = (
        db.query(models.EventRegistration, models.Event)
        .join(models.Event, models.EventRegistration.event_id == models.Event.id)
        .filter(models.EventRegistration.user_id == user.id, models.EventRegistration.attended.isnot(False))
        .all()
    )
    events = volunteer = 0
    for reg, event in regs:
        if _as_utc(event.ends_at) <= now and _in(event.starts_at, bounds):
            if reg.role == "volunteer":
                volunteer += 1
            else:
                events += 1

    meetings = sum(
        1 for (starts,) in db.query(models.Meeting.starts_at)
        .join(models.MeetingAttendance, models.MeetingAttendance.meeting_id == models.Meeting.id)
        .filter(models.MeetingAttendance.user_id == user.id)
        if _in(starts, bounds)
    )

    on_time = late = 0
    cards = (
        db.query(models.TaskAssignee.completed_at, models.Task.due_at, models.Task.association_id)
        .join(models.Task, models.TaskAssignee.task_id == models.Task.id)
        .filter(models.TaskAssignee.user_id == user.id, models.TaskAssignee.completed_at.isnot(None))
        .all()
    )
    for completed, due, association_id in cards:
        # Personal tasks do not count: anyone could tick them off
        if association_id is None or not _in(completed, bounds):
            continue
        if due is None or _as_utc(completed) <= _as_utc(due):
            on_time += 1
        else:
            late += 1

    homework = sum(1 for (created,) in db.query(models.GroupHomework.created_at)
                   .filter(models.GroupHomework.created_by_id == user.id) if _in(created, bounds))
    answers = solutions = 0
    for created, is_solution in db.query(models.ForumAnswer.created_at, models.ForumAnswer.is_solution).filter(
            models.ForumAnswer.author_id == user.id):
        if _in(created, bounds):
            answers += 1
            solutions += bool(is_solution)

    associations = db.query(func.count(models.Membership.id)).filter(
        models.Membership.user_id == user.id, models.Membership.status == "approved").scalar() or 0

    organized = 0
    led = [aid for (aid,) in db.query(models.Membership.association_id).filter(
        models.Membership.user_id == user.id, models.Membership.role == "leader")]
    if led:
        for event in db.query(models.Event).filter(models.Event.created_by_id == user.id,
                                                   models.Event.association_id.in_(led)).all():
            took_place = any(r.attended is not False for r in event.registrations if r.user_id != user.id)
            if _as_utc(event.ends_at) <= now and took_place and _in(event.starts_at, bounds):
                organized += 1

    return {
        "events": events, "volunteer": volunteer, "meetings": meetings, "on_time": on_time, "late": late,
        "homework": homework, "answers": answers, "solutions": solutions,
        "associations": associations, "organized": organized,
    }


def points(f: Dict[str, int], capped: bool) -> int:
    homework = min(f["homework"], CAPS["homework"]) if capped else f["homework"]
    answers = min(f["answers"], CAPS["answer"]) if capped else f["answers"]
    return (
        f["events"] * POINTS["event"] + f["volunteer"] * POINTS["volunteer"] + f["meetings"] * POINTS["meeting"]
        + f["on_time"] * POINTS["task_on_time"] + f["late"] * POINTS["task_late"]
        + homework * POINTS["homework"] + answers * POINTS["answer"] + f["solutions"] * POINTS["solution"]
        + f["organized"] * POINTS["organized"]
    )


def _semester_starts(first: date, last: date) -> List[Tuple[date, date]]:
    out, day = [], first
    while day <= last:
        start, end = pgas.semester_of(day)
        out.append((start, end))
        day = end + timedelta(days=1)
    return out


def summary(db: Session, user: models.User) -> Dict:
    today = timetable.msk_now().date()
    total_facts = facts(db, user)
    # Caps apply per semester: sum the semesters since the account appeared
    joined = (_as_utc(user.created_at) or datetime.now(timezone.utc)).astimezone(timetable.MSK).date()
    total = sum(points(facts(db, user, _msk_bounds(s, e)), capped=True) for s, e in _semester_starts(joined, today))
    sem_start, sem_end = pgas.semester_of(today)
    semester = points(facts(db, user, _msk_bounds(sem_start, sem_end)), capped=True)

    values = dict(total_facts, answers=total_facts["solutions"])
    badges = []
    for b in BADGES:
        value = values[b.id]
        level = sum(value >= t for t in b.thresholds)
        nxt = b.thresholds[level] if level < len(b.thresholds) else None
        badges.append({
            "id": b.id, "title": b.title, "icon": b.icon, "value": value, "level": level,
            "max_level": len(b.thresholds), "next": nxt,
            "hint": b.hint.format(n=nxt if nxt is not None else b.thresholds[-1]),
        })

    idx = max(i for i, (need, _) in enumerate(LEVELS) if total >= need)
    nxt = LEVELS[idx + 1] if idx + 1 < len(LEVELS) else None
    return {
        "points": total,
        "semester_points": semester,
        "level": {
            "index": idx + 1, "title": LEVELS[idx][1], "from": LEVELS[idx][0],
            "next_title": nxt[1] if nxt else None, "next_at": nxt[0] if nxt else None,
        },
        "badges": badges,
        "facts": total_facts,
        "rules": POINTS,
    }
