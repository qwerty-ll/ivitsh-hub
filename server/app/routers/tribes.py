"""Tribe tournaments: the administration starts one, the portal splits students into equal tribes at random,
tribes collect their members' points plus awards, and at the end the top tribes' members get bits.

Everyone signed in sees the standings; member lists show names only (no contacts).
"""
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.database import get_db
import app.models as models
import app.schemas as schemas
import app.core.security as security
from app.services import tribes as tribes_service

router = APIRouter(prefix="/api/v1", tags=["Tribes"])

# The tribe's best contributors shown to everyone
TOP_SHOWN = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load(db: Session, tournament_id: int) -> models.Tournament:
    t = (
        db.query(models.Tournament)
        .options(selectinload(models.Tournament.tribes).selectinload(models.Tribe.members).joinedload(models.TribeMember.user),
                 selectinload(models.Tournament.tribes).selectinload(models.Tribe.awards))
        .filter(models.Tournament.id == tournament_id)
        .first()
    )
    if not t:
        raise HTTPException(status_code=404, detail="Турнир не найден")
    return t


def _current(db: Session) -> Optional[models.Tournament]:
    """The running tournament, or else the latest one."""
    t = db.query(models.Tournament).filter(models.Tournament.status == "active").first()
    if t:
        return t
    return db.query(models.Tournament).filter(models.Tournament.status == "finished").order_by(
        models.Tournament.ends_on.desc()).first()


def _auto_join(db: Session, t: models.Tournament, user: models.User, snapshot: Dict) -> Dict:
    """A student who appeared after the split joins the smallest tribe (while the tournament runs)."""
    if t.status != "active" or not t.auto_join or user.role != "student" or user.is_blocked or user.auth_source != "eios":
        return snapshot
    if any(p[0] == user.id for p in snapshot["people"]):
        return snapshot
    wanted = {tribes_service.group_key(g) for g in (t.groups or "").split(",")} - {""}
    if wanted and tribes_service.group_key(user.group_number) not in wanted:
        return snapshot
    if db.query(models.TribeMember.id).filter_by(tournament_id=t.id, user_id=user.id).first():
        return snapshot
    sizes = dict(db.query(models.Tribe.id, func.count(models.TribeMember.id))
                 .outerjoin(models.TribeMember, models.TribeMember.tribe_id == models.Tribe.id)
                 .filter(models.Tribe.tournament_id == t.id).group_by(models.Tribe.id).all())
    if not sizes:
        return snapshot
    smallest = min(sizes, key=lambda tid: (sizes[tid], tid))
    db.add(models.TribeMember(tournament_id=t.id, tribe_id=smallest, user_id=user.id))
    try:
        db.commit()
    except IntegrityError:
        # The same student's other tab joined first
        db.rollback()
        return snapshot
    tribes_service.add_member(t, smallest, user)
    return tribes_service.standings(db, t)


def view(db: Session, t: models.Tournament, user: models.User, snapshot: Optional[Dict] = None) -> Dict:
    table = snapshot or tribes_service.standings(db, t)
    by_tribe: Dict[int, list] = {}
    for uid, tribe_id, name, group, pts in table["people"]:
        by_tribe.setdefault(tribe_id, []).append((uid, name, group, pts))
    mine_id = next((p[1] for p in table["people"] if p[0] == user.id), None)
    is_admin = user.role == "admin"
    rows = []
    for row in table["tribes"]:
        ranked = sorted(by_tribe.get(row["id"], []), key=lambda p: -p[3])
        # The tribe's best contributor: its master for this tournament
        master = ranked[0][1] if ranked and ranked[0][3] > 0 else None
        shown = ranked if is_admin or mine_id == row["id"] else ranked[:TOP_SHOWN]
        top = [{"full_name": name, "group_number": group, "points": pts} for _, name, group, pts in shown[:200]]
        rows.append(dict(row) | {"master": master, "top": top})
    names = {r["id"]: r for r in table["tribes"]}
    my_points = my_rank = None
    if mine_id is not None:
        values = sorted((p[3] for p in by_tribe.get(mine_id, [])), reverse=True)
        my_points = next(p[4] for p in table["people"] if p[0] == user.id)
        my_rank = values.index(my_points) + 1
    return {
        "id": t.id, "title": t.title, "status": t.status,
        "starts_on": t.starts_on.isoformat(), "ends_on": t.ends_on.isoformat(),
        "prizes": [t.prize_1, t.prize_2, t.prize_3],
        "groups": [g for g in (t.groups or "").split(",") if g],
        "auto_join": t.auto_join,
        "tribes": rows,
        "my_tribe_id": mine_id,
        "my_points": my_points,
        "my_rank_in_tribe": my_rank,
        "awards": [
            {"tribe": names[tid]["name"], "color": names[tid]["color"], "points": pts, "reason": reason, "created_at": when}
            for tid, pts, reason, when in table["awards"] if tid in names
        ],
        "computed_at": table["computed_at"],
        "can_manage": is_admin,
    }


