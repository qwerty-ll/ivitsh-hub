"""Bring the database schema up to date. Run directly with: python -m app.db.migrate"""
import logging
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.db.database import engine

logger = logging.getLogger("ivitsh_portal.migrate")

_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASELINE_REVISION = "0001"
# Advisory lock key for start-up work that must run once however many workers start
STARTUP_LOCK = 515151


def run_migrations() -> None:
    cfg = Config(os.path.join(_SERVER_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_SERVER_DIR, "migrations"))
    cfg.attributes["configure_logging"] = False
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            # Several workers start at once: one migrates, the others wait and then find nothing to do
            connection.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": STARTUP_LOCK})
        cfg.attributes["connection"] = connection
        tables = set(inspect(connection).get_table_names())
        if "alembic_version" not in tables and "users" in tables:
            # Database created by the old create_all() startup code: adopt it at the baseline.
            logger.info("Existing database without migration history, stamping baseline %s", BASELINE_REVISION)
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
