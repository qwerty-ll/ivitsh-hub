"""Association announcements: a leader posts to all members or to chosen ones (a chat link, an order...)."""
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.database import get_db
import app.models as models
import app.schemas as schemas
import app.core.security as security
from app.routers.associations import _get_association, is_leader, require_manager
from app.routers.tasks import attachment_item
from app.services import uploads

router = APIRouter(prefix="/api/v1", tags=["Association posts"])


def can_manage_post(db: Session, post: models.AssociationPost, user: models.User) -> bool:
    return user.role == "admin" or is_leader(db, user, post.association_id)


def can_see_post(db: Session, post: models.AssociationPost, user: models.User) -> bool:
    if can_manage_post(db, post, user):
        return True
    member = (
        db.query(models.Membership)
        .filter(
            models.Membership.user_id == user.id,
            models.Membership.association_id == post.association_id,
            models.Membership.status == "approved",
        )
        .first()
    )
    return bool(member) and (post.to_all or any(r.user_id == user.id for r in post.recipients))


def load_post(db: Session, post_id: int) -> models.AssociationPost:
    post = (
        db.query(models.AssociationPost)
        .options(
            joinedload(models.AssociationPost.author),
            selectinload(models.AssociationPost.recipients),
            selectinload(models.AssociationPost.attachments).joinedload(models.Attachment.uploaded_by),
        )
        .filter(models.AssociationPost.id == post_id)
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Объявление не найдено")
    return post


def post_item(db: Session, post: models.AssociationPost, manage: bool, names: Dict[int, models.User]) -> Dict:
    return {
        "id": post.id,
        "title": post.title,
        "text": post.text or "",
        "to_all": post.to_all,
        "author": post.author.full_name if post.author else None,
        "created_at": post.created_at,
        "attachments": [attachment_item(a, manage) for a in post.attachments],
        "recipients": [
            {"id": r.user_id, "full_name": names[r.user_id].full_name, "group_number": names[r.user_id].group_number}
            for r in post.recipients if r.user_id in names
        ] if manage else [],
        "can_manage": manage,
    }


@router.get("/associations/{association_id}/posts", response_model=List[schemas.PostItem])
def list_posts(
    association_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    """Members see the posts meant for them; leaders see all, with the recipients."""
    _get_association(db, association_id, include_inactive=user.role == "admin")
    posts = (
        db.query(models.AssociationPost)
        .options(
            joinedload(models.AssociationPost.author),
            selectinload(models.AssociationPost.recipients),
            selectinload(models.AssociationPost.attachments).joinedload(models.Attachment.uploaded_by),
        )
        .filter(models.AssociationPost.association_id == association_id)
        .order_by(models.AssociationPost.created_at.desc())
        .all()
    )
    manage = user.role == "admin" or is_leader(db, user, association_id)
    visible = [p for p in posts if manage or can_see_post(db, p, user)]
    ids = {r.user_id for p in visible for r in p.recipients}
    names = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(ids or [-1]))}
    return [post_item(db, p, manage, names) for p in visible]


@router.post("/associations/{association_id}/posts", response_model=schemas.PostItem, status_code=201)
def create_post(
    association_id: int,
    req: schemas.PostIn,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    association = require_manager(association_id, user, db)
    members = {m.user_id for m in association.memberships if m.status == "approved"}
    recipients = [] if req.to_all else list(dict.fromkeys(req.recipient_ids))
    if not req.to_all and not recipients:
        raise HTTPException(status_code=400, detail="Выберите, кому адресовано объявление")
    if any(uid not in members for uid in recipients):
        raise HTTPException(status_code=400, detail="Объявление можно адресовать только участникам объединения")
    post = models.AssociationPost(
        association_id=association.id,
        author_id=user.id,
        title=req.title,
        text=req.text.strip(),
        to_all=req.to_all,
        recipients=[models.AssociationPostRecipient(user_id=uid) for uid in recipients],
    )
    db.add(post)
    db.commit()
    post = load_post(db, post.id)
    names = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(recipients or [-1]))}
    return post_item(db, post, True, names)


@router.delete("/associations/posts/{post_id}", status_code=200)
def delete_post(
    post_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    post = load_post(db, post_id)
    if not can_manage_post(db, post, user):
        raise HTTPException(status_code=403, detail="Удалить объявление может руководитель объединения")
    files = [a.stored_name for a in post.attachments]
    db.delete(post)
    db.commit()
    uploads.delete(files)
    return {"message": "Объявление удалено"}
