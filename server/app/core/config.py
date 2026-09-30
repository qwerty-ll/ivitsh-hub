"""Single source of application configuration, read once from the environment / .env."""
import os
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

_PLACEHOLDER_SECRETS = {
    "your_super_secret_jwt_key_here",
    "change_me",
    "changeme",
    "secret",
}
_ALLOWED_JWT_ALGORITHMS = {"HS256", "HS384", "HS512"}


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _list(name: str) -> list:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


class Settings:
    def __init__(self) -> None:
        self.SECRET_KEY = os.getenv("SECRET_KEY", "")
        if not self.SECRET_KEY or self.SECRET_KEY.strip().lower() in _PLACEHOLDER_SECRETS or len(self.SECRET_KEY) < 32:
            raise RuntimeError(
                "SECRET_KEY is missing, a placeholder or shorter than 32 characters. "
                "Generate one with: python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        self.ALGORITHM = os.getenv("ALGORITHM", "HS256").strip().upper()
        if self.ALGORITHM not in _ALLOWED_JWT_ALGORITHMS:
            raise RuntimeError(f"ALGORITHM must be one of {sorted(_ALLOWED_JWT_ALGORITHMS)}")
        self.ACCESS_TOKEN_EXPIRE_MINUTES = _int("ACCESS_TOKEN_EXPIRE_MINUTES", 1440)
        # Secure cookies need HTTPS; browsers still accept them on http://localhost for development.
        self.COOKIE_SECURE = _bool("COOKIE_SECURE", True)

        self.DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./portal.db")
        self.DB_POOL_SIZE = _int("DB_POOL_SIZE", 10)
        self.DB_MAX_OVERFLOW = _int("DB_MAX_OVERFLOW", 20)

        self.ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip()
        self.ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

        self.ALLOWED_ORIGINS = _list("ALLOWED_ORIGINS")
        self.DOCS_ENABLED = _bool("DOCS_ENABLED", False)

        self.EIOS_BASE_URL = os.getenv("EIOS_BASE_URL", "https://eios.kosgos.ru/api").rstrip("/")
        self.VERIFY_SSL = _bool("VERIFY_SSL", True)
        # SDO (Moodle): the same login and password as EIOS. Empty SDO_BASE_URL turns the course list off.
        self.SDO_BASE_URL = os.getenv("SDO_BASE_URL", "https://sdo.kosgos.ru").strip().rstrip("/")
        self.SDO_SERVICE = os.getenv("SDO_SERVICE", "moodle_mobile_app").strip()

        # GigaChat "Authorization key" (base64 of client_id:client_secret) from the Sber developer console.
        self.GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY") or os.getenv("GIGACHAT_SECRET", "")
        self.GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE") or "GIGACHAT_API_PERS"
        # "GigaChat-2" is GigaChat 2 Lite; first-generation names ("GigaChat") are redirected to it anyway.
        self.GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL") or "GigaChat-2"
        # Parallel requests the key allows: 1 for individuals (GIGACHAT_API_PERS), 10 for companies.
        # The limit is per backend process, and the portal runs one.
        self.GIGACHAT_MAX_STREAMS = max(1, int(os.getenv("GIGACHAT_MAX_STREAMS") or 1))
        # The Russian Trusted Root and Sub CAs that sign the GigaChat endpoints ship with the portal
        # (app/assets/certs/russian_trusted_ca.pem); GIGACHAT_CA_BUNDLE adds another PEM file on top.
        self.GIGACHAT_CA_BUNDLE = os.getenv("GIGACHAT_CA_BUNDLE", "").strip()

        # Whom the explanatory notes and retake requests ВИТШик prepares are addressed to (dative case).
        # DOCUMENT_ADDRESSEE_NAME="-" leaves a blank line to fill in by hand.
        self.DOCUMENT_ADDRESSEE_TITLE = (os.getenv("DOCUMENT_ADDRESSEE_TITLE") or "Директору Высшей ИТ-школы КГУ").strip()
        name = (os.getenv("DOCUMENT_ADDRESSEE_NAME") or "А. С. Борисову").strip()
        self.DOCUMENT_ADDRESSEE_NAME = "" if name == "-" else name

        # Files attached to tasks and announcements: kept on disk here (a Docker volume), never in git
        self.UPLOAD_DIR = os.path.abspath(os.getenv("UPLOAD_DIR", "").strip() or "uploads")
        self.MAX_UPLOAD_MB = max(1, _int("MAX_UPLOAD_MB", 10))

    @property
    def admin_username_normalized(self) -> str:
        return self.ADMIN_USERNAME.lower()


settings = Settings()
