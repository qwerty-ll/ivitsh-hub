"""Tribe tournaments: a random, balanced split of students into tribes and the tribes' standings.

Every student lands in one tribe at random; the tribe's score is what its members earn by being active (the same
confirmed facts as personal bits) plus awards and penalties from the administration; at the end the top tribes'
members get bits for the shop.
"""
import json
import random
import threading
import time as clock
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List

from sqlalchemy.orm import Session

import app.models as models
from app.core import shared
from app.routers.homework import group_key
from app.services import progress, timetable

# Section hues the client knows, in the order tribes get them
TRIBE_COLORS = ["blue", "red", "green", "violet", "orange", "teal", "pink", "amber"]
DEFAULT_NAMES = ["Альфа", "Бета", "Гамма", "Дельта", "Эпсилон", "Зета", "Эта", "Тета"]

_rng = random.SystemRandom()
_cache: Dict[int, tuple] = {}
CACHE_SECONDS = 300
# One computation per tournament at a time: the others wait for it instead of repeating it
_computing: Dict[int, threading.Lock] = defaultdict(threading.Lock)
_computing_guard = threading.Lock()
# Shared snapshots outlive a tournament's last change by at most this long (finished ones are re-read rarely)
_SHARED_TTL = 7 * 24 * 3600
# How long one worker may hold the "I am recomputing" mark
_SHARED_LOCK_SECONDS = 120


def _version(r) -> int:
    return int(r.get(shared.key("tribes", "version")) or 0)


def _get(tid: int):
    """(computed at, snapshot) or None: from Redis when the workers share state, else from this process."""
    r = shared.client()
    if r is None:
        return _cache.get(tid)
    raw = r.get(shared.key("tribes", _version(r), tid))
    return tuple(json.loads(raw)) if raw else None


def _put(tid: int, computed_at: float, snapshot: Dict) -> None:
    r = shared.client()
    if r is None:
        _cache[tid] = (computed_at, snapshot)
        return
    r.set(shared.key("tribes", _version(r), tid), json.dumps([computed_at, snapshot], ensure_ascii=False), ex=_SHARED_TTL)


def _claim_shared(tid: int) -> bool:
    """Only one worker recomputes a stale snapshot; the others keep serving it."""
    r = shared.client()
    return r is None or bool(r.set(shared.key("tribes", "computing", tid), 1, nx=True, ex=_SHARED_LOCK_SECONDS))


def _release_shared(tid: int) -> None:
    r = shared.client()
    if r is not None:
        r.delete(shared.key("tribes", "computing", tid))


def clear_cache() -> None:
    """After an administrator's change: every worker drops its snapshots (a new version in Redis)."""
    _cache.clear()
    r = shared.client()
    if r is not None:
        r.incr(shared.key("tribes", "version"))


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


