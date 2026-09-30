"""Tasks: association tasks set by leaders (one card per assignee) and personal tasks with colors.

Rights: an assignee sees the task and moves their own card up to "На проверке"; the association's
leaders and administrators manage the task and every card; a personal task belongs to its author.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.database import get_db
import app.models as models
import app.schemas as schemas
import app.core.security as security
from app.core import rate_limit
from app.routers.associations import is_leader, require_manager
from app.services import uploads

router = APIRouter(prefix="/api/v1", tags=["Tasks"])

# Handed in: the moment of reaching one of these counts for "on time / late"
_HANDED_IN = ("review", "done")
# A "Готово" card leaves the board for the archive a day after it got there
ARCHIVE_AFTER = timedelta(days=1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load(db: Session, task_id: int) -> Optional[models.Task]:
    return (
        db.query(models.Task)
        .options(
            joinedload(models.Task.association),
            joinedload(models.Task.created_by),
            selectinload(models.Task.assignees).joinedload(models.TaskAssignee.user),
            selectinload(models.Task.comments).joinedload(models.TaskComment.author),
            selectinload(models.Task.attachments).joinedload(models.Attachment.uploaded_by),
        )
        .filter(models.Task.id == task_id)
        .first()
    )


def can_manage(db: Session, task: models.Task, user: models.User) -> bool:
    if security.is_admin(user):
        return True
    if task.association_id is None:
        return task.created_by_id == user.id
    return is_leader(db, user, task.association_id)


def my_card(task: models.Task, user: models.User) -> Optional[models.TaskAssignee]:
    return next((a for a in task.assignees if a.user_id == user.id), None)


def get_visible(db: Session, task_id: int, user: models.User) -> models.Task:
    """The task if the user may see it; otherwise 404, so others cannot probe which tasks exist."""
    task = _load(db, task_id)
    if not task or not (my_card(task, user) or can_manage(db, task, user)):
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task


def get_managed(db: Session, task_id: int, user: models.User) -> models.Task:
    task = get_visible(db, task_id, user)
    if not can_manage(db, task, user):
        raise HTTPException(status_code=403, detail="Менять задачу может тот, кто её поставил, или руководитель объединения")
    return task


def _approved_members(association: models.Association) -> Dict[int, models.Membership]:
    return {m.user_id: m for m in association.memberships if m.status == "approved"}


def _ref(task: models.Task) -> Optional[Dict]:
    return {"id": task.association.id, "name": task.association.name} if task.association else None


def attachment_item(a: models.Attachment, can_delete: bool) -> Dict:
    return {
        "id": a.id,
        "kind": a.kind,
        "title": a.title,
        "url": a.url if a.kind == "link" else None,
        "size": a.size,
        "uploaded_by": a.uploaded_by.full_name if a.uploaded_by else None,
        "created_at": a.created_at,
        "can_delete": can_delete,
    }


def _assignee_item(a: models.TaskAssignee) -> Dict:
    return {
        "user_id": a.user_id,
        "full_name": a.user.full_name,
        "group_number": a.user.group_number,
        "status": a.status,
        "status_changed_at": a.status_changed_at,
        "completed_at": a.completed_at,
        "vk_url": a.user.vk_url,
        "max_contact": a.user.max_contact,
    }


def _detail(db: Session, task: models.Task, user: models.User) -> Dict:
    manage = can_manage(db, task, user)
    mine = my_card(task, user)
    assignees = sorted(task.assignees, key=lambda a: a.user.full_name) if manage else ([mine] if mine else [])
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description or "",
        "due_at": task.due_at,
        "color": task.color,
        "association": _ref(task),
        "created_by": task.created_by.full_name if task.created_by else None,
        "created_at": task.created_at,
        "can_manage": manage,
        "my_status": mine.status if mine else None,
        "assignees": [_assignee_item(a) for a in assignees],
        "comments": [
            {
                "id": c.id,
                "author_id": c.author_id,
                "author_name": c.author.full_name,
                "text": c.text,
                "created_at": c.created_at,
                "can_delete": manage or c.author_id == user.id,
            }
            for c in task.comments
        ],
        "attachments": [attachment_item(a, manage or a.uploaded_by_id == user.id) for a in task.attachments],
    }


def set_status(card: models.TaskAssignee, status: str) -> None:
    if status == card.status:
        return
    if status in _HANDED_IN and card.status not in _HANDED_IN:
        card.completed_at = _now()
    elif status not in _HANDED_IN:
        card.completed_at = None
    if status != "done":
        card.archived_at = None
    card.status, card.status_changed_at = status, _now()


# --- My board ------------------------------------------------------------------------------------

@router.get("/tasks/my", response_model=List[schemas.TaskCard])
def my_board(
    association_id: Optional[int] = Query(None, ge=1),
    personal: bool = False,
    archived: bool = Query(False, description="The archive instead of the board"),
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    # Cards "Готово" for a week go to the archive, so the board keeps only what is current
    stale = (
        db.query(models.TaskAssignee)
        .filter(models.TaskAssignee.user_id == user.id, models.TaskAssignee.status == "done",
                models.TaskAssignee.archived_at.is_(None),
                models.TaskAssignee.status_changed_at < _now() - ARCHIVE_AFTER)
        .all()
    )
    for card in stale:
        card.archived_at = _now()
    if stale:
        db.commit()
    query = (
        db.query(models.TaskAssignee)
        .join(models.Task)
        .options(
            joinedload(models.TaskAssignee.task).joinedload(models.Task.association),
            joinedload(models.TaskAssignee.task).selectinload(models.Task.comments),
            joinedload(models.TaskAssignee.task).selectinload(models.Task.attachments),
            joinedload(models.TaskAssignee.task).selectinload(models.Task.assignees),
        )
        .filter(models.TaskAssignee.user_id == user.id,
                models.TaskAssignee.archived_at.isnot(None) if archived else models.TaskAssignee.archived_at.is_(None))
    )
    if personal:
        query = query.filter(models.Task.association_id.is_(None))
    elif association_id:
        query = query.filter(models.Task.association_id == association_id)
    cards = []
    for card in query.all():
        task = card.task
        if task.association and not task.association.is_active:
            continue
        cards.append({
            "id": task.id,
            "title": task.title,
            "due_at": task.due_at,
            "color": task.color,
            "association": _ref(task),
            "my_status": card.status,
            "comments_count": len(task.comments),
            "attachments_count": len(task.attachments),
            "assignees_count": len(task.assignees),
            "archived_at": card.archived_at,
            "completed_at": card.completed_at,
        })
    if archived:
        # Most recently finished first
        cards.sort(key=lambda c: schemas.as_utc(c["archived_at"]), reverse=True)
        return cards[:300]
    # Nearest deadline first, tasks without one at the end
    far = datetime.max.replace(tzinfo=timezone.utc)
    cards.sort(key=lambda c: (schemas.as_utc(c["due_at"]) if c["due_at"] else far, c["id"]))
    return cards


@router.get("/tasks/managed", response_model=List[schemas.ManagedTask])
def managed_tasks(
    association_id: Optional[int] = Query(None, ge=1),
    archived: bool = Query(False, description="Tasks moved to the archive"),
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    """Association tasks the user runs as a leader (an administrator: of any association)."""
    query = (
        db.query(models.Task)
        .options(joinedload(models.Task.association), selectinload(models.Task.assignees))
        .filter(models.Task.association_id.isnot(None),
                models.Task.archived_at.isnot(None) if archived else models.Task.archived_at.is_(None))
    )
    if association_id:
        query = query.filter(models.Task.association_id == association_id)
    if not security.is_admin(user):
        led = [
            m.association_id for m in db.query(models.Membership).filter(
                models.Membership.user_id == user.id,
                models.Membership.role == "leader",
                models.Membership.status == "approved",
            )
        ]
        query = query.filter(models.Task.association_id.in_(led or [-1]))
    result = []
    for task in query.order_by(models.Task.created_at.desc()).all():
        counts = {s: 0 for s in models.TASK_STATUSES}
        for a in task.assignees:
            counts[a.status] = counts.get(a.status, 0) + 1
        result.append({
            "id": task.id,
            "title": task.title,
            "due_at": task.due_at,
            "association": _ref(task),
            "counts": counts,
            "total": len(task.assignees),
            "created_at": task.created_at,
            "archived_at": task.archived_at,
        })
    return result


# --- One task ------------------------------------------------------------------------------------

@router.post("/tasks", response_model=schemas.TaskDetail, status_code=201)
def create_task(
    req: schemas.TaskIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    task = models.Task(
        title=req.title,
        description=req.description.strip(),
        due_at=req.due_at,
        created_by_id=user.id,
    )
    if req.association_id is None:
        task.color = req.color or "blue"
        task.assignees = [models.TaskAssignee(user_id=user.id)]
    else:
        association = require_manager(req.association_id, user, db)
        task.association_id = association.id
        members = _approved_members(association)
        if req.to_all:
            ids = [uid for uid, m in members.items() if m.role == "member"]
        else:
            ids = list(dict.fromkeys(req.assignee_ids))
            if any(uid not in members for uid in ids):
                raise HTTPException(status_code=400, detail="Задачу можно поставить только участникам объединения")
        if not ids:
            raise HTTPException(status_code=400, detail="Выберите, кому поставить задачу: в объединении пока нет участников")
        task.assignees = [models.TaskAssignee(user_id=uid) for uid in ids]
    db.add(task)
    db.commit()
    return _detail(db, _load(db, task.id), user)


@router.get("/tasks/{task_id}", response_model=schemas.TaskDetail)
def get_task(
    task_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    return _detail(db, get_visible(db, task_id, user), user)


@router.put("/tasks/{task_id}", response_model=schemas.TaskDetail)
def edit_task(
    task_id: int,
    req: schemas.TaskEdit,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    task = get_managed(db, task_id, user)
    task.title, task.description, task.due_at = req.title, req.description.strip(), req.due_at
    if task.association_id is None:
        task.color = req.color or task.color
    elif req.add_assignee_ids:
        members = _approved_members(task.association)
        have = {a.user_id for a in task.assignees}
        for uid in dict.fromkeys(req.add_assignee_ids):
            if uid not in members:
                raise HTTPException(status_code=400, detail="Задачу можно поставить только участникам объединения")
            if uid not in have:
                task.assignees.append(models.TaskAssignee(user_id=uid))
    db.commit()
    return _detail(db, _load(db, task.id), user)


@router.delete("/tasks/{task_id}", status_code=200)
def delete_task(
    task_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    task = get_managed(db, task_id, user)
    files = [a.stored_name for a in task.attachments]
    db.delete(task)
    db.commit()
    uploads.delete(files)
    return {"message": "Задача удалена"}


@router.patch("/tasks/{task_id}/status", response_model=schemas.AssigneeItem)
def change_status(
    task_id: int,
    req: schemas.TaskStatusIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    task = get_visible(db, task_id, user)
    manage = can_manage(db, task, user)
    target_id = req.user_id or user.id
    if target_id != user.id and not manage:
        raise HTTPException(status_code=403, detail="Чужую карточку двигает только руководитель")
    card = next((a for a in task.assignees if a.user_id == target_id), None)
    if not card:
        raise HTTPException(status_code=404, detail="Этот человек не исполнитель задачи")
    if req.status == "done" and not manage:
        raise HTTPException(status_code=403, detail="«Готово» ставит руководитель после проверки. Отправьте задачу на проверку.")
    set_status(card, req.status)
    db.commit()
    return _assignee_item(card)


@router.delete("/tasks/{task_id}/assignees/{user_id}", status_code=200)
def remove_assignee(
    task_id: int,
    user_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    task = get_managed(db, task_id, user)
    card = next((a for a in task.assignees if a.user_id == user_id), None)
    if task.association_id is None or not card:
        raise HTTPException(status_code=404, detail="Этот человек не исполнитель задачи")
    if len(task.assignees) == 1:
        raise HTTPException(status_code=400, detail="Это последний исполнитель: удалите задачу целиком")
    task.assignees.remove(card)
    db.commit()
    return {"message": "Исполнитель снят с задачи"}


# --- Comments ------------------------------------------------------------------------------------

@router.patch("/tasks/{task_id}/archive", response_model=schemas.TaskCard)
def archive_my_card(
    task_id: int,
    data: schemas.ArchiveIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    """Moves my finished card off the board, or brings it back."""
    task = get_visible(db, task_id, user)
    card = my_card(task, user)
    if not card:
        raise HTTPException(status_code=404, detail="Этой задачи нет на вашей доске")
    if data.archived:
        if card.status != "done":
            raise HTTPException(status_code=400, detail="В архив уходят задачи со статусом «Готово»")
        card.archived_at = card.archived_at or _now()
    else:
        # Back on the board for another day
        card.archived_at, card.status_changed_at = None, _now()
    db.commit()
    return {
        "id": task.id, "title": task.title, "due_at": task.due_at, "color": task.color, "association": _ref(task),
        "my_status": card.status, "comments_count": len(task.comments), "attachments_count": len(task.attachments),
        "assignees_count": len(task.assignees), "archived_at": card.archived_at, "completed_at": card.completed_at,
    }


@router.patch("/tasks/{task_id}/managed-archive", status_code=200)
def archive_managed(
    task_id: int,
    data: schemas.ArchiveIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    """Leaders move a task they set out of their list (assignees keep their cards)."""
    task = get_managed(db, task_id, user)
    if task.association_id is None:
        raise HTTPException(status_code=400, detail="Личные задачи архивируются на доске")
    task.archived_at = (task.archived_at or _now()) if data.archived else None
    db.commit()
    return {"archived": task.archived_at is not None}


@router.post("/tasks/{task_id}/comments", response_model=schemas.CommentItem, status_code=201)
def add_comment(
    task_id: int,
    req: schemas.CommentIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    task = get_visible(db, task_id, user)
    rate_limit.check_posting(user)
    comment = models.TaskComment(task_id=task.id, author_id=user.id, text=req.text)
    db.add(comment)
    db.commit()
    return {
        "id": comment.id,
        "author_id": user.id,
        "author_name": user.full_name,
        "text": comment.text,
        "created_at": comment.created_at,
        "can_delete": True,
    }


@router.delete("/tasks/comments/{comment_id}", status_code=200)
def delete_comment(
    comment_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    comment = db.query(models.TaskComment).filter(models.TaskComment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Комментарий не найден")
    task = get_visible(db, comment.task_id, user)
    if comment.author_id != user.id and not can_manage(db, task, user):
        raise HTTPException(status_code=403, detail="Удалить можно только свой комментарий")
    db.delete(comment)
    db.commit()
    return {"message": "Комментарий удалён"}
