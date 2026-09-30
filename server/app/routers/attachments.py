"""Files and links on tasks, association announcements, events and manual achievements.

A file is uploaded as the raw request body (its name in ?name=) and is downloaded only through
GET /attachments/{id}, after the same rights check as its task or announcement: orders and
thank-you letters carry students' names.
"""
import os
from typing import Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
import app.models as models
import app.schemas as schemas
import app.core.security as security
from app.routers import achievements, events, posts, tasks
from app.services import uploads

router = APIRouter(prefix="/api/v1", tags=["Attachments"])


def _owner_rights(db: Session, a: models.Attachment, user: models.User) -> Tuple[bool, bool]:
    """(can see, can manage) for the attachment's task, announcement, event or achievement."""
    if a.event_id:
        event = events.get_visible(db, a.event_id, user)
        manage = events.can_manage(db, event, user)
        if not (manage or any(r.user_id == user.id for r in event.registrations)):
            raise HTTPException(status_code=404, detail="Файл не найден")
        return True, manage
    if a.achievement_id:
        achievements.get_own(db, a.achievement_id, user)  # 404 for anyone else
        return True, True
    if a.task_id:
        task = tasks.get_visible(db, a.task_id, user)  # 404 if hidden
        return True, tasks.can_manage(db, task, user)
    post = posts.load_post(db, a.post_id)
    if not posts.can_see_post(db, post, user):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return True, posts.can_manage_post(db, post, user)


async def _store_file(request: Request, name: str, user: models.User, db: Session, **owner) -> models.Attachment:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Файл больше {settings.MAX_UPLOAD_MB} МБ")
    stored, size, content_type = await uploads.save(request.stream(), name)
    attachment = models.Attachment(
        kind="file", title=uploads.clean_filename(name), stored_name=stored, size=size,
        content_type=content_type, uploaded_by_id=user.id, **owner,
    )
    db.add(attachment)
    try:
        db.commit()
    except Exception:
        db.rollback()
        uploads.delete([stored])
        raise
    return attachment


def _add_link(req: schemas.LinkIn, user: models.User, db: Session, **owner) -> models.Attachment:
    attachment = models.Attachment(kind="link", title=req.title.strip() or req.url, url=req.url, uploaded_by_id=user.id, **owner)
    db.add(attachment)
    db.commit()
    return attachment


def _item(a: models.Attachment, user: models.User) -> dict:
    a.uploaded_by = user
    return tasks.attachment_item(a, can_delete=True)


# --- Tasks: any assignee or manager adds material ------------------------------------------------

@router.post("/tasks/{task_id}/files", response_model=schemas.AttachmentItem, status_code=201)
async def upload_task_file(
    task_id: int,
    request: Request,
    name: str = Query(..., min_length=1, max_length=200),
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    tasks.get_visible(db, task_id, user)
    return _item(await _store_file(request, name, user, db, task_id=task_id), user)


@router.post("/tasks/{task_id}/links", response_model=schemas.AttachmentItem, status_code=201)
def add_task_link(
    task_id: int,
    req: schemas.LinkIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    tasks.get_visible(db, task_id, user)
    return _item(_add_link(req, user, db, task_id=task_id), user)


# --- Announcements: their leaders only -----------------------------------------------------------

def _managed_post(db: Session, post_id: int, user: models.User) -> models.AssociationPost:
    post = posts.load_post(db, post_id)
    if not posts.can_manage_post(db, post, user):
        raise HTTPException(status_code=403, detail="Прикреплять к объявлению может руководитель объединения")
    return post


@router.post("/associations/posts/{post_id}/files", response_model=schemas.AttachmentItem, status_code=201)
async def upload_post_file(
    post_id: int,
    request: Request,
    name: str = Query(..., min_length=1, max_length=200),
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    _managed_post(db, post_id, user)
    return _item(await _store_file(request, name, user, db, post_id=post_id), user)


@router.post("/associations/posts/{post_id}/links", response_model=schemas.AttachmentItem, status_code=201)
def add_post_link(
    post_id: int,
    req: schemas.LinkIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    _managed_post(db, post_id, user)
    return _item(_add_link(req, user, db, post_id=post_id), user)


# --- Events: organizers attach orders, exemptions and thank-you letters ---------------------------

@router.post("/events/{event_id}/files", response_model=schemas.AttachmentItem, status_code=201)
async def upload_event_file(
    event_id: int,
    request: Request,
    name: str = Query(..., min_length=1, max_length=200),
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    events.get_managed(db, event_id, user)
    return _item(await _store_file(request, name, user, db, event_id=event_id), user)


@router.post("/events/{event_id}/links", response_model=schemas.AttachmentItem, status_code=201)
def add_event_link(
    event_id: int,
    req: schemas.LinkIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    events.get_managed(db, event_id, user)
    return _item(_add_link(req, user, db, event_id=event_id), user)


# --- Manual achievements: the student's own scan -------------------------------------------------

@router.post("/achievements/{achievement_id}/files", response_model=schemas.AttachmentItem, status_code=201)
async def upload_achievement_file(
    achievement_id: int,
    request: Request,
    name: str = Query(..., min_length=1, max_length=200),
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    achievements.get_own(db, achievement_id, user)
    return _item(await _store_file(request, name, user, db, achievement_id=achievement_id), user)


# --- Download and delete -------------------------------------------------------------------------

def _get(db: Session, attachment_id: int) -> models.Attachment:
    a = db.query(models.Attachment).filter(models.Attachment.id == attachment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Файл не найден")
    return a


@router.get("/attachments/{attachment_id}")
def download(
    attachment_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    a = _get(db, attachment_id)
    _owner_rights(db, a, user)
    if a.kind != "file":
        raise HTTPException(status_code=404, detail="Это ссылка, а не файл")
    path = uploads.path_of(a.stored_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Файл не найден на сервере")
    return FileResponse(
        path,
        media_type=a.content_type or "application/octet-stream",
        filename=a.title,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/attachments/{attachment_id}", status_code=200)
def delete_attachment(
    attachment_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    a = _get(db, attachment_id)
    _, manage = _owner_rights(db, a, user)
    if not manage and a.uploaded_by_id != user.id:
        raise HTTPException(status_code=403, detail="Удалить можно только то, что прикрепили вы")
    stored = a.stored_name
    db.delete(a)
    db.commit()
    uploads.delete([stored])
    return {"message": "Удалено"}
