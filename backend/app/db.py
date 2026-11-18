"""Database engine and session handling (PostgreSQL in Docker, SQLite in lite mode)."""
from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import JSON, create_engine, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
IS_SQLITE = settings.database_url.startswith("sqlite")
IS_POSTGRES = settings.database_url.startswith("postgresql")

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 30} if IS_SQLITE else {},
    pool_pre_ping=True,
)

if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # WAL lets the API read while the worker writes
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# JSONB on PostgreSQL, JSON elsewhere
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Naive UTC timestamp (all times are stored as UTC)."""
    return datetime.now(UTC).replace(tzinfo=None)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine)
    if IS_POSTGRES:  # full-text search index over log messages
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_log_events_fts ON log_events "
                "USING GIN (to_tsvector('simple', message))"))
