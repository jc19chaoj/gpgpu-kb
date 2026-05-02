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
    ("ix_papers_quality_score", "papers", "quality_score"),
    ("ix_papers_ingested_date", "papers", "ingested_date"),
]

# Columns added after the original schema. `Base.metadata.create_all` doesn't
# add columns to existing tables, so we ALTER them in idempotently. Each entry
# is (column_name, sql_type_with_default).
_BACKCOMPAT_COLUMNS = [
    ("quality_score", "FLOAT DEFAULT 0.0"),
    ("relevance_score", "FLOAT DEFAULT 0.0"),
    ("score_rationale", "TEXT DEFAULT ''"),
    ("full_text", "TEXT DEFAULT ''"),
]


def _ensure_papers_columns(conn) -> None:
    """Add missing columns to `papers` (SQLite-friendly, idempotent).

    Only runs on SQLite; on Postgres we expect alembic-style migrations.
    """
    if not settings.database_url.startswith("sqlite"):
        return
    rows = conn.execute(text("PRAGMA table_info(papers)")).fetchall()
    existing = {r[1] for r in rows}  # second column is the column name
    for name, ddl_type in _BACKCOMPAT_COLUMNS:
        if name in existing:
            continue
        try:
            conn.execute(text(f"ALTER TABLE papers ADD COLUMN {name} {ddl_type}"))
        except Exception as e:
            logger.warning("Could not add column papers.%s: %s", name, e)


def init_db() -> None:
    import kb.models  # noqa: F401 — ensure models registered
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        # 1) Add missing columns (must happen before index creation since
        #    ix_papers_quality_score references quality_score).
        _ensure_papers_columns(conn)
        # 2) Add indexes idempotently for pre-existing tables.
        for name, table, column in _BACKCOMPAT_INDEXES:
            try:
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})'))
            except Exception as e:
                logger.warning("Could not create index %s: %s", name, e)
