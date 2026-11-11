"""
Database engine and session management.

WHY sync SQLAlchemy: the spec explicitly allows sync, and it's simpler to
debug and explain in an interview.  The session dependency (get_db) gives
each request its own transaction scope.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# WHY pool_pre_ping: detects stale connections after DB restarts,
# avoiding cryptic "connection closed" errors on the first request.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and ensures cleanup.

    WHY generator dependency: guarantees the session is closed even if
    the endpoint raises an exception, preventing connection leaks.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db() -> bool:
    """Run a trivial query to verify DB connectivity.

    Used by /readyz.  Returns True if reachable, False otherwise.
    WHY SELECT 1: lightest possible query; we only care about connectivity.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
