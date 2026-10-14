"""Database engine, session factory and migration bootstrap."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from huntly.config import resource_path

log = logging.getLogger(__name__)


def make_engine(db_path: Path) -> Engine:
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    return engine


def run_migrations(engine: Engine) -> None:
    from alembic import command
    from alembic.config import Config

    migrations_dir = resource_path("migrations")
    cfg = Config()
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.attributes["engine"] = engine
    command.upgrade(cfg, "head")
    log.info("database migrated to head")


class Database:
    def __init__(self, db_path: Path):
        self.path = db_path
        self.engine = make_engine(db_path)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def migrate(self) -> None:
        run_migrations(self.engine)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self.SessionLocal()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()
