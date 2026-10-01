"""How a person appears to others: the photo next to their name."""
from typing import Optional

import app.models as models


def photo_for(viewer: Optional[models.User], person: Optional[models.User]) -> Optional[str]:
    """A person's photo for a signed-in viewer (guests see names only); one's own even if hidden from others."""
    if viewer is None or person is None:
        return None
    if person.id == viewer.id:
        return person.own_photo_url or person.avatar_url
    return person.photo_url
