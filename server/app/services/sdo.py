"""SDO KSU (Moodle): the student's course list, fetched at sign-in with the same login and password as EIOS.

Neither the password nor the Moodle token is stored: only course ids and names are kept.
Any failure is logged and ignored, SDO must never break signing in to the portal.
"""
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import httpx

from app.core.config import settings
from app.db.database import SessionLocal
import app.models as models

logger = logging.getLogger("ivitsh_portal.sdo")

_MAX_COURSES = 200


def course_url(course_id: int) -> str:
    return f"{settings.SDO_BASE_URL}/course/view.php?id={course_id}"


def _clean_name(value) -> Optional[str]:
    if not isinstance(value, str):
        return None
    # Moodle names may carry HTML entities and markup
    value = re.sub(r"<[^>]+>", "", value).replace("&amp;", "&").replace("&quot;", '"')
    value = " ".join(value.split())
    return value[:300] or None


def parse_courses(payload) -> List[Tuple[int, str]]:
    """(id, full name) from a core_enrol_get_users_courses answer; hidden courses are left out."""
    if not isinstance(payload, list):
        return []
    courses = {}
    for item in payload[:_MAX_COURSES]:
        if not isinstance(item, dict) or item.get("hidden"):
            continue
        cid = item.get("id")
        name = _clean_name(item.get("fullname")) or _clean_name(item.get("shortname"))
        if isinstance(cid, int) and not isinstance(cid, bool) and cid > 1 and name:
            courses[cid] = name
    return sorted(courses.items(), key=lambda c: c[1].casefold())


async def _call(client: httpx.AsyncClient, token: str, function: str, **params):
    resp = await client.post(
        f"{settings.SDO_BASE_URL}/webservice/rest/server.php",
        data={"wstoken": token, "moodlewsrestformat": "json", "wsfunction": function, **params},
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("exception"):
        raise ValueError(data.get("errorcode") or "moodle exception")
    return data


async def fetch_courses(username: str, password: str) -> Optional[List[Tuple[int, str]]]:
    """The student's courses, or None when SDO is off, rejects the login or does not answer."""
    if not settings.SDO_BASE_URL:
        return None
    try:
        async with httpx.AsyncClient(verify=settings.VERIFY_SSL, timeout=8.0) as client:
            resp = await client.post(
                f"{settings.SDO_BASE_URL}/login/token.php",
                data={"username": username, "password": password, "service": settings.SDO_SERVICE},
            )
            resp.raise_for_status()
            token = resp.json().get("token")
            if not isinstance(token, str) or not token:
                logger.info("SDO gave no token for %r", username)
                return None
            info = await _call(client, token, "core_webservice_get_site_info")
            user_id = info.get("userid") if isinstance(info, dict) else None
            if not isinstance(user_id, int):
                return None
            return parse_courses(await _call(client, token, "core_enrol_get_users_courses", userid=user_id))
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        logger.warning("SDO course list unavailable: %s", exc)
        return None


async def sync_courses(user_id: int, username: str, password: str) -> None:
    """Replace the user's saved course list; run after the sign-in response has been sent."""
    courses = await fetch_courses(username, password)
    if courses is None:
        return
    db = SessionLocal()
    try:
        user = db.get(models.User, user_id)
        if user is None:
            return
        db.query(models.SdoCourse).filter(models.SdoCourse.user_id == user_id).delete()
        db.add_all(models.SdoCourse(user_id=user_id, course_id=cid, name=name) for cid, name in courses)
        user.sdo_synced_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Saving the SDO course list failed")
    finally:
        db.close()


# --- Matching courses to timetable disciplines ------------------------------------------------------

_PARENS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_NOT_WORD = re.compile(r"[^0-9a-zа-я]+")


def _key(name: str) -> str:
    """"Базы данных (2025-2026)" → "базы данных"."""
    text = _PARENS.sub(" ", name.lower().replace("ё", "е"))
    return " ".join(_NOT_WORD.sub(" ", text).split())


def match_course(discipline: str, courses: List[Tuple[int, str]]) -> Optional[Tuple[int, str]]:
    """The course of a timetable discipline: the same name, or a course name that starts with it."""
    wanted = _key(discipline)
    if len(wanted) < 3:
        return None
    keyed = [(c, _key(c[1])) for c in courses]
    exact = next((c for c, k in keyed if k == wanted), None)
    if exact:
        return exact
    # "Базы данных" → "Базы данных. Часть 1", but not "Базы" → "Базы данных"
    return next((c for c, k in keyed if k.startswith(wanted + " ") and len(wanted) >= 6), None)
