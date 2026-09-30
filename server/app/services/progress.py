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
# Counted per semester at most, so nothing can be farmed. Institute events are set by the administration and
# are not capped; everything an association leader creates (events, meetings, tasks) is.
CAPS = {"homework": 10, "answer": 15, "tasks": 15, "meetings": 12, "association_events": 8, "organized": 5}
# A task counts only if it lived this long before it was handed in (no "create and tick" micro-tasks)
TASK_MIN_LIFETIME = timedelta(hours=12)
# An organized event counts when this many other people came
ORGANIZED_MIN_PEOPLE = 3

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
    events = volunteer = association_events = 0
    for reg, event in regs:
        if _as_utc(event.ends_at) <= now and _in(event.starts_at, bounds):
            if event.scope != "institute":
                association_events += 1
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
    # Only association tasks the leader accepted ("Готово"), with a deadline, set by someone else,
    # that existed a while before being handed in. Personal tasks never count: anyone could tick them off.
    cards = (
        db.query(models.TaskAssignee.completed_at, models.Task.due_at, models.Task.created_at)
        .join(models.Task, models.TaskAssignee.task_id == models.Task.id)
        .filter(models.TaskAssignee.user_id == user.id, models.TaskAssignee.status == "done",
                models.TaskAssignee.completed_at.isnot(None), models.Task.association_id.isnot(None),
                models.Task.due_at.isnot(None), models.Task.created_by_id != user.id)
        .all()
    )
    for completed, due, created in cards:
        if not _in(completed, bounds) or _as_utc(completed) - _as_utc(created) < TASK_MIN_LIFETIME:
            continue
        if _as_utc(completed) <= _as_utc(due):
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
            came = sum(r.attended is not False for r in event.registrations if r.user_id != user.id)
            took_place = came >= ORGANIZED_MIN_PEOPLE
            if _as_utc(event.ends_at) <= now and took_place and _in(event.starts_at, bounds):
                organized += 1

    return {
        "events": events, "volunteer": volunteer, "association_events": association_events, "meetings": meetings, "on_time": on_time, "late": late,
        "homework": homework, "answers": answers, "solutions": solutions,
        "associations": associations, "organized": organized,
    }


def points(f: Dict[str, int], capped: bool) -> int:
    """Points of one period (a semester): the caps apply within it."""
    def cap(value: int, key: str) -> int:
        return min(value, CAPS[key]) if capped else value

    # Association events beyond the cap stop counting; institute ones always count
    extra = max(0, f["association_events"] - CAPS["association_events"]) if capped else 0
    events, volunteer = f["events"], f["volunteer"]
    # Drop the cheaper ones first: plain participation, then volunteering
    drop_events = min(extra, events)
    drop_volunteer = min(extra - drop_events, volunteer)
    tasks_on_time = cap(f["on_time"], "tasks")
    tasks_late = min(f["late"], max(0, CAPS["tasks"] - tasks_on_time)) if capped else f["late"]
    return (
        (events - drop_events) * POINTS["event"] + (volunteer - drop_volunteer) * POINTS["volunteer"]
        + cap(f["meetings"], "meetings") * POINTS["meeting"]
        + tasks_on_time * POINTS["task_on_time"] + tasks_late * POINTS["task_late"]
        + cap(f["homework"], "homework") * POINTS["homework"] + cap(f["answers"], "answer") * POINTS["answer"]
        + f["solutions"] * POINTS["solution"] + cap(f["organized"], "organized") * POINTS["organized"]
    )


def _semester_starts(first: date, last: date) -> List[Tuple[date, date]]:
    out, day = [], first
    while day <= last:
        start, end = pgas.semester_of(day)
        out.append((start, end))
        day = end + timedelta(days=1)
    return out


def earned_between(db: Session, user: models.User, first: date, last: date) -> int:
    """Points earned from activity over a span of days, the caps applied semester by semester."""
    total = 0
    for s, e in _semester_starts(first, last):
        total += points(facts(db, user, _msk_bounds(max(s, first), min(e, last))), capped=True)
    return total


def earned_total(db: Session, user: models.User) -> int:
    joined = (_as_utc(user.created_at) or datetime.now(timezone.utc)).astimezone(timetable.MSK).date()
    # From the start of the semester the account appeared in: organizers may add people to events before that
    return earned_between(db, user, pgas.semester_of(joined)[0], timetable.msk_now().date())


def balance(db: Session, user: models.User, earned: Optional[int] = None) -> Dict[str, int]:
    """Bits to spend: earned from activity + granted (prizes, by hand) − spent in the shop (cancelled orders refunded)."""
    earned = earned_total(db, user) if earned is None else earned
    granted = db.query(func.coalesce(func.sum(models.BitsGrant.amount), 0)).filter(
        models.BitsGrant.user_id == user.id).scalar() or 0
    spent = db.query(func.coalesce(func.sum(models.ShopOrder.price), 0)).filter(
        models.ShopOrder.user_id == user.id, models.ShopOrder.status != "cancelled").scalar() or 0
    return {"earned": earned, "granted": int(granted), "spent": int(spent), "available": earned + int(granted) - int(spent)}


def summary(db: Session, user: models.User) -> Dict:
    today = timetable.msk_now().date()
    total_facts = facts(db, user)
    total = earned_total(db, user)
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
        "caps": CAPS,
        "balance": balance(db, user, earned=total),
    }
