"""Coworking room 108 ("8 бит") and laptops.

The room is booked by parts: "top", "bottom" or "whole"; the whole room collides with either part.
Laptops: at no moment may more than LAPTOPS_TOTAL be booked at once. A booking is confirmed at once;
its author or an administrator may cancel it. Association leaders and administrators book;
every signed-in user sees what is taken.
"""
import threading
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.database import get_db
import app.models as models
import app.schemas as schemas
import app.core.security as security
from app.routers.associations import is_leader
from app.services import timetable

router = APIRouter(prefix="/api/v1", tags=["Booking"])

ZONE_TEXT = {"top": "верх", "bottom": "низ", "whole": "всё помещение"}
MIN_MINUTES = 15
MAX_DAYS_AHEAD = 90
# The check and the insert must not interleave: one lock per process (the portal runs one),
# plus a transaction-level advisory lock on PostgreSQL
_lock = threading.Lock()
_PG_LOCK_KEY = 108108


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def _msk(dt: datetime) -> datetime:
    return schemas.as_utc(dt).astimezone(timetable.MSK)


def _is_admin(user: models.User) -> bool:
    return user.role == "admin"


def _led(db: Session, user: models.User) -> List[int]:
    return [
        aid for (aid,) in db.query(models.Membership.association_id).join(models.Association).filter(
            models.Membership.user_id == user.id, models.Membership.role == "leader",
            models.Membership.status == "approved", models.Association.is_active.is_(True))
    ]


def can_book(db: Session, user: models.User) -> bool:
    return _is_admin(user) or bool(_led(db, user))


def item(b: models.Booking, user: models.User) -> Dict:
    return {
        "id": b.id, "resource": b.resource, "zone": b.zone, "laptops": b.laptops,
        "starts_at": b.starts_at, "ends_at": b.ends_at, "purpose": b.purpose or "",
        "association": {"id": b.association.id, "name": b.association.name} if b.association else None,
        "booked_by": b.booked_by.full_name if b.booked_by else None,
        "cancelled_at": b.cancelled_at,
        "cancelled_by": b.cancelled_by.full_name if b.cancelled_by else None,
        "cancel_reason": b.cancel_reason,
        "mine": b.booked_by_id == user.id,
        "can_cancel": b.cancelled_at is None and schemas.as_utc(b.ends_at) > _now()
        and (_is_admin(user) or b.booked_by_id == user.id),
    }


def _active_overlapping(db: Session, resource: str, starts: datetime, ends: datetime) -> List[models.Booking]:
    return (
        db.query(models.Booking)
        .options(joinedload(models.Booking.association))
        .filter(models.Booking.resource == resource, models.Booking.cancelled_at.is_(None),
                models.Booking.starts_at < ends, models.Booking.ends_at > starts)
        .all()
    )


def _who(b: models.Booking) -> str:
    return f" ({b.association.name})" if b.association else ""


def _check_room(db: Session, zone: str, starts: datetime, ends: datetime) -> None:
    for b in _active_overlapping(db, "room", starts, ends):
        if zone == "whole" or b.zone == "whole" or b.zone == zone:
            raise HTTPException(
                status_code=409,
                detail=f"Занято: {ZONE_TEXT[b.zone]} с {_msk(b.starts_at):%H:%M} до {_msk(b.ends_at):%H:%M}{_who(b)}",
            )


def laptops_in_use(bookings: List[models.Booking], starts: datetime, ends: datetime) -> int:
    """The most laptops taken at any moment of [starts, ends)."""
    moments = sorted({starts} | {schemas.as_utc(b.starts_at) for b in bookings if starts <= schemas.as_utc(b.starts_at) < ends})
    return max(
        (sum(b.laptops or 0 for b in bookings if schemas.as_utc(b.starts_at) <= m < schemas.as_utc(b.ends_at)) for m in moments),
        default=0,
    )


def _check_laptops(db: Session, count: int, starts: datetime, ends: datetime) -> None:
    taken = laptops_in_use(_active_overlapping(db, "laptops", starts, ends), starts, ends)
    free = settings.LAPTOPS_TOTAL - taken
    if count > free:
        raise HTTPException(
            status_code=409,
            detail=f"В это время свободно ноутбуков: {max(free, 0)} из {settings.LAPTOPS_TOTAL}",
        )