@router.get("/tribes/current")
def current(user: models.User = Depends(security.require_current_user), db: Session = Depends(get_db)):
    """The page everyone opens: one light row and the cached snapshot, never the whole member list."""
    t = _current(db)
    if not t:
        return {"tournament": None}
    snapshot = _auto_join(db, t, user, tribes_service.standings(db, t))
    return {"tournament": view(db, t, user, snapshot)}


@router.get("/tribes/tournaments")
def tournaments(user: models.User = Depends(security.require_current_user), db: Session = Depends(get_db)):
    rows = db.query(models.Tournament).options(selectinload(models.Tournament.tribes)).order_by(
        models.Tournament.starts_on.desc()).all()
    if user.role != "admin":
        rows = [t for t in rows if t.status != "draft"]
    counts = dict(db.query(models.TribeMember.tournament_id, func.count(models.TribeMember.id))
                  .group_by(models.TribeMember.tournament_id).all())
    out = []
    for t in rows:
        winner = next((tr for tr in t.tribes if tr.id == t.winner_tribe_id), None)
        out.append({
            "id": t.id, "title": t.title, "status": t.status, "starts_on": t.starts_on.isoformat(), "ends_on": t.ends_on.isoformat(),
            "tribes": len(t.tribes), "members": counts.get(t.id, 0),
            "winner": {"name": winner.name, "color": winner.color, "points": winner.final_points} if winner else None,
        })
    return out


