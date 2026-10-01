"""The administrators' journal: who did what to which account. The caller commits."""
from typing import Optional

from sqlalchemy.orm import Session

import app.models as models

ACTION_TEXT = {
    "role": "Смена роли",
    "block": "Блокировка",
    "unblock": "Разблокировка",
    "anonymize": "Удаление (обезличивание)",
    "purge": "Полное стирание",
    "leader_add": "Назначен руководителем",
    "leader_remove": "Снят с руководства",
    "bits_grant": "Начисление бит",
}


def user_label(user: Optional[models.User]) -> Optional[str]:
    if user is None:
        return None
    return f"{user.full_name} ({user.username})"


def log(db: Session, actor: models.User, action: str, target: Optional[models.User] = None, details: str = "") -> None:
    db.add(models.AdminAction(
        actor_id=actor.id,
        actor_name=user_label(actor),
        action=action,
        target_user_id=target.id if target else None,
        target_name=user_label(target),
        details=details or None,
    ))
