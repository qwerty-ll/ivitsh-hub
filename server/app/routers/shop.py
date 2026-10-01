"""The merch shop: bits earned on the portal are spent on merch and privileges, handed out in person.

A purchase is checked and written under a lock (balance and stock must not race). An order can be cancelled
(by the buyer while it is new, by the administration until it is issued): the bits and the stock come back.
"""
import os
from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
import app.models as models
import app.schemas as schemas
import app.core.security as security
from app.core import locks
from app.services import audit, progress, uploads

router = APIRouter(prefix="/api/v1", tags=["Shop"])

LOCK_KEY = 212121
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
STATUS_TEXT = {"new": "Оформлен", "ready": "Готов к выдаче", "issued": "Выдан", "cancelled": "Отменён"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _bought(db: Session, item_id: int, user_id: int = None) -> int:
    q = db.query(func.count(models.ShopOrder.id)).filter(models.ShopOrder.item_id == item_id,
                                                       models.ShopOrder.status != "cancelled")
    if user_id is not None:
        q = q.filter(models.ShopOrder.user_id == user_id)
    return q.scalar() or 0


def item_view(db: Session, item: models.ShopItem, user: models.User) -> Dict:
    mine = _bought(db, item.id, user.id)
    return {
        "id": item.id, "title": item.title, "description": item.description or "", "kind": item.kind,
        "price": item.price, "stock": item.stock, "per_user_limit": item.per_user_limit,
        "image": f"/api/v1/shop/items/{item.id}/image?v={item.image_name[:8]}" if item.image_name else None,
        "is_active": item.is_active, "sort": item.sort,
        "mine": mine,
        "limit_reached": item.per_user_limit is not None and mine >= item.per_user_limit,
    }


def order_view(o: models.ShopOrder, with_user: bool = False) -> Dict:
    out = {
        "id": o.id, "item_id": o.item_id, "item_title": o.item_title, "price": o.price, "status": o.status,
        "status_text": STATUS_TEXT.get(o.status, o.status), "comment": o.comment,
        "created_at": schemas.as_utc(o.created_at).isoformat() if o.created_at else None,
    }
    if with_user:
        out["user"] = {"id": o.user.id, "full_name": o.user.full_name, "group_number": o.user.group_number}
    return out


@router.get("/shop")
def shop(user: models.User = Depends(security.require_current_user), db: Session = Depends(get_db)):
    items = db.query(models.ShopItem).filter(models.ShopItem.is_active.is_(True)).order_by(
        models.ShopItem.sort, models.ShopItem.price).all()
    orders = db.query(models.ShopOrder).filter(models.ShopOrder.user_id == user.id).order_by(
        models.ShopOrder.created_at.desc()).limit(50).all()
    grants = db.query(models.BitsGrant).filter(models.BitsGrant.user_id == user.id).order_by(
        models.BitsGrant.created_at.desc()).limit(20).all()
    return {
        "balance": progress.balance(db, user),
        "items": [item_view(db, i, user) for i in items],
        "orders": [order_view(o) for o in orders],
        "grants": [{"amount": g.amount, "reason": g.reason,
                    "created_at": schemas.as_utc(g.created_at).isoformat() if g.created_at else None} for g in grants],
    }


@router.get("/shop/items/{item_id}/image")
def image(item_id: int, db: Session = Depends(get_db)):
    """Merch photos are public (no personal data)."""
    item = db.query(models.ShopItem).filter(models.ShopItem.id == item_id).first()
    if not item or not item.image_name:
        raise HTTPException(status_code=404, detail="Картинки нет")
    path = uploads.path_of(item.image_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Картинки нет")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=604800", "X-Content-Type-Options": "nosniff"})


@router.post("/shop/items/{item_id}/buy")
def buy(item_id: int, user: models.User = Depends(security.require_current_user), db: Session = Depends(get_db)):
    with locks.serialized(db, LOCK_KEY):
        item = db.query(models.ShopItem).filter(models.ShopItem.id == item_id, models.ShopItem.is_active.is_(True)).first()
        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")
        if item.stock is not None and item.stock <= 0:
            raise HTTPException(status_code=409, detail="Товар закончился")
        if item.per_user_limit is not None and _bought(db, item.id, user.id) >= item.per_user_limit:
            raise HTTPException(status_code=409, detail=f"Больше {item.per_user_limit} в одни руки нельзя")
        available = progress.balance(db, user)["available"]
        if available < item.price:
            raise HTTPException(status_code=409, detail=f"Не хватает {item.price - available} бит")
        if item.stock is not None:
            item.stock -= 1
        order = models.ShopOrder(user_id=user.id, item_id=item.id, item_title=item.title, price=item.price)
        db.add(order)
        db.commit()
    return {"order": order_view(order), "balance": progress.balance(db, user)}


def _cancel(db: Session, order: models.ShopOrder, by: models.User, comment: str = "") -> None:
    order.status, order.updated_at, order.handled_by_id = "cancelled", _now(), by.id
    order.comment = comment or order.comment
    if order.item and order.item.stock is not None:
        order.item.stock += 1


