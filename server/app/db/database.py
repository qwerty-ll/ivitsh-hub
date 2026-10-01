import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL
IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    db_path = DATABASE_URL.replace("sqlite:///", "", 1)
    db_dir = os.path.dirname(db_path)
    if db_dir and db_path != ":memory:" and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        # SQLite ignores foreign keys unless enabled per connection.
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()
else:
    # Sized per process: sync endpoints run in a ~40-thread pool, so more connections are never used.
    # Keep workers * (pool_size + max_overflow) below PostgreSQL max_connections (100 by default).
    engine = create_engine(
        DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )

# Connections one process can hold at once (SQLite gets SQLAlchemy's default pool of 5 + 10)
MAX_CONNECTIONS = 15 if IS_SQLITE else settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
