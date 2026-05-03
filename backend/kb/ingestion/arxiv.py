# kb/ingestion/arxiv.py
import datetime
import logging

import arxiv

from kb.config import settings
from kb.database import SessionLocal
from kb.models import Paper, SourceType

logger = logging.getLogger(__name__)

ARXIV_CATEGORIES = [
    "cs.AR",   # Architecture
    "cs.AI",   # Artificial Intelligence
    "cs.LG",   # Machine Learning
    "cs.CL",   # Computation and Language (LLMs)
    "cs.ET",   # Emerging Technologies
    "cs.DC",   # Distributed/Parallel Computing
    "cs.PF",   # Performance
    "cs.SE",   # Software Engineering
    "cs.NE",   # Neural and Evolutionary Computing
]


def fetch_recent_papers(days_back: int | None = 1) -> list[dict]:
    """Fetch recent papers from ArXiv.

    Queries each category independently (rather than ORing them in one query)
    so that no single high-volume category like cs.AI can starve the others
    when MAX_RESULTS is hit.

    `days_back` semantics:
        * int → explicit override, applied to every category.
        * None → cold-start-aware lookback for `source_name="arxiv"` via
          `kb.ingestion.run._lookback_for_source`. Behaves identically to
          the global gap on existing DBs (since every arxiv row shares the
          same source_name) but stays consistent with the per-source model
          used by RSS / sitemap fetchers.
    """
    if days_back is None:
        # Lazy import: run.py imports this fetcher at top level.
        from kb.ingestion.run import _lookback_for_source
        days_back = _lookback_for_source("arxiv")
        logger.info("[arxiv] lookback=%dd (per-source)", days_back)

    client = arxiv.Client()
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days_back)
    seen_urls: set[str] = set()
    papers: list[dict] = []

    per_category = settings.arxiv_per_category

    for cat in ARXIV_CATEGORIES:
        try:
            search = arxiv.Search(
                query=f"cat:{cat}",
                max_results=per_category,
                sort_by=arxiv.SortCriterion.SubmittedDate,
            )
            cat_count = 0
            for result in client.results(search):
                if result.published < cutoff:
                    # Results are date-sorted descending; once we cross the cutoff we can stop
                    break
                url = result.entry_id
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                papers.append({
                    "title": result.title,
                    "authors": [a.name for a in result.authors],
                    "organizations": [],
                    "abstract": result.summary.replace("\n", " "),
                    "url": url,
                    "pdf_url": result.pdf_url,
                    "source_type": SourceType.PAPER,
                    "source_name": "arxiv",
                    "published_date": result.published,
                    "categories": result.categories,
                    "venue": "",
                })
                cat_count += 1
            logger.info("[arxiv] %s: %d papers", cat, cat_count)
        except Exception:
            logger.exception("[arxiv] %s: query failed", cat)

    return papers


def save_papers(papers: list[dict]) -> int:
    """Save papers to DB, skip duplicates by URL. Returns count of new papers."""
    db = SessionLocal()
    new_count = 0
    try:
        for p in papers:
            if not p.get("url"):
                continue
            existing = db.query(Paper).filter(Paper.url == p["url"]).first()
            if existing:
                continue
            db.add(Paper(**p))
            new_count += 1
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[arxiv] save failed")
        raise
    finally:
        db.close()
    return new_count
