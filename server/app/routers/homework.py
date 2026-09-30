"""Homework, deadlines and notes inside an academic group: every student of the group sees and adds them.

The author edits and deletes their entry; moderators and administrators may remove any.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
import app.models as models
import app.schemas as schemas
import app.core.security as security

router = APIRouter(prefix="/api/v1", tags=["Group homework"])


def group_key(name: Optional[str]) -> str:
    """"24-ИСбо-1" and "24-исбо-1 " are the same group."""
    return "".join((name or "").lower().replace("ё", "е").split())


def _require_group(user: models.User) -> str:
    key = group_key(user.group_number)
    if not key:
        raise HTTPException(status_code=400, detail="Укажите свою группу в личном кабинете")
    return key


def _can_edit(entry: models.GroupHomework, user: models.User) -> bool:
    return entry.created_by_id == user.id or user.role in ("admin", "moderator")


def homework_item(entry: models.GroupHomework, user: models.User) -> Dict:
    return {
        "id": entry.id,
        "subject": entry.subject or "",
        "text": entry.text,
        "due_at": entry.due_at,
        "group_number": entry.group_number,
        "author": entry.created_by.full_name if entry.created_by else None,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "can_edit": _can_edit(entry, user),
    }


def _get(db: Session, entry_id: int, user: models.User) -> models.GroupHomework:
    entry = db.query(models.GroupHomework).options(joinedload(models.GroupHomework.created_by)).filter(
        models.GroupHomework.id == entry_id).first()
    # Other groups' entries are invisible, moderators included
    if not entry or entry.group_key != group_key(user.group_number):
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return entry


@router.get("/homework", response_model=List[schemas.HomeworkItem])
def list_homework(
    past: bool = Query(False, description="Entries whose deadline passed more than a day ago"),
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    key = group_key(user.group_number)
    if not key:
        return []
    since = datetime.now(timezone.utc) - timedelta(days=1)
    query = db.query(models.GroupHomework).options(joinedload(models.GroupHomework.created_by)).filter(
        models.GroupHomework.group_key == key)
    if past:
        query = query.filter(models.GroupHomework.due_at < since).order_by(models.GroupHomework.due_at.desc()).limit(50)
        return [homework_item(e, user) for e in query.all()]
    entries = query.filter(or_(models.GroupHomework.due_at.is_(None), models.GroupHomework.due_at >= since)).all()
    # Nearest deadline first, notes without one after them, newest first
    far = datetime.max.replace(tzinfo=timezone.utc)
    entries.sort(key=lambda e: (
        schemas.as_utc(e.due_at) if e.due_at else far,
        -(schemas.as_utc(e.created_at).timestamp() if e.created_at else 0),
    ))
    return [homework_item(e, user) for e in entries]


@router.post("/homework", response_model=schemas.HomeworkItem, status_code=201)
def add_homework(
    data: schemas.HomeworkIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    key = _require_group(user)
    entry = models.GroupHomework(group_key=key, group_number=user.group_number.strip(), created_by_id=user.id,
                                 **data.model_dump())
    db.add(entry)
    db.commit()
    return homework_item(_get(db, entry.id, user), user)


@router.put("/homework/{entry_id}", response_model=schemas.HomeworkItem)
def edit_homework(
    entry_id: int,
    data: schemas.HomeworkIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    entry = _get(db, entry_id, user)
    if not _can_edit(entry, user):
        raise HTTPException(status_code=403, detail="Изменить запись может только её автор")
    for field, value in data.model_dump().items():
        setattr(entry, field, value)
    entry.updated_at = datetime.now(timezone.utc)
    db.commit()
    return homework_item(_get(db, entry_id, user), user)


@router.delete("/homework/{entry_id}", status_code=200)
def delete_homework(
    entry_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    entry = _get(db, entry_id, user)
    if not _can_edit(entry, user):
        raise HTTPException(status_code=403, detail="Удалить запись может только её автор")
    db.delete(entry)
    db.commit()
    return {"ok": True}
