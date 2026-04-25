# tests/test_ingestion_run.py
"""Orchestrator tests: gap-based days_back computation and source propagation."""
from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest


@pytest.fixture
def clean_papers():
    """Wipe papers so MAX(ingested_date) reflects only the rows seeded by
    the current test. Other tests share the session-scoped DB and would
    otherwise pollute the gap calculation."""
    from kb.database import SessionLocal
    from kb.models import Paper

    db = SessionLocal()
    try:
        db.query(Paper).delete()
        db.commit()
    finally:
        db.close()


def _seed_paper(ingested_date: datetime.datetime, url: str) -> None:
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType

    db = SessionLocal()
    try:
        p = Paper(
            title="seed",
            authors=[],
            organizations=[],
            abstract="",
            source_type=SourceType.PAPER,
            source_name="arxiv",
            url=url,
            ingested_date=ingested_date,
            published_date=ingested_date,
        )
        db.add(p)
        db.commit()
    finally:
        db.close()


# ─── _compute_days_back ───────────────────────────────────────────


def test_compute_days_back_empty_db_returns_cold_start_window(clean_papers):
    from kb.ingestion import run as run_mod

    assert run_mod._compute_days_back() == run_mod.EMPTY_DB_DAYS


def test_compute_days_back_returns_gap_when_within_bounds(clean_papers):
    from kb.ingestion import run as run_mod

    _seed_paper(
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=5),
        "https://example.test/run/gap-5d",
    )
    assert run_mod._compute_days_back() == 5


def test_compute_days_back_clamps_high_at_max(clean_papers):
    from kb.ingestion import run as run_mod

    _seed_paper(
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=100),
        "https://example.test/run/gap-100d",
    )
    assert run_mod._compute_days_back() == run_mod.GAP_MAX_DAYS


def test_compute_days_back_clamps_low_at_one(clean_papers):
    """Same-day re-runs must still look at the last 1 day, not 0 (which would
    return zero papers from the date-cutoff sources)."""
    from kb.ingestion import run as run_mod

    _seed_paper(
        datetime.datetime.now(datetime.UTC),
        "https://example.test/run/gap-now",
    )
    assert run_mod._compute_days_back() == run_mod.GAP_MIN_DAYS


def test_compute_days_back_tolerates_naive_legacy_datetime(clean_papers):
    """SQLite can return timezone-naive datetimes for older rows. The helper
    must not crash on `naive - aware` subtraction."""
    from kb.ingestion import run as run_mod

    naive_three_days_ago = (
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=3)
    ).replace(tzinfo=None)
    _seed_paper(naive_three_days_ago, "https://example.test/run/naive")
    # The exact value depends on tz handling; accept the reasonable range.
    result = run_mod._compute_days_back()
    assert run_mod.GAP_MIN_DAYS <= result <= run_mod.GAP_MAX_DAYS


# ─── run_ingestion source propagation ─────────────────────────────


def _spy_run_ingestion(run_mod, **call_kwargs):
    """Patch all three fetchers + savers; return the captured days_back map."""
    captured: dict[str, int] = {}

    def make_spy(name):
        def spy(days_back):
            captured[name] = days_back
            return []
        return spy

    with patch.object(run_mod, "fetch_recent_papers", side_effect=make_spy("arxiv")), \
         patch.object(run_mod, "fetch_recent_posts", side_effect=make_spy("rss")), \
         patch.object(run_mod, "fetch_trending_repos", side_effect=make_spy("github")), \
         patch.object(run_mod, "save_papers", return_value=0), \
         patch.object(run_mod, "save_posts", return_value=0), \
         patch.object(run_mod, "save_repos", return_value=0):
        run_mod.run_ingestion(**call_kwargs)

    return captured


def test_run_ingestion_propagates_cold_start_window_to_all_sources(clean_papers):
    from kb.ingestion import run as run_mod

    captured = _spy_run_ingestion(run_mod)
    assert captured == {"arxiv": run_mod.EMPTY_DB_DAYS,
                        "rss": run_mod.EMPTY_DB_DAYS,
                        "github": run_mod.EMPTY_DB_DAYS}


def test_run_ingestion_explicit_override_takes_precedence(clean_papers):
    """An explicit days_back must skip MAX() and propagate as-is, even when
    a recent paper would otherwise produce a smaller window."""
    from kb.ingestion import run as run_mod

    _seed_paper(
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=2),
        "https://example.test/run/override",
    )
    captured = _spy_run_ingestion(run_mod, days_back=7)
    assert captured == {"arxiv": 7, "rss": 7, "github": 7}
