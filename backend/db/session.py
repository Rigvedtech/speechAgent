"""SQLAlchemy engine and session helpers."""

from __future__ import annotations

import logging
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import config as app_config

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
SessionLocal: Optional[sessionmaker] = None


def is_db_configured() -> bool:
    return bool(app_config.DATABASE_URL)


def get_engine() -> Engine:
    global _engine, SessionLocal
    if not app_config.DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. Add it to backend/.env "
            "(e.g. postgresql://postgres:password@localhost:5432/prabhat_DB)."
        )
    if _engine is None:
        _engine = create_engine(
            app_config.DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        logger.info("[DB] Engine created")
    return _engine


def init_db() -> bool:
    """
    Verify DB connectivity at startup.
    Returns True if connected; False if DATABASE_URL missing or unreachable.
    Does not create tables — schema is applied via database/init.sql.
    """
    if not is_db_configured():
        logger.warning(
            "[DB] DATABASE_URL not set — auth/CRUD APIs disabled; interview APIs still work"
        )
        return False
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("[DB] Connected successfully")
        return True
    except Exception as ex:
        logger.error("[DB] Connection failed: %s", ex)
        return False


def get_session_factory() -> sessionmaker:
    """Return the live sessionmaker (always re-read after engine init)."""
    get_engine()
    if SessionLocal is None:
        raise RuntimeError("Database session factory failed to initialize")
    return SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
