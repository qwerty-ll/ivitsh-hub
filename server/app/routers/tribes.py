"""Tribe tournaments: the administration starts one, the portal splits students into equal tribes at random,
tribes collect their members' points plus awards, and at the end the top tribes' members get bits.

Everyone signed in sees the standings; member lists show names only (no contacts).
"""
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
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


def _auto_join(db: Session, t: models.Tournament, user: models.User) -> None:
    """A student who appeared after the split joins the smallest tribe (while the tournament runs)."""
    if t.status != "active" or not t.auto_join or user.role != "student" or user.is_blocked:
        return
    if any(m.user_id == user.id for tribe in t.tribes for m in tribe.members):
        return
    if user.id not in {u.id for u in tribes_service.pool(db, t)}:
        return
    smallest = min(t.tribes, key=lambda tr: (len(tr.members), tr.id))
    db.add(models.TribeMember(tournament_id=t.id, tribe_id=smallest.id, user_id=user.id))
    db.commit()
    tribes_service.clear_cache()


def view(db: Session, t: models.Tournament, user: models.User) -> Dict:
    table = tribes_service.standings(db, t)
    names = {m.user_id: (m.user.full_name, m.user.group_number) for tr in t.tribes for m in tr.members}
    mine = next((tr for tr in t.tribes if any(m.user_id == user.id for m in tr.members)), None)
    is_admin = user.role == "admin"
    rows = []
    for row in table["tribes"]:
        ranked = sorted(row["contributions"].items(), key=lambda kv: -kv[1])
        # The tribe's best contributor: its master for this tournament
        master = names.get(ranked[0][0], ("", ""))[0] if ranked and ranked[0][1] > 0 else None
        top = [{"full_name": names[uid][0], "group_number": names[uid][1], "points": pts}
               for uid, pts in (ranked if is_admin or (mine and mine.id == row["id"]) else ranked[:TOP_SHOWN])[:200]
               if uid in names]
        rows.append({k: v for k, v in row.items() if k != "contributions"} | {"master": master, "top": top})
    tribe_by_id = {tr.id: tr for tr in t.tribes}
    awards = sorted((a for tr in t.tribes for a in tr.awards), key=lambda a: a.created_at or _now(), reverse=True)[:30]
    my_row = next((r for r in table["tribes"] if mine and r["id"] == mine.id), None)
    return {
        "id": t.id, "title": t.title, "status": t.status,
        "starts_on": t.starts_on.isoformat(), "ends_on": t.ends_on.isoformat(),
        "prizes": [t.prize_1, t.prize_2, t.prize_3],
        "groups": [g for g in (t.groups or "").split(",") if g],
        "auto_join": t.auto_join,
        "tribes": rows,
        "my_tribe_id": mine.id if mine else None,
        "my_points": my_row["contributions"].get(user.id, 0) if my_row else None,
        "my_rank_in_tribe": (sorted(my_row["contributions"].values(), reverse=True).index(my_row["contributions"][user.id]) + 1)
        if my_row and user.id in my_row["contributions"] else None,
        "awards": [
            {"tribe": tribe_by_id[a.tribe_id].name, "color": tribe_by_id[a.tribe_id].color,
             "points": a.points, "reason": a.reason, "created_at": a.created_at}
            for a in awards
        ],
        "computed_at": table["computed_at"],
        "can_manage": is_admin,
    }


@router.get("/tribes/current")
def current(user: models.User = Depends(security.require_current_user), db: Session = Depends(get_db)):
    t = _current(db)
    if not t:
        return {"tournament": None}
    t = _load(db, t.id)
    _auto_join(db, t, user)
    return {"tournament": view(db, _load(db, t.id), user)}


@router.get("/tribes/tournaments")
def tournaments(user: models.User = Depends(security.require_current_user), db: Session = Depends(get_db)):
    rows = db.query(models.Tournament).options(selectinload(models.Tournament.tribes).selectinload(models.Tribe.members)).order_by(
        models.Tournament.starts_on.desc()).all()
    if user.role != "admin":
        rows = [t for t in rows if t.status != "draft"]
    out = []
    for t in rows:
        winner = next((tr for tr in t.tribes if tr.id == t.winner_tribe_id), None)
        out.append({
            "id": t.id, "title": t.title, "status": t.status, "starts_on": t.starts_on.isoformat(), "ends_on": t.ends_on.isoformat(),
            "tribes": len(t.tribes), "members": sum(len(tr.members) for tr in t.tribes),
            "winner": {"name": winner.name, "color": winner.color, "points": winner.final_points} if winner else None,
        })
    return out


@router.get("/tribes/tournaments/{tournament_id}")
def tournament(tournament_id: int, user: models.User = Depends(security.require_current_user), db: Session = Depends(get_db)):
    t = _load(db, tournament_id)
    if t.status == "draft" and user.role != "admin":
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
    by_id = {tr.id: tr for tr in t.tribes}
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
