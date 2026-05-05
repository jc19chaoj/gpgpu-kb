# kb/ingestion/run.py
"""Run all ingestion pipelines. Called by cron job."""
import datetime
import logging

from sqlalchemy import func

from kb.config import settings
from kb.database import SessionLocal
from kb.ingestion.arxiv import fetch_recent_papers, save_papers
from kb.ingestion.rss import fetch_recent_posts, save_posts
from kb.ingestion.sitemap_blog import fetch_recent_sitemap_posts
from kb.ingestion.github_trending import fetch_trending_repos, save_repos
from kb.models import Paper

logger = logging.getLogger(__name__)


def _lookback_for_source(source_name: str | None) -> int:
    """Pick a lookback window for a single source (or the whole table).

    Empty source (no rows with that `source_name`) → cold-start backfill of
    `settings.ingest_empty_db_days`; otherwise the gap since
    `MAX(Paper.ingested_date)` for that source, clamped to
    `[ingest_gap_min_days, ingest_gap_max_days]`.

    Passing `source_name=None` skips the filter and returns the legacy
    "global" window — useful for the back-compat `_compute_days_back`
    wrapper. Per-source filtering is what makes adding a new feed /
    sitemap source automatically trigger a 30-day backfill on its first
    daily run: no rows with the new `source_name` exist yet, so MAX(...)
    is NULL and we fall through to the cold-start branch — even when
    other long-running sources have very recent rows.

    All three bounds come from `kb.config.settings` (KB_INGEST_*) so
    operators can tune the cold-start window or relax the cap for big
    backfills.
    """
    db = SessionLocal()
    try:
        q = db.query(func.max(Paper.ingested_date))
        if source_name is not None:
            q = q.filter(Paper.source_name == source_name)
        last = q.scalar()
    finally:
        db.close()

    if last is None:
        return settings.ingest_empty_db_days

    if last.tzinfo is None:
        last = last.replace(tzinfo=datetime.UTC)
    gap_days = (datetime.datetime.now(datetime.UTC) - last).days
    return min(
        max(gap_days, settings.ingest_gap_min_days),
        settings.ingest_gap_max_days,
    )


def _compute_days_back() -> int:
    """Legacy global lookback (no source filter). Kept as a thin wrapper
    around `_lookback_for_source(None)` so existing callers / tests that
    rely on the "any source" semantics continue to work.
    """
    return _lookback_for_source(None)


def run_ingestion(days_back: int | None = None) -> dict[str, int]:
    """Run all ingestion sources. Returns counts.

    When `days_back` is None, each fetcher computes its own lookback per
    `Paper.source_name` (see `_lookback_for_source`). Adding a new RSS
    feed or sitemap source therefore auto-triggers a 30-day backfill for
    that specific source on the next run, while mature sources keep
    their narrow gap-based window.

    Pass an explicit integer to override every source uniformly — useful
    for tests and one-off backfills.
    """
    if days_back is None:
        logger.info("[ingestion] days_back=per-source (cold-start aware)")
    else:
        logger.info("[ingestion] days_back=%d (explicit override)", days_back)

    results: dict[str, int] = {}

    logger.info("[ingestion] Fetching ArXiv papers...")
    try:
        papers = fetch_recent_papers(days_back=days_back)
        results["arxiv"] = save_papers(papers)
    except Exception:
        logger.exception("[ingestion] arxiv stage failed")
        results["arxiv"] = 0
    logger.info("[ingestion]   %d new papers", results["arxiv"])

    logger.info("[ingestion] Fetching blog posts...")
    try:
        posts = fetch_recent_posts(days_back=days_back)
        results["blogs"] = save_posts(posts)
    except Exception:
        logger.exception("[ingestion] rss stage failed")
        results["blogs"] = 0
    logger.info("[ingestion]   %d new posts", results["blogs"])

    # Sitemap-driven blog sources (sites with no native RSS, e.g. LMSYS / SGLang).
    # Kept as a separate stage with its own try/except so a flaky scraper
    # can't poison the RSS counts above. Reuses save_posts + Paper.url
    # uniqueness for dedup.
    logger.info("[ingestion] Fetching sitemap-based blog posts...")
    try:
        sitemap_posts = fetch_recent_sitemap_posts(days_back=days_back)
        results["sitemap_blogs"] = save_posts(sitemap_posts)
    except Exception:
        logger.exception("[ingestion] sitemap_blog stage failed")
        results["sitemap_blogs"] = 0
    logger.info("[ingestion]   %d new posts", results["sitemap_blogs"])

    logger.info("[ingestion] Fetching GitHub repos...")
    try:
        repos = fetch_trending_repos(days_back=days_back)
        results["github"] = save_repos(repos)
    except Exception:
        logger.exception("[ingestion] github stage failed")
        results["github"] = 0
    logger.info("[ingestion]   %d new repos", results["github"])

    total = sum(results.values())
    logger.info("[ingestion] Done. %d total new items.", total)

    # Tail step: prefetch full-article HTML / GitHub READMEs into
    # `Paper.full_text` so the downstream scoring stage scores against
    # the real body instead of a 200-char og:description. Best-effort —
    # any failure here must not poison the headline ingest counts above.
    # Idempotent (skips rows whose `full_text` is already populated).
    try:
        from kb.processing.fulltext import prefetch_pending_full_text

        n = prefetch_pending_full_text()
        results["fulltext_prefetched"] = n
    except Exception:
        logger.exception("[ingestion] fulltext prefetch failed (non-fatal)")
        results["fulltext_prefetched"] = 0

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_ingestion()
