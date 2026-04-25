# kb/database.py
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from kb.config import settings

logger = logging.getLogger(__name__)

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Backward-compat indexes for DBs created before index=True was added.
# `Base.metadata.create_all` does NOT add indexes to existing tables in SQLite,
# so we issue idempotent CREATE INDEX IF NOT EXISTS for them explicitly.
_BACKCOMPAT_INDEXES = [
    ("ix_papers_url", "papers", "url"),
    ("ix_papers_source_type", "papers", "source_type"),
    ("ix_papers_is_processed", "papers", "is_processed"),
    ("ix_papers_impact_score", "papers", "impact_score"),
    ("ix_papers_ingested_date", "papers", "ingested_date"),
]


def init_db() -> None:
    import kb.models  # noqa: F401 — ensure models registered
    Base.metadata.create_all(bind=engine)

    # Add indexes idempotently for pre-existing tables
    with engine.begin() as conn:
        for name, table, column in _BACKCOMPAT_INDEXES:
            try:
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})'))
            except Exception as e:
                logger.warning("Could not create index %s: %s", name, e)
