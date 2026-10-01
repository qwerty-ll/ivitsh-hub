"""People's photos for everyone signed in: shown next to names on the forum, in member lists, tasks, tribes."""
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
import app.models as models
import app.core.security as security
from app.services import uploads

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


@router.get("/{user_id}/photo")
def photo(
    user_id: int,
    viewer: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    """The photo a person uploaded: to its owner always, to other signed-in users unless hidden.
    Guests never get it (personal data)."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    visible = user is not None and user.photo_name and (user.id == viewer.id or user.photo_url is not None)
    if not visible:
        raise HTTPException(status_code=404, detail="Фото не найдено")
    path = uploads.path_of(user.photo_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Фото не найдено")
    # The address carries the version (?v=): a new photo is a new address, so caching is safe
    return FileResponse(path, headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})
