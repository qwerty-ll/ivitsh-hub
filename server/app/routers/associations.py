"""Student associations: the catalog, applications and their moderation, leaders.

Rights: anyone reads the catalog; signed-in users see leaders' contacts and apply;
an association's leaders and the administrators manage its members.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
import app.models as models
import app.schemas as schemas
import app.core.security as security
from app.services import uploads

router = APIRouter(prefix="/api/v1", tags=["Associations"])


# Stored file names on the tasks / posts matching a filter: collected before the rows are deleted
# so the files can be removed from disk afterwards
def task_files(db: Session, task_filter) -> List[str]:
    rows = (
        db.query(models.Attachment.stored_name)
        .join(models.Task, models.Attachment.task_id == models.Task.id)
        .filter(task_filter, models.Attachment.stored_name.isnot(None))
        .all()
    )
    return [name for (name,) in rows]


def post_files(db: Session, post_filter) -> List[str]:
    rows = (
        db.query(models.Attachment.stored_name)
        .join(models.AssociationPost, models.Attachment.post_id == models.AssociationPost.id)
        .filter(post_filter, models.Attachment.stored_name.isnot(None))
        .all()
    )
    return [name for (name,) in rows]


def catalog_order(association: models.Association):
    """Russian names first, then Latin ones ("IT профессионал", "Nexthub"), each alphabetically."""
    name = association.name.casefold()
    return (not ("а" <= name[:1] <= "я" or name[:1] == "ё"), name.replace("ё", "е"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_admin(user: Optional[models.User]) -> bool:
    return bool(user) and user.role == "admin"


def _get_association(db: Session, association_id: int, *, include_inactive: bool = False) -> models.Association:
    association = db.query(models.Association).filter(models.Association.id == association_id).first()
    if not association or (not association.is_active and not include_inactive):
        raise HTTPException(status_code=404, detail="Объединение не найдено")
    return association


def _membership(db: Session, user_id: int, association_id: int) -> Optional[models.Membership]:
    return (
        db.query(models.Membership)
        .filter(models.Membership.user_id == user_id, models.Membership.association_id == association_id)
        .first()
    )


def is_leader(db: Session, user: Optional[models.User], association_id: int) -> bool:
    if not user:
        return False
    m = _membership(db, user.id, association_id)
    return bool(m) and m.role == "leader" and m.status == "approved"


def require_manager(association_id: int, user: models.User, db: Session) -> models.Association:
    """The association's leader or an administrator; everyone else gets 403."""
    association = _get_association(db, association_id, include_inactive=_is_admin(user))
    if not (_is_admin(user) or is_leader(db, user, association_id)):
        raise HTTPException(status_code=403, detail="Управлять объединением могут его руководители и администраторы")
    return association


def _person(user: models.User, with_contacts: bool) -> Dict:
    return {
        "user_id": user.id,
        "full_name": user.full_name,
        "group_number": user.group_number,
        "vk_url": user.vk_url if with_contacts else None,
        "max_contact": user.max_contact if with_contacts else None,
    }


def _item(association: models.Association, viewer: Optional[models.User]) -> Dict:
    approved = [m for m in association.memberships if m.status == "approved"]
    leaders = sorted((m.user for m in approved if m.role == "leader"), key=lambda u: u.full_name)
    mine = next((m for m in association.memberships if viewer and m.user_id == viewer.id), None)
    return {
        "id": association.id,
        "name": association.name,
        "description": association.description or "",
        "contacts": association.contacts,
        # Leaders' contacts are for signed-in students only, never for the open web
        "leaders": [_person(u, with_contacts=viewer is not None) for u in leaders],
        # Until the leader signs in, the name from the institute's list (no contacts)
        "listed_leader": None if leaders else association.leader_hint,
        "member_count": len(approved),
        "my_role": mine.role if mine else None,
        "my_status": mine.status if mine else None,
    }


def _member_item(m: models.Membership) -> Dict:
    return {
        **_person(m.user, with_contacts=True),
        "role": m.role,
        "status": m.status,
        "message": m.message,
        "created_at": m.created_at,
        "decided_at": m.decided_at,
    }


def _with_memberships(query):
    return query.options(joinedload(models.Association.memberships).joinedload(models.Membership.user))


# --- Catalog -------------------------------------------------------------------------------------

@router.get("/associations", response_model=List[schemas.AssociationItem])
def list_associations(
    viewer: Optional[models.User] = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    associations = (
        _with_memberships(db.query(models.Association))
        .filter(models.Association.is_active.is_(True))
        .all()
    )
    return [_item(a, viewer) for a in sorted(associations, key=catalog_order)]


@router.get("/associations/mine", response_model=List[schemas.MyMembership])
def my_memberships(
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.Membership)
        .options(joinedload(models.Membership.association))
        .join(models.Association)
        .filter(models.Membership.user_id == user.id, models.Association.is_active.is_(True))
        .order_by(models.Association.name)
        .all()
    )
    return [
        {
            "association_id": m.association_id,
            "association_name": m.association.name,
            "role": m.role,
            "status": m.status,
            "created_at": m.created_at,
        }
        for m in rows
    ]