def _check_time(starts: datetime, ends: datetime) -> None:
    s, e = _msk(starts), _msk(ends)
    if s.date() != e.date():
        raise HTTPException(status_code=400, detail="Бронь должна начинаться и заканчиваться в один день")
    if s.time() < _hm(settings.BOOKING_OPEN) or e.time() > _hm(settings.BOOKING_CLOSE) or e.time() == time(0):
        raise HTTPException(status_code=400, detail=f"Коворкинг работает с {settings.BOOKING_OPEN} до {settings.BOOKING_CLOSE}")
    if s.minute % 5 or e.minute % 5 or s.second or e.second:
        raise HTTPException(status_code=400, detail="Время брони — с шагом 5 минут")
    if (ends - starts) < timedelta(minutes=MIN_MINUTES):
        raise HTTPException(status_code=400, detail=f"Бронь — не меньше {MIN_MINUTES} минут")
    if ends <= _now():
        raise HTTPException(status_code=400, detail="Это время уже прошло")
    if starts > _now() + timedelta(days=MAX_DAYS_AHEAD):
        raise HTTPException(status_code=400, detail=f"Бронировать можно не больше чем на {MAX_DAYS_AHEAD} дней вперёд")


def _load(db: Session, booking_id: int) -> models.Booking:
    b = (
        db.query(models.Booking)
        .options(joinedload(models.Booking.association), joinedload(models.Booking.booked_by), joinedload(models.Booking.cancelled_by))
        .filter(models.Booking.id == booking_id)
        .first()
    )
    if not b:
        raise HTTPException(status_code=404, detail="Бронь не найдена")
    return b


@router.get("/bookings", response_model=schemas.BookingDay)
def list_bookings(
    day: date = Query(..., description="YYYY-MM-DD, Moscow time"),
    days: int = Query(1, ge=1, le=14),
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    since = datetime.combine(day, time(0), tzinfo=timetable.MSK)
    until = since + timedelta(days=days)
    rows = (
        db.query(models.Booking)
        .options(joinedload(models.Booking.association), joinedload(models.Booking.booked_by))
        .filter(models.Booking.cancelled_at.is_(None), models.Booking.starts_at < until, models.Booking.ends_at > since)
        .order_by(models.Booking.starts_at)
        .all()
    )
    return {
        "open": settings.BOOKING_OPEN, "close": settings.BOOKING_CLOSE, "laptops_total": settings.LAPTOPS_TOTAL,
        "can_book": can_book(db, user), "items": [item(b, user) for b in rows],
    }


@router.get("/bookings/mine", response_model=List[schemas.BookingItem])
def my_bookings(
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    """Upcoming bookings I made, cancelled ones included (with the reason), and the last week's."""
    rows = (
        db.query(models.Booking)
        .options(joinedload(models.Booking.association), joinedload(models.Booking.booked_by), joinedload(models.Booking.cancelled_by))
        .filter(models.Booking.booked_by_id == user.id, models.Booking.ends_at > _now() - timedelta(days=7))
        .order_by(models.Booking.starts_at)
        .all()
    )
    return [item(b, user) for b in rows]


@router.post("/bookings", response_model=schemas.BookingItem, status_code=201)
def create_booking(
    data: schemas.BookingIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    if not can_book(db, user):
        raise HTTPException(status_code=403, detail="Бронировать могут руководители объединений и администрация")
    if data.association_id is None and not _is_admin(user):
        raise HTTPException(status_code=400, detail="Выберите объединение, для которого бронь")
    if data.association_id is not None and not _is_admin(user) and not is_leader(db, user, data.association_id):
        raise HTTPException(status_code=403, detail="Бронировать можно только для объединения, которым вы руководите")
    if data.resource == "laptops" and data.laptops > settings.LAPTOPS_TOTAL:
        raise HTTPException(status_code=400, detail=f"Всего ноутбуков: {settings.LAPTOPS_TOTAL}")
    _check_time(data.starts_at, data.ends_at)

    with _lock:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _PG_LOCK_KEY})
        if data.resource == "room":
            _check_room(db, data.zone, data.starts_at, data.ends_at)
        else:
            _check_laptops(db, data.laptops, data.starts_at, data.ends_at)
        booking = models.Booking(
            resource=data.resource,
            zone=data.zone if data.resource == "room" else None,
            laptops=data.laptops if data.resource == "laptops" else None,
            starts_at=data.starts_at, ends_at=data.ends_at, purpose=data.purpose,
            association_id=data.association_id, booked_by_id=user.id,
        )
        db.add(booking)
        db.commit()
    return item(_load(db, booking.id), user)


@router.post("/bookings/{booking_id}/cancel", response_model=schemas.BookingItem)
def cancel_booking(
    booking_id: int,
    data: schemas.CancelIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    b = _load(db, booking_id)
    if not (_is_admin(user) or b.booked_by_id == user.id):
        raise HTTPException(status_code=403, detail="Отменить чужую бронь может только администрация")
    if b.cancelled_at is None and schemas.as_utc(b.ends_at) <= _now():
        raise HTTPException(status_code=400, detail="Бронь уже закончилась")
    if b.cancelled_at is None:
        b.cancelled_at, b.cancelled_by_id = _now(), user.id
        b.cancel_reason = data.reason.strip() or None
        db.commit()
    return item(_load(db, booking_id), user)
