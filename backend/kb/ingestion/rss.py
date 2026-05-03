# kb/ingestion/rss.py
import datetime
import logging

import feedparser

from kb.database import SessionLocal
from kb.models import Paper, SourceType

logger = logging.getLogger(__name__)


def _tag_to_str(tag) -> str:
    """Normalize a feedparser tag to a string.

    feedparser yields tags as FeedParserDicts with keys `term` / `scheme` /
    `label`. The `term` is the human-readable category. Plain strings are
    passed through; anything unrecognised becomes "" so callers can drop it.
    """
    if isinstance(tag, str):
        return tag
    if hasattr(tag, "get"):
        return tag.get("term") or tag.get("label") or ""
    return ""


# Feeds verified active as of 2026-05. Update this list when feeds rot.
# Removed: AnandTech (site shut down in 2024, /rss redirects to forums HTML);
#          Meta AI Blog (ai.meta.com/blog/feed/ returns 404, no public RSS).
# Note: SGLang / LMSYS (lmsys.org) does NOT have a native RSS — its blog is a
# Next.js SPA with no /feed.xml. It's pulled via the sitemap-based scraper in
# `kb.ingestion.sitemap_blog` instead, not from this list.
FEEDS = [
    # Chip / Architecture
    ("https://semiengineering.com/feed/", "Semiconductor Engineering"),
    ("https://chipsandcheese.com/feed/", "Chips and Cheese"),
    # SemiAnalysis migrated to Substack in late 2025; the wp.com feed stopped at 2025-09.
    ("https://semianalysis.substack.com/feed", "SemiAnalysis"),
    # AI / ML labs
    ("https://openai.com/news/rss.xml", "OpenAI"),
    ("https://blog.google/technology/ai/rss/", "Google AI Blog"),
    ("https://huggingface.co/blog/feed.xml", "Hugging Face Blog"),
    ("https://developer.nvidia.com/blog/feed", "NVIDIA Developer Blog"),
    ("https://research.nvidia.com/rss.xml", "NVIDIA Research"),
    # Inference engines
    # vLLM uses Jekyll under vllm.ai; the rss.xml lives under /blog/.
    ("https://vllm.ai/blog/rss.xml", "vLLM Blog"),
    # Systems / Performance personalities
    # lilianweng.github.io serves the Atom feed at /index.xml, not /feed.xml.
    ("https://lilianweng.github.io/index.xml", "Lilian Weng"),
    ("https://karpathy.github.io/feed.xml", "Andrej Karpathy"),
    ("https://www.interconnects.ai/feed", "Interconnects (Nathan Lambert)"),
]


def fetch_recent_posts(days_back: int | None = 1) -> list[dict]:
    """Fetch recent blog posts from RSS feeds.

    `days_back` semantics:
        * int → applied uniformly to every feed (legacy behavior, useful for
          tests and one-off backfills).
        * None → each feed gets its own per-`source_name` cold-start-aware
          window. A feed whose `source_name` has no rows in the DB yet (i.e.
          newly added to FEEDS) gets `settings.ingest_empty_db_days` (30 by
          default), while mature feeds keep their tight gap-based window.
    """
    # Lazy import to avoid circular dependency at module load time:
    # run.py already imports `fetch_recent_posts` from this module, so a
    # top-level `from kb.ingestion.run import ...` here would fail during
    # the partial load of run.py. Pulling the symbol inside the function
    # body sidesteps the bootstrap order entirely.
    from kb.ingestion.run import _lookback_for_source

    now = datetime.datetime.now(datetime.UTC)
    posts: list[dict] = []

    for feed_url, source_name in FEEDS:
        per_feed_days = (
            days_back if days_back is not None
            else _lookback_for_source(source_name)
        )
        cutoff = now - datetime.timedelta(days=per_feed_days)
        logger.info("[rss] %s: lookback=%dd", source_name, per_feed_days)

        try:
            feed = feedparser.parse(feed_url)
        except Exception:
            logger.exception("[rss] %s: parse failed", source_name)
            continue

        if getattr(feed, "bozo", False) and getattr(feed, "bozo_exception", None):
            logger.warning("[rss] %s: malformed feed (%s)", source_name, feed.bozo_exception)

        kept = 0
        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime.datetime(*entry.published_parsed[:6], tzinfo=datetime.UTC)

            if published and published < cutoff:
                continue

            url = entry.get("link", "")
            if not url:
                continue

            posts.append({
                "title": entry.get("title", ""),
                "authors": [entry.get("author", "")] if entry.get("author") else [],
                "organizations": [],
                "abstract": entry.get("summary", "")[:2000],
                "url": url,
                "pdf_url": "",
                "source_type": SourceType.BLOG,
                "source_name": source_name,
                "published_date": published,
                "categories": [s for s in (_tag_to_str(t) for t in entry.get("tags", [])) if s],
                "venue": "",
            })
            kept += 1
        logger.info("[rss] %s: %d posts", source_name, kept)

    return posts


def save_posts(posts: list[dict]) -> int:
    """Save blog posts to DB (same Paper table), skip duplicates."""
    db = SessionLocal()
    new_count = 0
    try:
        for p in posts:
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
        logger.exception("[rss] save failed")
        raise
    finally:
        db.close()
    return new_count
