# kb/ingestion/rss.py
import datetime
import logging

import feedparser

from kb.database import SessionLocal
from kb.models import Paper, SourceType

logger = logging.getLogger(__name__)

# Feeds verified active as of 2026-04. Update this list when feeds rot.
# Removed: AnandTech (site shut down in 2024, /rss redirects to forums HTML);
#          Meta AI Blog (ai.meta.com/blog/feed/ returns 404, no public RSS).
FEEDS = [
    # Chip / Architecture
    ("https://semiengineering.com/feed/", "Semiconductor Engineering"),
    ("https://chipsandcheese.com/feed/", "Chips and Cheese"),
    ("https://fuse.wikichip.org/feed/", "WikiChip Fuse"),
    # SemiAnalysis migrated to Substack in late 2025; the wp.com feed stopped at 2025-09.
    ("https://semianalysis.substack.com/feed", "SemiAnalysis"),
    # AI / ML labs
    ("https://openai.com/news/rss.xml", "OpenAI"),
    ("https://blog.google/technology/ai/rss/", "Google AI Blog"),
    ("https://huggingface.co/blog/feed.xml", "Hugging Face Blog"),
    ("https://developer.nvidia.com/blog/feed", "NVIDIA Developer Blog"),
    ("https://research.nvidia.com/rss.xml", "NVIDIA Research"),
    # Systems / Performance personalities
    # lilianweng.github.io serves the Atom feed at /index.xml, not /feed.xml.
    ("https://lilianweng.github.io/index.xml", "Lilian Weng"),
    ("https://karpathy.github.io/feed.xml", "Andrej Karpathy"),
    ("https://www.interconnects.ai/feed", "Interconnects (Nathan Lambert)"),
]


def fetch_recent_posts(days_back: int = 1) -> list[dict]:
    """Fetch recent blog posts from RSS feeds."""
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days_back)
    posts: list[dict] = []

    for feed_url, source_name in FEEDS:
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
                "categories": list(entry.get("tags", [])),
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
