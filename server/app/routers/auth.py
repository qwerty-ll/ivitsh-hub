import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Response, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core import rate_limit
from app.db.database import get_db
from app.services import eios, sdo
import app.models as models
import app.schemas as schemas
import app.core.security as security

logger = logging.getLogger("ivitsh_portal.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

_LOGIN_LOOKS_LIKE_RAW_ID = re.compile(r"^\d{2}-[a-zа-я]+-\d+", re.IGNORECASE)
_INVALID_CREDENTIALS = "Неверный логин или пароль ЭИОС КГУ. Проверьте данные и попробуйте снова."
_INVALID_ADMIN_CREDENTIALS = "Неверный логин или пароль Администратора ИВИТШ"
# Edition of the consent text on /privacy#consent (client/src/pages/Privacy.jsx, EDITION): change both together
PD_CONSENT_VERSION = "2026-09-30"


def _find_user(db: Session, username: str) -> Optional[models.User]:
    return db.query(models.User).filter(func.lower(models.User.username) == username.lower()).first()


def _safe_avatar_url(url: Optional[str]) -> Optional[str]:
    """Keep only plain http(s) links: the value ends up in an <img src> on every page."""
    if not isinstance(url, str):
        return None
    url = url.strip()
    if len(url) > 1000 or not url.lower().startswith(("https://", "http://")):
        return None
    return url


def _user_response(user: models.User) -> schemas.UserResponse:
    response = schemas.UserResponse.model_validate(user)
    response.userpictureurl = user.avatar_url
    return response


def _login_response(response: Response, user: models.User) -> schemas.LoginResponse:
    security.set_auth_cookie(response, security.create_access_token(user.username))
    return schemas.LoginResponse(user=_user_response(user))


@router.post("/admin-login", response_model=schemas.LoginResponse)
def admin_login(user_in: schemas.UserLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = rate_limit.client_ip(request)
    username = user_in.username.strip()
    user_key = f"admin:{username.lower()}"
    if rate_limit.admin_login_failures_by_ip.is_limited(ip) or rate_limit.login_failures_by_user.is_limited(user_key):
        raise rate_limit.too_many_requests()

    is_env_admin = (
        bool(settings.ADMIN_USERNAME)
        and bool(settings.ADMIN_PASSWORD)
        and secrets.compare_digest(username.lower().encode(), settings.admin_username_normalized.encode())
        and secrets.compare_digest(user_in.password.encode(), settings.ADMIN_PASSWORD.encode())
    )
    db_user = _find_user(db, username)

    if is_env_admin:
        if db_user is None:
            db_user = models.User(
                username=username,
                full_name="Администратор ИВИТШ КГУ",
                group_number="Деканат ИВИТШ",
                hashed_password=security.get_password_hash(secrets.token_urlsafe(32)),
                role="admin",
                auth_source="local",
            )
            db.add(db_user)
        elif db_user.auth_source != "local" and db_user.sdo_id:
            # Never hand admin rights to an EIOS student (an account bound to an EIOS identity) who shares the admin login.
            logger.error("ADMIN_USERNAME %r collides with an EIOS account; choose another admin login", username)
            raise HTTPException(status_code=409, detail="Логин администратора совпадает с учётной записью ЭИОС. Смените ADMIN_USERNAME.")
        else:
            if db_user.auth_source != "local":
                # An account of earlier portal versions (demo data, the old registration) that EIOS never
                # confirmed: migration 0002 marked it "eios" by default. The env administrator takes it over.
                logger.warning("Admin login %r takes over an account never bound to EIOS", username)
                db_user.auth_source = "local"
                db_user.hashed_password = security.get_password_hash(secrets.token_urlsafe(32))
            db_user.role = "admin"
            db_user.is_blocked = False
        db.commit()
        db.refresh(db_user)
    elif not (
        db_user
        and db_user.auth_source == "local"
        and db_user.role in ("admin", "moderator")
        and not db_user.is_blocked
        and security.verify_password(user_in.password, db_user.hashed_password)
    ):
        rate_limit.admin_login_failures_by_ip.add(ip)
        rate_limit.login_failures_by_user.add(user_key)
        logger.warning("Admin login failed for %r from %s", username, ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_ADMIN_CREDENTIALS)

    rate_limit.login_failures_by_user.reset(user_key)
    logger.info("Admin login succeeded for %r", db_user.username)
    return _login_response(response, db_user)


@router.post("/eios-login", response_model=schemas.LoginResponse)
async def eios_login(
    req: schemas.EiosLoginRequest,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    username = req.username.strip()
    password = req.password  # passwords may legitimately start or end with spaces
    if not username or not password:
        raise HTTPException(status_code=400, detail="Логин и пароль обязательны для входа через ЭИОС КГУ")
    # 152-ФЗ: personal data is requested from EIOS and stored only after the student agreed to it
    if not req.consent:
        raise HTTPException(status_code=400, detail="Чтобы войти, отметьте согласие на обработку персональных данных.")
    consent_at = datetime.now(timezone.utc)

    ip = rate_limit.client_ip(request)
    user_key = f"eios:{username.lower()}"
    if rate_limit.login_failures_by_user.is_limited(user_key) or rate_limit.login_failures_by_ip.is_limited(ip):
        raise rate_limit.too_many_requests()

    if settings.ADMIN_USERNAME and username.lower() == settings.admin_username_normalized:
        # The local administrator account must never be reachable through EIOS.
        rate_limit.login_failures_by_user.add(user_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS)

    try:
        identity = await eios.authenticate(username, password)
    except eios.EiosVpnBlocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Сервер ЭИОС КГУ заблокировал подключение из-за включённого VPN. Пожалуйста, отключите VPN и повторите попытку.",
        )
    except eios.EiosUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервер ЭИОС КГУ недоступен. Попробуйте позже или обратитесь к администратору.",
        )

    if identity is None:
        rate_limit.login_failures_by_user.add(user_key)
        rate_limit.login_failures_by_ip.add(ip)
        logger.warning("EIOS login rejected for %r from %s", username, ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS)

    full_name = identity.full_name
    if not full_name or full_name.lower() == username.lower() or _LOGIN_LOOKS_LIKE_RAW_ID.match(full_name):
        full_name = f"Студент {username}"
    # The group EIOS reports wins over one typed at login; only the former comes with its timetable id.
    group = identity.group or (req.group_number or "").strip() or None
    group_id = identity.group_id if identity.group else None
    avatar_url = _safe_avatar_url(identity.avatar_url)

    db_user = _find_user(db, username)
    if db_user is None and identity.eios_id:
        db_user = db.query(models.User).filter(models.User.sdo_id == identity.eios_id).first()

    if db_user is not None:
        if db_user.auth_source != "eios":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS)
        if db_user.sdo_id and identity.eios_id and db_user.sdo_id != identity.eios_id:
            logger.error("EIOS id mismatch for local user %r", db_user.username)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Учётная запись портала привязана к другому пользователю ЭИОС. Обратитесь к администратору.")
        if db_user.is_blocked:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Учётная запись заблокирована администратором портала.")
        db_user.sdo_id = db_user.sdo_id or identity.eios_id
        db_user.full_name = full_name
        db_user.pd_consent_at, db_user.pd_consent_version = consent_at, PD_CONSENT_VERSION
        if group:
            db_user.group_number = group
            db_user.eios_group_id = group_id
        if avatar_url:
            db_user.avatar_url = avatar_url
        db.commit()
    else:
        db_user = models.User(
            username=username.lower(),
            full_name=full_name,
            group_number=group,
            eios_group_id=group_id,
            # EIOS users never log in with a local password; store an unusable random one.
            hashed_password=security.get_password_hash(secrets.token_urlsafe(32)),
            role="student",
            auth_source="eios",
            sdo_id=identity.eios_id,
            avatar_url=avatar_url,
            pd_consent_at=consent_at,
            pd_consent_version=PD_CONSENT_VERSION,
        )
        db.add(db_user)
        try:
            db.commit()
        except Exception:
            # Another request created the same user concurrently.
            db.rollback()
            db_user = _find_user(db, username)
            if db_user is None:
                raise HTTPException(status_code=500, detail="Ошибка создания пользователя. Попробуйте ещё раз.")
    db.refresh(db_user)

    rate_limit.login_failures_by_user.reset(user_key)
    logger.info("EIOS login succeeded for %r", db_user.username)
    # SDO shares the EIOS password: refresh the course list after the response, never delaying the sign-in
    if settings.SDO_BASE_URL:
        background.add_task(sdo.sync_courses, db_user.id, username, password)
    return _login_response(response, db_user)


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(security.require_current_user)):
    return _user_response(current_user)


@router.patch("/me", response_model=schemas.UserResponse)
def update_my_profile(
    req: schemas.UserUpdateProfile,
    current_user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db),
):
    # Full name comes from EIOS and is not user-editable, so nobody can post as "Администратор" or a teacher.
    if req.group_number is not None and req.group_number.strip():
        group = req.group_number.strip()
        if group != current_user.group_number and current_user.eios_group_id:
            raise HTTPException(status_code=400, detail="Группа подтверждена ЭИОС и обновляется при входе")
        if group != current_user.group_number:
            # The EIOS id belonged to the old group
            current_user.group_number = group
            current_user.eios_group_id = None
    for field in ("vk_url", "max_contact"):
        value = getattr(req, field)
        if value is not None:
            setattr(current_user, field, value or None)
    db.commit()
    db.refresh(current_user)
    return _user_response(current_user)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    token: Optional[str] = Depends(security.oauth2_scheme),
    db: Session = Depends(get_db),
):
    auth_token = security.extract_token(request, token)
    payload = security.decode_access_token(auth_token) if auth_token else None
    if payload:
        security.revoke_token(payload["jti"], db)
    security.clear_auth_cookie(response)
    return {"message": "Успешный выход из системы"}