def _compute(db: Session, t: models.Tournament) -> Dict:
    """The standings snapshot: every tribe's points, every member with name and contribution.
    JSON-friendly, so any worker can keep or share it."""
    tribes = db.query(models.Tribe).filter(models.Tribe.tournament_id == t.id).order_by(models.Tribe.id).all()
    members = (
        db.query(models.TribeMember.user_id, models.TribeMember.tribe_id, models.TribeMember.joined_at,
                 models.User.full_name, models.User.group_number, models.User.photo_name, models.User.avatar_url,
                 models.User.photo_public, models.User.auth_source)
        .join(models.User, models.TribeMember.user_id == models.User.id)
        .filter(models.TribeMember.tournament_id == t.id)
        .all()
    )
    awards = (
        db.query(models.TribeAward).join(models.Tribe, models.TribeAward.tribe_id == models.Tribe.id)
        .filter(models.Tribe.tournament_id == t.id).order_by(models.TribeAward.created_at.desc()).all()
    )
    today = timetable.msk_now().date()
    spans = {}
    for uid, _, joined_at, *_ in members:
        joined = progress._as_utc(joined_at).astimezone(timetable.MSK).date() if joined_at else t.starts_on
        spans[uid] = (max(t.starts_on, joined), min(t.ends_on, today))
    earned = progress.earned_between_many(db, spans)

    award_sum: Dict[int, int] = defaultdict(int)
    for a in awards:
        award_sum[a.tribe_id] += a.points
    by_tribe: Dict[int, List] = defaultdict(list)
    for uid, tribe_id, *_ in members:
        by_tribe[tribe_id].append(uid)
    rows = []
    for tribe in tribes:
        count = len(by_tribe[tribe.id])
        activity = sum(earned[uid] for uid in by_tribe[tribe.id])
        awarded = award_sum[tribe.id]
        points = tribe.final_points if t.status == "finished" and tribe.final_points is not None else activity + awarded
        rows.append({
            "id": tribe.id, "name": tribe.name, "color": tribe.color,
            "members": count, "points": points, "activity": activity, "awards": awarded,
            "average": round(activity / count, 1) if count else 0,
            "place": tribe.place,
        })
    rows.sort(key=lambda x: (-x["points"], x["name"]))
    prev = None
    for i, row in enumerate(rows, start=1):
        # Equal points share a place, as at the finish
        if row["place"]:
            row["rank"] = row["place"]
        else:
            row["rank"] = rows[i - 2]["rank"] if prev is not None and row["points"] == prev else i
        prev = row["points"]
    return {
        "status": t.status,
        "tribes": rows,
        # [user id, tribe id, full name, group, points, photo]
        "people": [[uid, tribe_id, name, group, earned[uid], models.User.public_photo(uid, photo, avatar, public, source)]
                   for uid, tribe_id, _, name, group, photo, avatar, public, source in members],
        # [tribe id, points, reason, when] — the latest ones
        "awards": [[a.tribe_id, a.points, a.reason, progress._as_utc(a.created_at).isoformat() if a.created_at else None]
                   for a in awards[:30]],
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def _fresh(t: models.Tournament, hit) -> bool:
    if hit is None or hit[1]["status"] != t.status:
        return False
    # A finished tournament never changes: its snapshot is kept until an administrator touches it
    return t.status == "finished" or clock.time() - hit[0] < CACHE_SECONDS


def standings(db: Session, t: models.Tournament) -> Dict:
    """The cached snapshot. When it is out of date one request rebuilds it and the rest get the previous one
    meanwhile, so a crowd opening the page never queues behind the computation."""
    hit = _get(t.id)
    if _fresh(t, hit):
        return hit[1]
    with _computing_guard:
        lock = _computing[t.id]
    usable = hit is not None and hit[1]["status"] == t.status
    if usable:
        if not lock.acquire(blocking=False):
            return hit[1]
        claimed = _claim_shared(t.id)
        if not claimed:
            lock.release()
            return hit[1]
    else:
        # Nothing to show yet: compute now (another worker may be doing the same, once)
        lock.acquire()
        claimed = _claim_shared(t.id)
    try:
        hit = _get(t.id)
        if _fresh(t, hit):
            return hit[1]
        result = _compute(db, t)
        _put(t.id, clock.time(), result)
        return result
    finally:
        if claimed:
            _release_shared(t.id)
        lock.release()


def add_member(t: models.Tournament, tribe_id: int, user: models.User) -> None:
    """A newcomer joined: put them into the cached snapshot instead of recomputing everything."""
    hit = _get(t.id)
    if hit is None:
        return
    snapshot = dict(hit[1])
    snapshot["people"] = hit[1]["people"] + [[user.id, tribe_id, user.full_name, user.group_number, 0, user.photo_url]]
    rows = [dict(r) for r in hit[1]["tribes"]]
    for r in rows:
        if r["id"] == tribe_id:
            r["members"] += 1
            r["average"] = round(r["activity"] / r["members"], 1)
    snapshot["tribes"] = rows
    _put(t.id, hit[0], snapshot)
