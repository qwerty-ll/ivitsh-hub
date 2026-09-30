"""Tribe tournaments: a random, balanced split of students into tribes and the tribes' standings.

Every student lands in one tribe at random; the tribe's score is what its members earn by being active (the same
confirmed facts as personal bits) plus awards and penalties from the administration; at the end the top tribes'
members get bits for the shop.
"""
import random
import time as clock
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Dict, List

from sqlalchemy.orm import Session, selectinload

import app.models as models
from app.routers.homework import group_key
from app.services import progress, timetable

# Section hues the client knows, in the order tribes get them
TRIBE_COLORS = ["blue", "red", "green", "violet", "orange", "teal", "pink", "amber"]
DEFAULT_NAMES = ["Альфа", "Бета", "Гамма", "Дельта", "Эпсилон", "Зета", "Эта", "Тета"]

_rng = random.SystemRandom()
_cache: Dict[int, tuple] = {}
CACHE_SECONDS = 300


def clear_cache() -> None:
    _cache.clear()


def pool(db: Session, tournament: models.Tournament) -> List[models.User]:
    """Who takes part: students who signed in through EIOS, not blocked; only the chosen groups if any."""
    wanted = {group_key(g) for g in (tournament.groups or "").split(",")} - {""}
    users = db.query(models.User).filter(models.User.role == "student", models.User.auth_source == "eios",
                                         models.User.is_blocked.is_(False)).all()
    return [u for u in users if not wanted or group_key(u.group_number) in wanted]


def split(users: List[models.User], tribes: int) -> List[List[models.User]]:
    """A random split into `tribes` teams of equal size (±1) with every academic group spread evenly:
    shuffle within each group, lay the groups end to end in random order, deal the line out one by one."""
    by_group: Dict[str, List[models.User]] = defaultdict(list)
    for u in users:
        by_group[group_key(u.group_number)].append(u)
    groups = list(by_group.values())
    _rng.shuffle(groups)
    line: List[models.User] = []
    for g in groups:
        _rng.shuffle(g)
        line.extend(g)
    teams: List[List[models.User]] = [[] for _ in range(tribes)]
    # Start dealing from a random tribe so the extra person does not always land in the first one
    offset = _rng.randrange(tribes)
    for i, u in enumerate(line):
        teams[(i + offset) % tribes].append(u)
    return teams


def _member_points(db: Session, member: models.TribeMember, t: models.Tournament, today: date) -> int:
    joined = progress._as_utc(member.joined_at).astimezone(timetable.MSK).date() if member.joined_at else t.starts_on
    first = max(t.starts_on, joined)
    last = min(t.ends_on, today)
    if last < first:
        return 0
    return progress.earned_between(db, member.user, first, last)


def standings(db: Session, t: models.Tournament) -> Dict:
    """Tribes by points, and every member's contribution. Cached for a few minutes: it is heavy."""
    hit = _cache.get(t.id)
    if hit and clock.time() - hit[0] < CACHE_SECONDS and t.status != "finished":
        return hit[1]
    t = (
        db.query(models.Tournament)
        .options(selectinload(models.Tournament.tribes).selectinload(models.Tribe.members).joinedload(models.TribeMember.user),
                 selectinload(models.Tournament.tribes).selectinload(models.Tribe.awards))
        .filter(models.Tournament.id == t.id).one()
    )
    today = timetable.msk_now().date()
    tribes = []
    for tribe in t.tribes:
        contributions = {m.user_id: _member_points(db, m, t, today) for m in tribe.members}
        awards = sum(a.points for a in tribe.awards)
        activity = sum(contributions.values())
        points = tribe.final_points if t.status == "finished" and tribe.final_points is not None else activity + awards
        tribes.append({
            "id": tribe.id, "name": tribe.name, "color": tribe.color,
            "members": len(tribe.members), "points": points, "activity": activity, "awards": awards,
            "average": round(activity / len(tribe.members), 1) if tribe.members else 0,
            "place": tribe.place,
            "contributions": contributions,
        })
    tribes.sort(key=lambda x: (-x["points"], x["name"]))
    prev = None
    for i, tribe in enumerate(tribes, start=1):
        # Equal points share a place, as at the finish
        if tribe["place"]:
            tribe["rank"] = tribe["place"]
        else:
            tribe["rank"] = tribes[i - 2]["rank"] if prev is not None and tribe["points"] == prev else i
        prev = tribe["points"]
    result = {"tribes": tribes, "computed_at": datetime.now(timezone.utc).isoformat()}
    _cache[t.id] = (clock.time(), result)
    return result