@router.post("/shop/orders/{order_id}/cancel")
def cancel_mine(order_id: int, user: models.User = Depends(security.require_current_user), db: Session = Depends(get_db)):
    # Under the shop lock: a cancel racing the administration must not return the stock twice
    with locks.serialized(db, LOCK_KEY):
        order = db.query(models.ShopOrder).options(joinedload(models.ShopOrder.item)).filter(
            models.ShopOrder.id == order_id, models.ShopOrder.user_id == user.id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        if order.status != "new":
            raise HTTPException(status_code=400, detail="Заказ уже собирают — отменить его может администрация")
        _cancel(db, order, user)
        db.commit()
    return {"order": order_view(order), "balance": progress.balance(db, user)}


# --- The administration ---------------------------------------------------------------------------

@router.get("/shop/admin")
def admin_view(
    status: str = Query("open", pattern="^(open|all|new|ready|issued|cancelled)$"),
    user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db),
):
    items = db.query(models.ShopItem).order_by(models.ShopItem.sort, models.ShopItem.price).all()
    q = db.query(models.ShopOrder).options(joinedload(models.ShopOrder.user)).order_by(models.ShopOrder.created_at.desc())
    if status == "open":
        q = q.filter(models.ShopOrder.status.in_(("new", "ready")))
    elif status != "all":
        q = q.filter(models.ShopOrder.status == status)
    return {
        "items": [item_view(db, i, user) | {"sold": _bought(db, i.id)} for i in items],
        "orders": [order_view(o, with_user=True) for o in q.limit(300).all()],
    }


@router.post("/shop/items", status_code=201)
def create_item(data: schemas.ShopItemIn, user: models.User = Depends(security.require_admin), db: Session = Depends(get_db)):
    item = models.ShopItem(**data.model_dump())
    db.add(item)
    db.commit()
    return item_view(db, item, user)


@router.put("/shop/items/{item_id}")
def edit_item(item_id: int, data: schemas.ShopItemIn, user: models.User = Depends(security.require_admin), db: Session = Depends(get_db)):
    item = db.query(models.ShopItem).filter(models.ShopItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден")
    for field, value in data.model_dump().items():
        setattr(item, field, value)
    db.commit()
    return item_view(db, item, user)


@router.delete("/shop/items/{item_id}", status_code=200)
def delete_item(item_id: int, user: models.User = Depends(security.require_admin), db: Session = Depends(get_db)):
    """Deletes an item nobody bought; a bought one is hidden instead, so orders keep their history."""
    item = db.query(models.ShopItem).filter(models.ShopItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден")
    if db.query(models.ShopOrder).filter(models.ShopOrder.item_id == item.id).first():
        item.is_active = False
        db.commit()
        return {"hidden": True}
    stored = item.image_name
    db.delete(item)
    db.commit()
    if stored:
        uploads.delete([stored])
    return {"deleted": True}


@router.post("/shop/items/{item_id}/image")
async def upload_image(
    item_id: int,
    request: Request,
    name: str = Query(..., min_length=1, max_length=200),
    user: models.User = Depends(security.require_admin),
    db: Session = Depends(get_db),
):
    item = db.query(models.ShopItem).filter(models.ShopItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден")
    if not name.lower().endswith(IMAGE_EXT):
        raise HTTPException(status_code=415, detail="Нужна картинка: PNG, JPG или WebP")
    uploads.check_declared_size(request)
    stored, _, _ = await uploads.save(request.stream(), name)
    old, item.image_name = item.image_name, stored
    db.commit()
    if old:
        uploads.delete([old])
    return item_view(db, item, user)


@router.patch("/shop/orders/{order_id}")
def set_order_status(order_id: int, data: schemas.OrderStatusIn,
                     user: models.User = Depends(security.require_admin), db: Session = Depends(get_db)):
    with locks.serialized(db, LOCK_KEY):
        order = db.query(models.ShopOrder).options(joinedload(models.ShopOrder.item), joinedload(models.ShopOrder.user)).filter(
            models.ShopOrder.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        if order.status in ("issued", "cancelled"):
            raise HTTPException(status_code=400, detail="Заказ уже закрыт")
        if data.status == "cancelled":
            _cancel(db, order, user, data.comment.strip())
        else:
            order.status, order.updated_at, order.handled_by_id = data.status, _now(), user.id
            if data.comment.strip():
                order.comment = data.comment.strip()
        db.commit()
    return order_view(order, with_user=True)


@router.post("/bits/grants", status_code=201)
def grant(data: schemas.GrantIn, user: models.User = Depends(security.require_admin), db: Session = Depends(get_db)):
    """Bits by hand: a prize for a contest outside the portal, or a correction."""
    target = db.query(models.User).filter(models.User.id == data.user_id, models.User.auth_source != "deleted").first()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if target.id == user.id:
        raise HTTPException(status_code=403, detail="Начислить биты себе нельзя: попросите другого администратора")
    db.add(models.BitsGrant(user_id=target.id, amount=data.amount, reason=data.reason, created_by_id=user.id))
    audit.log(db, user, "bits_grant", target, f"{data.amount:+d}: {data.reason}")
    db.commit()
    return {"balance": progress.balance(db, target)}