@router.get("/tribes/tournaments/{tournament_id}")
def tournament(tournament_id: int, user: models.User = Depends(security.require_current_user), db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not t or (t.status == "draft" and user.role != "admin"):
        raise HTTPException(status_code=404, detail="Турнир не найден")
    return view(db, t, user)


# --- The administration ---------------------------------------------------------------------------

@router.post("/tribes/tournaments", status_code=201)
def create(data: schemas.TournamentIn, user: models.User = Depends(security.require_admin), db: Session = Depends(get_db)):
    t = models.Tournament(
        title=data.title, starts_on=data.starts_on, ends_on=data.ends_on, groups=",".join(g.strip() for g in data.groups if g.strip()),
        auto_join=data.auto_join, prize_1=data.prize_1, prize_2=data.prize_2, prize_3=data.prize_3, created_by_id=user.id,
    )
    t.tribes = [models.Tribe(name=n, color=tribes_service.TRIBE_COLORS[i % len(tribes_service.TRIBE_COLORS)])
                for i, n in enumerate(data.tribe_names)]
    db.add(t)
    db.commit()
    return view(db, _load(db, t.id), user)


def _claim(db: Session, t: models.Tournament, was: str, becomes: str) -> bool:
    """Moves the tournament to a new status only if nobody did it first (one conditional UPDATE)."""
    done = db.query(models.Tournament).filter(models.Tournament.id == t.id, models.Tournament.status == was).update(
        {models.Tournament.status: becomes}, synchronize_session=False)
    if done:
        db.refresh(t)
    return bool(done)


@router.post("/tribes/tournaments/{tournament_id}/start")
def start(tournament_id: int, user: models.User = Depends(security.require_admin), db: Session = Depends(get_db)):
    """Splits the students into the tribes at random and starts the tournament."""
    t = _load(db, tournament_id)
    if t.status != "draft":
        raise HTTPException(status_code=400, detail="Турнир уже запущен")
    if db.query(models.Tournament).filter(models.Tournament.status == "active").first():
        raise HTTPException(status_code=409, detail="Уже идёт другой турнир: сначала завершите его")
    people = tribes_service.pool(db, t)
    if len(people) < len(t.tribes):
        raise HTTPException(status_code=400, detail=f"Участников ({len(people)}) меньше, чем трайбов")
    if not _claim(db, t, "draft", "active"):
        raise HTTPException(status_code=400, detail="Турнир уже запущен")
    for tribe, team in zip(t.tribes, tribes_service.split(people, len(t.tribes))):
        tribe.members = [models.TribeMember(tournament_id=t.id, user_id=u.id) for u in team]
    t.status = "active"
    db.commit()
    tribes_service.clear_cache()
    return view(db, _load(db, t.id), user)


@router.post("/tribes/{tribe_id}/awards")
def award(tribe_id: int, data: schemas.AwardIn, user: models.User = Depends(security.require_admin), db: Session = Depends(get_db)):
    """Points for a tribe (a hackathon, a tribe challenge) or a penalty (negative)."""
    tribe = db.query(models.Tribe).filter(models.Tribe.id == tribe_id).first()
    if not tribe:
        raise HTTPException(status_code=404, detail="Трайб не найден")
    if tribe.tournament.status != "active":
        raise HTTPException(status_code=400, detail="Очки начисляются только во время турнира")
    db.add(models.TribeAward(tribe_id=tribe.id, points=data.points, reason=data.reason, created_by_id=user.id))
    db.commit()
    tribes_service.clear_cache()
    return view(db, _load(db, tribe.tournament_id), user)


@router.put("/tribes/tournaments/{tournament_id}/members/{user_id}")
def move(tournament_id: int, user_id: int, data: schemas.MoveIn,
         user: models.User = Depends(security.require_admin), db: Session = Depends(get_db)):
    """Moves a student to another tribe (or adds one who is not in any)."""
    t = _load(db, tournament_id)
    if t.status != "active":
        raise HTTPException(status_code=400, detail="Составы меняются только во время турнира")
    if data.tribe_id not in {tr.id for tr in t.tribes}:
        raise HTTPException(status_code=400, detail="Такого трайба в этом турнире нет")
    if not db.query(models.User).filter(models.User.id == user_id).first():
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    member = db.query(models.TribeMember).filter_by(tournament_id=t.id, user_id=user_id).first()
    if member:
        member.tribe_id = data.tribe_id
    else:
        db.add(models.TribeMember(tournament_id=t.id, tribe_id=data.tribe_id, user_id=user_id))
    db.commit()
    tribes_service.clear_cache()
    return view(db, _load(db, t.id), user)


@router.post("/tribes/tournaments/{tournament_id}/finish")
def finish(tournament_id: int, user: models.User = Depends(security.require_admin), db: Session = Depends(get_db)):
    """Fixes the standings and pays the prizes: every member of the top three tribes gets bits."""
    t = _load(db, tournament_id)
    # Claim the tournament atomically: a double click must not pay the prizes twice
    if not _claim(db, t, "active", "finished"):
        raise HTTPException(status_code=400, detail="Завершить можно только идущий турнир")
    tribes_service.clear_cache()
    table = tribes_service.standings(db, t)["tribes"]
    by_id = {tr.id: tr for tr in t.tribes}  # members loaded by _load
    prizes = [t.prize_1, t.prize_2, t.prize_3]
    place = 0
    prev = None
    for i, row in enumerate(table, start=1):
        # Equal points share a place
        place = place if prev is not None and row["points"] == prev else i
        prev = row["points"]
        tribe = by_id[row["id"]]
        tribe.final_points, tribe.place = row["points"], place
        prize = prizes[place - 1] if place <= 3 else 0
        if prize:
            for m in tribe.members:
                db.add(models.BitsGrant(user_id=m.user_id, amount=prize, tournament_id=t.id, created_by_id=user.id,
                                        reason=f"Турнир «{t.title}»: {place} место трайба «{tribe.name}»"))
    t.winner_tribe_id = table[0]["id"] if table else None
    t.status, t.finished_at = "finished", _now()
    db.commit()
    tribes_service.clear_cache()
    return view(db, _load(db, t.id), user)


@router.delete("/tribes/tournaments/{tournament_id}", status_code=200)
def delete(tournament_id: int, user: models.User = Depends(security.require_admin), db: Session = Depends(get_db)):
    t = _load(db, tournament_id)
    if t.status != "draft":
        raise HTTPException(status_code=400, detail="Удалить можно только незапущенный турнир")
    db.delete(t)
    db.commit()
    return {"ok": True}
