"""Shared persistence helper for ingestion fetchers.

Every ingestion source (arxiv / rss / sitemap_blog / github_trending) hands
the orchestrator a list of dict payloads with the same Paper-shaped keys,
then needs to: open a SessionLocal, skip empty URLs, skip URLs already in
the DB, insert the rest, commit, rollback on failure, close. This module
collapses those three near-identical loops behind one call so adding a new
source no longer means copy-pasting the persistence boilerplate.
"""
from __future__ import annotations

import logging

from kb.database import SessionLocal
from kb.models import Paper

logger = logging.getLogger(__name__)


def save_items(
    items: list[dict],
    *,
    log_prefix: str,
    dedupe_in_memory: bool = False,
) -> int:
    """Insert new Paper rows from `items`, skip duplicates by URL.

    Args:
        items: Paper-shaped dicts (must include a non-empty `url`).
        log_prefix: tag for failure logs (e.g. "arxiv", "rss", "github").
        dedupe_in_memory: when True, also de-duplicate by URL within `items`
            itself before hitting the DB. Useful for fetchers like GitHub
            trending that may return the same repo across multiple periods
            (daily/weekly/monthly) in a single batch.

    Returns:
        Number of newly inserted rows.
    """
    db = SessionLocal()
    seen: set[str] = set()
    new_count = 0
    try:
        for item in items:
            url = item.get("url")
            if not url:
                continue
            if dedupe_in_memory:
                if url in seen:
                    continue
                seen.add(url)
            existing = db.query(Paper).filter(Paper.url == url).first()
            if existing:
                continue
            db.add(Paper(**item))
            new_count += 1
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[%s] save failed", log_prefix)
        raise
    finally:
        db.close()
    return new_count
