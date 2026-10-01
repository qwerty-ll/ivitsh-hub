import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DataError

from app.core.config import settings
from app.core import security
from app.db.database import SessionLocal
from app.db.migrate import run_migrations
import app.models as models
from app.routers import auth, forum, chat, schedule, documents, admin, rooms, associations, tasks, posts, attachments, meetings, homework, calendar, events, achievements, booking, tribes, shop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("ivitsh_portal")

SEEDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "db", "seeds")


def _seed_table_if_empty(db, model, filename: str) -> None:
    path = os.path.join(SEEDS_DIR, filename)
    if db.query(model).first() is not None or not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        rows = json.load(f)
    db.add_all(model(**row) for row in rows)
    db.commit()
    logger.info("Seeded %d rows into %s from %s", len(rows), model.__tablename__, filename)


def seed_database() -> None:
    """Fill reference tables on first start only; afterwards they are managed from the admin panel."""
    db = SessionLocal()
    try:
        _seed_table_if_empty(db, models.Teacher, "teachers.json")
        _seed_table_if_empty(db, models.Subject, "subjects.json")
        _seed_table_if_empty(db, models.Association, "associations.json")
    except Exception:
        db.rollback()
        logger.exception("Could not seed the database")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting IVITSH KSU Portal backend")
    run_migrations()
    seed_database()
    yield


app = FastAPI(
    title="ИВИТШ Хаб API",
    description="REST API ИВИТШ Хаба — единой площадки студентов Высшей ИТ-Школы КГУ",
    version="1.1.0",
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.DOCS_ENABLED else None,
    openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
    lifespan=lifespan,
)

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Primary keys are 32-bit integers in PostgreSQL; a larger id cannot exist
_MAX_DB_ID = 2_147_483_647
_NOT_FOUND = {"detail": "Не найдено"}


@app.middleware("http")
async def reject_impossible_ids(request: Request, call_next):
    """A numeric path segment beyond any database id is a 404, not a driver overflow (500)."""
    if request.url.path.startswith("/api/") and any(
        part.isascii() and part.isdigit() and (len(part) > 10 or int(part) > _MAX_DB_ID) for part in request.url.path.split("/")
    ):
        return JSONResponse(status_code=404, content=_NOT_FOUND)
    return await call_next(request)


@app.exception_handler(OverflowError)
@app.exception_handler(DataError)
async def out_of_range_value(request: Request, exc: Exception):
    # A huge number in a query string or a body (SQLite: OverflowError, PostgreSQL: DataError)
    logger.warning("Out-of-range value in %s %s: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse(status_code=400, content={"detail": "Некорректное значение в запросе"})


@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    """Cookie-authenticated writes must carry X-Requested-With.

    A foreign site cannot add that header without a CORS preflight, which only ALLOWED_ORIGINS pass.
    Requests authenticated with an explicit Bearer header are not exposed to CSRF and are let through.
    """
    if (
        request.method in _UNSAFE_METHODS
        and request.url.path.startswith("/api/")
        and security.AUTH_COOKIE_NAME in request.cookies
        and not request.headers.get("authorization")
        and request.headers.get(security.CSRF_HEADER_NAME) != security.CSRF_HEADER_VALUE
    ):
        return JSONResponse(status_code=403, content={"detail": "Запрос отклонён: отсутствует CSRF-заголовок"})
    return await call_next(request)


app.add_middleware(GZipMiddleware, minimum_size=500)

# The SPA is served from the same origin as the API (nginx / Vite proxy), so CORS is only needed
# for extra trusted front-ends listed explicitly in ALLOWED_ORIGINS.
if settings.ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", security.CSRF_HEADER_NAME],
    )

app.include_router(auth.router)
app.include_router(forum.router)
app.include_router(chat.router)
app.include_router(schedule.router)
app.include_router(documents.router)
app.include_router(admin.router)
app.include_router(rooms.router)
app.include_router(associations.router)
app.include_router(tasks.router)
app.include_router(posts.router)
app.include_router(attachments.router)
app.include_router(meetings.router)
app.include_router(homework.router)
app.include_router(calendar.router)
app.include_router(events.router)
app.include_router(achievements.router)
app.include_router(booking.router)
app.include_router(tribes.router)
app.include_router(shop.router)


@app.get("/api/v1/health")
def health_check():
    """Liveness probe; intentionally does not touch the database."""
    return {"status": "ok", "service": "IVITSH Portal Backend API"}


@app.get("/api/v1/health/ready")
def readiness_check():
    """Readiness probe for Docker and monitoring: the API can reach its database."""
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness check: database is unreachable")
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "down"})
    finally:
        db.close()
    return {"status": "ok", "database": "ok"}
