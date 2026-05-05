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


def _seed_paper(
    ingested_date: datetime.datetime,
    url: str,
    source_name: str = "arxiv",
    source_type=None,
) -> None:
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType

    db = SessionLocal()
    try:
        p = Paper(
            title="seed",
            authors=[],
            organizations=[],
            abstract="",
            source_type=source_type or SourceType.PAPER,
            source_name=source_name,
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

    assert run_mod._compute_days_back() == run_mod.settings.ingest_empty_db_days


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
    assert run_mod._compute_days_back() == run_mod.settings.ingest_gap_max_days


def test_compute_days_back_clamps_low_at_one(clean_papers):
    """Same-day re-runs must still look at the last 1 day, not 0 (which would
    return zero papers from the date-cutoff sources)."""
    from kb.ingestion import run as run_mod

    _seed_paper(
        datetime.datetime.now(datetime.UTC),
        "https://example.test/run/gap-now",
    )
    assert run_mod._compute_days_back() == run_mod.settings.ingest_gap_min_days


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
    assert run_mod.settings.ingest_gap_min_days <= result <= run_mod.settings.ingest_gap_max_days


# ─── _lookback_for_source (per-source cold-start) ─────────────────


def test_lookback_for_source_unknown_source_returns_cold_start(clean_papers):
    """The core "new source = automatic 30-day backfill" guarantee: if the
    DB has zero rows under a given source_name, the per-source helper must
    fall back to settings.ingest_empty_db_days, even when other sources
    have very recent rows. Without this, adding a new RSS feed would only
    get 1 day of content."""
    from kb.ingestion import run as run_mod

    _seed_paper(
        datetime.datetime.now(datetime.UTC),
        "https://example.test/run/lookback-existing",
        source_name="arxiv",
    )
    assert (
        run_mod._lookback_for_source("brand-new-feed-not-yet-seen")
        == run_mod.settings.ingest_empty_db_days
    )


def test_lookback_for_source_existing_source_returns_gap(clean_papers):
    """A mature source with a recent row should report its own gap, not
    cold-start, even if other (newer) sources are missing entirely."""
    from kb.ingestion import run as run_mod

    _seed_paper(
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=4),
        "https://example.test/run/lookback-arxiv-4d",
        source_name="arxiv",
    )
    assert run_mod._lookback_for_source("arxiv") == 4


def test_lookback_for_source_isolates_per_source(clean_papers):
    """Two sources with very different last-seen timestamps must report
    independent windows — that's the whole point of the per-source design."""
    from kb.ingestion import run as run_mod

    now = datetime.datetime.now(datetime.UTC)
    _seed_paper(
        now - datetime.timedelta(days=2),
        "https://example.test/run/iso-arxiv",
        source_name="arxiv",
    )
    _seed_paper(
        now - datetime.timedelta(days=10),
        "https://example.test/run/iso-openai",
        source_name="OpenAI",
    )

    assert run_mod._lookback_for_source("arxiv") == 2
    assert run_mod._lookback_for_source("OpenAI") == 10
    # Brand-new source still cold-starts despite other sources being mature.
    assert (
        run_mod._lookback_for_source("totally-new-source")
        == run_mod.settings.ingest_empty_db_days
    )


def test_lookback_for_source_none_matches_global(clean_papers):
    """Passing None must match the legacy global semantics, since
    _compute_days_back is now a thin wrapper around it."""
    from kb.ingestion import run as run_mod

    _seed_paper(
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=5),
        "https://example.test/run/none-global",
    )
    assert run_mod._lookback_for_source(None) == run_mod._compute_days_back() == 5


# ─── run_ingestion source propagation ─────────────────────────────


def _spy_run_ingestion(run_mod, **call_kwargs):
    """Patch all four fetchers + savers; return the captured days_back map.

    The fourth fetcher is `fetch_recent_sitemap_posts` (LMSYS / SGLang and any
    other sitemap-only blog source). The orchestrator now transparently
    propagates whatever `days_back` was passed to `run_ingestion` (including
    None, which signals "let each fetcher compute its own per-source window")
    so the captured value mirrors the input — fetchers do the per-source
    lookup themselves via `_lookback_for_source`.
    """
    captured: dict[str, int | None] = {}

    def make_spy(name):
        def spy(days_back):
            captured[name] = days_back
            return []
        return spy

    # Also short-circuit the fulltext prefetch tail so the test never
    # touches the network, even if the session-scoped DB happens to
    # contain blog/project rows from prior tests with empty full_text.
    from kb.processing import fulltext as fulltext_mod

    with patch.object(run_mod, "fetch_recent_papers", side_effect=make_spy("arxiv")), \
         patch.object(run_mod, "fetch_recent_posts", side_effect=make_spy("rss")), \
         patch.object(run_mod, "fetch_recent_sitemap_posts", side_effect=make_spy("sitemap_blogs")), \
         patch.object(run_mod, "fetch_trending_repos", side_effect=make_spy("github")), \
         patch.object(run_mod, "save_papers", return_value=0), \
         patch.object(run_mod, "save_posts", return_value=0), \
         patch.object(run_mod, "save_repos", return_value=0), \
         patch.object(fulltext_mod, "prefetch_pending_full_text", return_value=0):
        run_mod.run_ingestion(**call_kwargs)

    return captured


def test_run_ingestion_default_propagates_none_to_all_sources(clean_papers):
    """Without an explicit override, `run_ingestion` hands None to every
    fetcher so each one can compute its own per-source-name lookback. This
    is what enables "add a new feed → next run automatically backfills 30
    days for that feed only" without expanding the window for every other
    source.
    """
    from kb.ingestion import run as run_mod

    captured = _spy_run_ingestion(run_mod)
    assert captured == {"arxiv": None, "rss": None,
                        "sitemap_blogs": None, "github": None}


def test_run_ingestion_explicit_override_takes_precedence(clean_papers):
    """An explicit days_back must skip per-source lookup and propagate
    as-is, even when a recent paper would otherwise produce a smaller
    window. Used for tests and one-off operator backfills."""
    from kb.ingestion import run as run_mod

    _seed_paper(
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=2),
        "https://example.test/run/override",
    )
    captured = _spy_run_ingestion(run_mod, days_back=7)
    assert captured == {"arxiv": 7, "rss": 7, "sitemap_blogs": 7, "github": 7}