@router.get("/associations/{association_id}", response_model=schemas.AssociationDetail)
def get_association(
    association_id: int,
    viewer: Optional[models.User] = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    association = (
        _with_memberships(db.query(models.Association))
        .filter(models.Association.id == association_id)
        .first()
    )
    if not association or (not association.is_active and not _is_admin(viewer)):
        raise HTTPException(status_code=404, detail="Объединение не найдено")
    detail = _item(association, viewer)
    can_manage = _is_admin(viewer) or is_leader(db, viewer, association_id)
    detail["can_manage"] = can_manage
    if can_manage:
        by_name = sorted(association.memberships, key=lambda m: m.user.full_name)
        # Leaders first, then members by name
        detail["members"] = [_member_item(m) for m in sorted(
            (m for m in by_name if m.status == "approved"), key=lambda m: m.role != "leader")]
        detail["applications"] = [_member_item(m) for m in sorted(
            (m for m in association.memberships if m.status == "pending"), key=lambda m: m.created_at or _now())]
    return detail


# --- A student's side ----------------------------------------------------------------------------

@router.post("/associations/{association_id}/apply", response_model=schemas.MyMembership)
def apply(
    association_id: int,
    req: schemas.AssociationApply,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    association = _get_association(db, association_id)
    m = _membership(db, user.id, association_id)
    if m and m.status == "approved":
        raise HTTPException(status_code=400, detail="Вы уже участник этого объединения")
    if m and m.status == "pending":
        raise HTTPException(status_code=400, detail="Заявка уже отправлена и ждёт решения руководителя")
    if m:
        # Applying again after a refusal or after leaving
        m.status, m.role, m.message, m.created_at, m.decided_at = "pending", "member", req.message, _now(), None
    else:
        m = models.Membership(user_id=user.id, association_id=association_id, message=req.message)
        db.add(m)
    db.commit()
    return {
        "association_id": association.id,
        "association_name": association.name,
        "role": m.role,
        "status": m.status,
        "created_at": m.created_at,
    }


@router.delete("/associations/{association_id}/membership", status_code=200)
def leave(
    association_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    """Withdraws a pending application or leaves the association."""
    _get_association(db, association_id)
    m = _membership(db, user.id, association_id)
    if not m or m.status not in ("pending", "approved"):
        raise HTTPException(status_code=400, detail="Вы не состоите в этом объединении")
    if m.role == "leader":
        raise HTTPException(status_code=400, detail="Руководителя снимает администратор портала")
    if m.status == "pending":
        db.delete(m)
    else:
        m.status, m.decided_at = "left", _now()
    db.commit()
    return {"message": "Готово"}


# --- Leaders and administrators ------------------------------------------------------------------

@router.put("/associations/{association_id}", response_model=schemas.AssociationDetail)
def edit_association(
    association_id: int,
    req: schemas.AssociationLeaderEdit,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    """Leaders keep the description and contacts up to date; the name is the administrators' call."""
    association = require_manager(association_id, user, db)
    association.description = req.description.strip()
    association.contacts = (req.contacts or "").strip() or None
    db.commit()
    return get_association(association_id, user, db)


@router.post("/associations/{association_id}/members/{user_id}/decision", response_model=schemas.MemberItem)
def decide(
    association_id: int,
    user_id: int,
    req: schemas.MembershipDecision,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    require_manager(association_id, user, db)
    m = _membership(db, user_id, association_id)
    if not m or m.status != "pending":
        raise HTTPException(status_code=404, detail="Заявка не найдена или уже рассмотрена")
    m.status, m.decided_at = ("approved" if req.approve else "rejected"), _now()
    db.commit()
    return _member_item(m)


@router.delete("/associations/{association_id}/members/{user_id}", status_code=200)
def remove_member(
    association_id: int,
    user_id: int,
    user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    require_manager(association_id, user, db)
    m = _membership(db, user_id, association_id)
    if not m or m.status != "approved":
        raise HTTPException(status_code=404, detail="Участник не найден")
    if m.role == "leader":
        raise HTTPException(status_code=400, detail="Руководителя снимает администратор портала")
    m.status, m.decided_at = "left", _now()
    db.commit()
    return {"message": "Участник исключён"}


# --- Administrators ------------------------------------------------------------------------------

def _hint_matches(db: Session, hint: Optional[str], taken: set) -> List[models.User]:
    """Users whose full name starts with the listed "Фамилия Имя" (EIOS adds the patronymic)."""
    words = (hint or "").split()
    if len(words) < 2:
        return []
    fold = lambda text: text.lower().replace("ё", "е")  # noqa: E731 — the list and EIOS differ in ё
    prefix = fold(f"{words[0]} {words[1]}")
    # SQLite lower() and LIKE only fold ASCII: narrow by the start of the surname, compare in Python
    stem = words[0].capitalize()[:3]
    candidates = (
        db.query(models.User)
        .filter(models.User.full_name.like(f"{stem}%"), models.User.is_blocked.is_(False))
        .limit(200)
        .all()
    )
    return [u for u in candidates if fold(u.full_name).startswith(prefix) and u.id not in taken][:5]


def _admin_item(db: Session, association: models.Association) -> Dict:
    approved = [m for m in association.memberships if m.status == "approved"]
    leaders = [m.user for m in approved if m.role == "leader"]
    brief = lambda u: {"id": u.id, "full_name": u.full_name, "group_number": u.group_number}  # noqa: E731
    return {
        "id": association.id,
        "name": association.name,
        "description": association.description or "",
        "contacts": association.contacts,
        "leader_hint": association.leader_hint,
        "is_active": association.is_active,
        "leaders": [brief(u) for u in sorted(leaders, key=lambda u: u.full_name)],
        "member_count": len(approved),
        "pending_count": sum(1 for m in association.memberships if m.status == "pending"),
        "hint_matches": [brief(u) for u in _hint_matches(db, association.leader_hint, {u.id for u in leaders})],
    }


def _check_unique_name(db: Session, name: str, own_id: Optional[int] = None) -> None:
    for other in db.query(models.Association).all():
        if other.id != own_id and other.name.lower() == name.lower():
            raise HTTPException(status_code=400, detail="Объединение с таким названием уже есть")


@router.get("/admin/associations", response_model=List[schemas.AssociationAdminItem])
def admin_list(
    _: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db),
):
    associations = _with_memberships(db.query(models.Association)).all()
    return [_admin_item(db, a) for a in sorted(associations, key=catalog_order)]


@router.post("/admin/associations", response_model=schemas.AssociationAdminItem, status_code=201)
def admin_create(
    req: schemas.AssociationAdminIn,
    _: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db),
):
    _check_unique_name(db, req.name)
    association = models.Association(
        name=req.name,
        description=req.description.strip(),
        contacts=(req.contacts or "").strip() or None,
        leader_hint=(req.leader_hint or "").strip() or None,
        is_active=req.is_active,
    )
    db.add(association)
    db.commit()
    db.refresh(association)
    return _admin_item(db, association)


@router.put("/admin/associations/{association_id}", response_model=schemas.AssociationAdminItem)
def admin_update(
    association_id: int,
    req: schemas.AssociationAdminIn,
    _: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db),
):
    association = _get_association(db, association_id, include_inactive=True)
    _check_unique_name(db, req.name, own_id=association_id)
    association.name = req.name
    association.description = req.description.strip()
    association.contacts = (req.contacts or "").strip() or None
    association.leader_hint = (req.leader_hint or "").strip() or None
    association.is_active = req.is_active
    db.commit()
    return _admin_item(db, association)


@router.delete("/admin/associations/{association_id}", status_code=200)
def admin_delete(
    association_id: int,
    _: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db),
):
    """Deletes the association with its members, tasks and posts; hiding it (is_active) keeps the history."""
    association = _get_association(db, association_id, include_inactive=True)
    files = (task_files(db, models.Task.association_id == association_id)
             + post_files(db, models.AssociationPost.association_id == association_id))
    db.delete(association)
    db.commit()
    uploads.delete(files)
    return {"message": "Объединение удалено"}


@router.put("/admin/associations/{association_id}/leaders/{user_id}", response_model=schemas.AssociationAdminItem)
def admin_add_leader(
    association_id: int,
    user_id: int,
    _: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db),
):
    association = _get_association(db, association_id, include_inactive=True)
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    m = _membership(db, user_id, association_id)
    if not m:
        m = models.Membership(user_id=user_id, association_id=association_id)
        db.add(m)
    m.role, m.status, m.decided_at = "leader", "approved", _now()
    db.commit()
    db.refresh(association)
    return _admin_item(db, association)


@router.delete("/admin/associations/{association_id}/leaders/{user_id}", response_model=schemas.AssociationAdminItem)
def admin_remove_leader(
    association_id: int,
    user_id: int,
    _: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db),
):
    """The former leader stays in the association as a member."""
    association = _get_association(db, association_id, include_inactive=True)
    m = _membership(db, user_id, association_id)
    if not m or m.role != "leader":
        raise HTTPException(status_code=404, detail="Этот пользователь не руководит объединением")
    m.role = "member"
    db.commit()
    db.refresh(association)
    return _admin_item(db, association)
