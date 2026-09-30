import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
import app.models as models

AUTH_COOKIE_NAME = "portal_token"
# Header the SPA sends on every request; cross-site pages cannot set it without a CORS preflight.
CSRF_HEADER_NAME = "X-Requested-With"
CSRF_HEADER_VALUE = "XMLHttpRequest"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/admin-login", auto_error=False)

# users.last_seen_at is written at most this often per user
LAST_SEEN_EVERY = timedelta(minutes=10)


def _bcrypt_input(password: str) -> bytes:
    # bcrypt only uses the first 72 bytes and bcrypt>=5 rejects longer input.
    return (password or "").encode("utf-8")[:72]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password or not hashed_password.startswith("$2"):
        return False
    try:
        return bcrypt.checkpw(_bcrypt_input(plain_password), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_input(password), bcrypt.gensalt()).decode("utf-8")


def create_access_token(subject: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "sub", "jti"]},
        )
    except jwt.PyJWTError:
        return None


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/",
    )


def revoke_token(jti: str, db: Session) -> None:
    """Store the JTI so the token is rejected until it expires, and drop entries that already expired."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    try:
        db.query(models.RevokedToken).filter(models.RevokedToken.revoked_at < cutoff).delete(synchronize_session=False)
        if not db.query(models.RevokedToken).filter(models.RevokedToken.jti == jti).first():
            db.add(models.RevokedToken(jti=jti))
        db.commit()
    except Exception:
        db.rollback()
        raise


def is_token_revoked(jti: str, db: Session) -> bool:
    return db.query(models.RevokedToken.id).filter(models.RevokedToken.jti == jti).first() is not None


def extract_token(request: Request, bearer_token: Optional[str]) -> Optional[str]:
    return bearer_token or request.cookies.get(AUTH_COOKIE_NAME)


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    auth_token = extract_token(request, token)
    if not auth_token:
        return None
    payload = decode_access_token(auth_token)
    if not payload or is_token_revoked(payload["jti"], db):
        return None
    user = db.query(models.User).filter(models.User.username == payload["sub"]).first()
    if not user or user.is_blocked:
        return None
    touch_last_seen(user, db)
    return user


def touch_last_seen(user: models.User, db: Session) -> None:
    """Record activity for the "active this semester" statistics; never breaks the request."""
    now = datetime.now(timezone.utc)
    seen = user.last_seen_at
    if seen is not None and seen.tzinfo is None:  # SQLite returns naive datetimes
        seen = seen.replace(tzinfo=timezone.utc)
    if seen is not None and now - seen < LAST_SEEN_EVERY:
        return
    try:
        user.last_seen_at = now
        db.commit()
    except Exception:
        db.rollback()


def require_current_user(user: Optional[models.User] = Depends(get_current_user)) -> models.User:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Необходима авторизация",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_admin(user: models.User = Depends(require_current_user)) -> models.User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Необходимы права Администратора")
    return user


def require_moderator(user: models.User = Depends(require_current_user)) -> models.User:
    if user.role not in ("admin", "moderator"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Необходимы права Модератора или Администратора")
    return user


def is_admin(user: Optional[models.User]) -> bool:
    return bool(user) and user.role == "admin"


def is_moderator(user: Optional[models.User]) -> bool:
    return bool(user) and user.role in ("admin", "moderator")


def is_protected_admin(user: models.User) -> bool:
    """The env-configured administrator cannot be demoted, blocked or deleted from the admin panel."""
    return user.auth_source == "local" or (
        bool(settings.ADMIN_USERNAME) and user.username.lower() == settings.admin_username_normalized
    )
