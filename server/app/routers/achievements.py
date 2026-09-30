"""The ПГАС summary: events the student took part in on the portal plus ones added by hand (with a scan),
for a semester, on screen or as an Excel / Word file. Only the student sees their own summary."""
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.database import get_db
import app.models as models
import app.schemas as schemas
import app.core.security as security
from app.routers.tasks import attachment_item
from app.services import pgas, progress, timetable, uploads

router = APIRouter(prefix="/api/v1", tags=["Achievements"])

ROLE_TEXT = {"participant": "Участник", "volunteer": "Волонтёр"}


def _item(a: models.ManualAchievement) -> Dict:
    return {
        "id": a.id, "title": a.title, "organizer": a.organizer or "", "day": a.day, "role": a.role or "",
        "description": a.description or "",
        "attachments": [attachment_item(x, True) for x in a.attachments],
    }


def get_own(db: Session, achievement_id: int, user: models.User) -> models.ManualAchievement:
    a = (
        db.query(models.ManualAchievement)
        .options(selectinload(models.ManualAchievement.attachments).joinedload(models.Attachment.uploaded_by))
        .filter(models.ManualAchievement.id == achievement_id)
        .first()
    )
    if not a or a.user_id != user.id:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return a


@router.get("/achievements", response_model=List[schemas.AchievementItem])
def list_achievements(user: models.User = Depends(security.require_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(models.ManualAchievement)
        .options(selectinload(models.ManualAchievement.attachments).joinedload(models.Attachment.uploaded_by))
        .filter(models.ManualAchievement.user_id == user.id)
        .order_by(models.ManualAchievement.day.desc())
        .all()
    )
    return [_item(a) for a in rows]


@router.post("/achievements", response_model=schemas.AchievementItem, status_code=201)
def add_achievement(
    data: schemas.AchievementIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    a = models.ManualAchievement(user_id=user.id, **data.model_dump())
    db.add(a)
    db.commit()
    return _item(get_own(db, a.id, user))


@router.put("/achievements/{achievement_id}", response_model=schemas.AchievementItem)
def edit_achievement(
    achievement_id: int,
    data: schemas.AchievementIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    a = get_own(db, achievement_id, user)
    for field, value in data.model_dump().items():
        setattr(a, field, value)
    a.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _item(get_own(db, achievement_id, user))


@router.delete("/achievements/{achievement_id}", status_code=200)
def delete_achievement(
    achievement_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    a = get_own(db, achievement_id, user)
    files = [x.stored_name for x in a.attachments if x.stored_name]
    db.delete(a)
    db.commit()
    uploads.delete(files)
    return {"ok": True}


# --- The summary ---------------------------------------------------------------------------------

def _bounds(start: Optional[date], end: Optional[date]):
    if not start or not end:
        start, end = pgas.semester_of(timetable.msk_now().date())
    if end < start:
        raise HTTPException(status_code=400, detail="Конец периода раньше начала")
    if (end - start).days > 400:
        raise HTTPException(status_code=400, detail="Период не может быть длиннее года")
    return start, end


def portfolio_rows(db: Session, user: models.User, start: date, end: date) -> List[Dict]:
    since = datetime.combine(start, time(0), tzinfo=timetable.MSK)
    until = datetime.combine(end + timedelta(days=1), time(0), tzinfo=timetable.MSK)
    now = datetime.now(timezone.utc)
    regs = (
        db.query(models.EventRegistration)
        .join(models.Event)
        .options(
            joinedload(models.EventRegistration.event).joinedload(models.Event.association),
            joinedload(models.EventRegistration.event).selectinload(models.Event.attachments).joinedload(models.Attachment.uploaded_by),
        )
        .filter(models.EventRegistration.user_id == user.id,
                models.Event.starts_at >= since, models.Event.starts_at < until, models.Event.ends_at <= now)
        .all()
    )
    rows = []
    for r in regs:
        # Unmarked counts as present: not every organizer marks attendance
        if r.attended is False:
            continue
        e = r.event
        organizer = e.association.name if e.association else "Администрация ИВИТШ"
        rows.append({
            "kind": "event", "id": e.id,
            "day": schemas.as_utc(e.starts_at).astimezone(timetable.MSK).date(),
            "title": e.title, "organizer": organizer,
            "level": "Институт" if e.scope == "institute" else "Объединение",
            "role": ROLE_TEXT.get(r.role, r.role),
            "documents": [attachment_item(a, False) for a in e.attachments if a.kind == "file"],
        })
    manual = (
        db.query(models.ManualAchievement)
        .options(selectinload(models.ManualAchievement.attachments).joinedload(models.Attachment.uploaded_by))
        .filter(models.ManualAchievement.user_id == user.id,
                models.ManualAchievement.day >= start, models.ManualAchievement.day <= end)
        .all()
    )
    for a in manual:
        rows.append({
            "kind": "manual", "id": a.id, "day": a.day, "title": a.title,
            "organizer": a.organizer or "—", "level": "Внесено студентом", "role": a.role or "Участник",
            "documents": [attachment_item(x, True) for x in a.attachments if x.kind == "file"],
        })
    rows.sort(key=lambda r: (r["day"], r["title"]))
    return rows


@router.get("/portfolio", response_model=schemas.PortfolioOut)
def portfolio(
    start: Optional[date] = None,
    end: Optional[date] = None,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    start, end = _bounds(start, end)
    return {"start": start, "end": end, "rows": portfolio_rows(db, user, start, end)}


@router.get("/portfolio/export")
def portfolio_export(
    format: str = Query("xlsx", pattern="^(xlsx|docx)$"),
    start: Optional[date] = None,
    end: Optional[date] = None,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    start, end = _bounds(start, end)
    rows = portfolio_rows(db, user, start, end)
    if format == "xlsx":
        content, media = pgas.summary_xlsx(user.full_name, user.group_number, start, end, rows), pgas.XLSX
    else:
        content, media = pgas.summary_docx(user.full_name, user.group_number, start, end, rows, timetable.msk_now().date()), pgas.DOCX
    name = f"ПГАС {start:%d.%m.%Y}–{end:%d.%m.%Y}.{format}"
    return Response(content, media_type=media, headers={
        "Content-Disposition": f"attachment; filename=\"pgas.{format}\"; filename*=UTF-8''{quote(name)}",
        "Cache-Control": "private, no-store",
    })


@router.get("/progress")
def my_progress(
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    """My points, level and badges: only the student sees their own."""
    return progress.summary(db, user)
