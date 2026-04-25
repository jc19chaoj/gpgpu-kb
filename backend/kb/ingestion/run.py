# kb/ingestion/run.py
"""Run all ingestion pipelines. Called by cron job."""
import datetime
import logging

from sqlalchemy import func

from kb.database import SessionLocal
from kb.ingestion.arxiv import fetch_recent_papers, save_papers
from kb.ingestion.rss import fetch_recent_posts, save_posts
from kb.ingestion.github_trending import fetch_trending_repos, save_repos
from kb.models import Paper

logger = logging.getLogger(__name__)

# Lookback window bounds. Empty DB → EMPTY_DB_DAYS (cold start);
# otherwise gap = today − MAX(ingested_date), clamped to [GAP_MIN, GAP_MAX].
GAP_MIN_DAYS = 1
GAP_MAX_DAYS = 30
EMPTY_DB_DAYS = 30


def _compute_days_back() -> int:
    db = SessionLocal()
    try:
        last = db.query(func.max(Paper.ingested_date)).scalar()
    finally:
        db.close()

    if last is None:
        return EMPTY_DB_DAYS

    if last.tzinfo is None:
        last = last.replace(tzinfo=datetime.UTC)
    gap_days = (datetime.datetime.now(datetime.UTC) - last).days
    return min(max(gap_days, GAP_MIN_DAYS), GAP_MAX_DAYS)


def run_ingestion(days_back: int | None = None) -> dict[str, int]:
    """Run all ingestion sources. Returns counts.

    When `days_back` is None, the orchestrator picks a value based on
    `MAX(Paper.ingested_date)` so the lookback window automatically
    matches the time since the last successful run. Pass an explicit
    integer to override (useful for tests and one-off backfills).
    """
    if days_back is None:
        days_back = _compute_days_back()
    logger.info("[ingestion] days_back=%d", days_back)

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
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_ingestion()
