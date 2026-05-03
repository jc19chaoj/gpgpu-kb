# tests/test_ingestion_rss.py
"""Tests for kb/ingestion/rss.py — no network, feedparser patched."""
from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from kb.ingestion.rss import fetch_recent_posts, save_posts
from kb.models import Paper, SourceType


def _entry(
    title: str,
    link: str,
    author: str = "Author",
    summary: str = "Summary",
    published_parsed: tuple | None = None,
) -> SimpleNamespace:
    e = SimpleNamespace(
        title=title,
        link=link,
        author=author,
        summary=summary,
        published_parsed=published_parsed,
        tags=[],
    )
    # feedparser entries support .get() via dict-like access
    e.get = lambda key, default="": getattr(e, key, default)
    return e


def _fresh_parsed() -> tuple:
    """Return a time.struct_time-compatible 9-tuple for today."""
    now = datetime.datetime.now(datetime.UTC)
    return (now.year, now.month, now.day, now.hour, now.minute, now.second, 0, 0, 0)


def _old_parsed() -> tuple:
    """Return a tuple 30 days in the past."""
    old = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30)
    return (old.year, old.month, old.day, old.hour, old.minute, old.second, 0, 0, 0)


def _make_feed(entries: list, bozo: bool = False, bozo_exception=None) -> MagicMock:
    feed = MagicMock()
    feed.bozo = bozo
    feed.bozo_exception = bozo_exception
    feed.entries = entries
    return feed


# ---------------------------------------------------------------------------
# fetch_recent_posts
# ---------------------------------------------------------------------------

class TestFetchRecentPosts:
    def test_valid_posts_returned_with_blog_source_type(self):
        entry = _entry(
            title="GPU Memory Deep Dive",
            link="https://example.com/gpu-memory",
            published_parsed=_fresh_parsed(),
        )
        feed = _make_feed([entry])

        with patch("kb.ingestion.rss.FEEDS", [("https://example.com/feed", "Example Blog")]):
            with patch("kb.ingestion.rss.feedparser.parse", return_value=feed):
                posts = fetch_recent_posts(days_back=1)

        assert len(posts) == 1
        assert posts[0]["source_type"] == SourceType.BLOG
        assert posts[0]["source_name"] == "Example Blog"
        assert posts[0]["url"] == "https://example.com/gpu-memory"
        assert posts[0]["title"] == "GPU Memory Deep Dive"

    def test_posts_older_than_cutoff_filtered(self):
        old_entry = _entry(
            title="Old Post",
            link="https://example.com/old",
            published_parsed=_old_parsed(),
        )
        feed = _make_feed([old_entry])

        with patch("kb.ingestion.rss.FEEDS", [("https://example.com/feed", "Blog")]):
            with patch("kb.ingestion.rss.feedparser.parse", return_value=feed):
                posts = fetch_recent_posts(days_back=1)

        assert posts == []

    def test_entry_without_link_skipped(self):
        entry = _entry(title="No Link", link="", published_parsed=_fresh_parsed())
        feed = _make_feed([entry])

        with patch("kb.ingestion.rss.FEEDS", [("https://example.com/feed", "Blog")]):
            with patch("kb.ingestion.rss.feedparser.parse", return_value=feed):
                posts = fetch_recent_posts(days_back=1)

        assert posts == []

    def test_malformed_feed_logs_warning_and_skips(self, caplog):
        feed = _make_feed([], bozo=True, bozo_exception="URLError: bad url")

        with patch("kb.ingestion.rss.FEEDS", [("https://bad.url/feed", "Bad Blog")]):
            with patch("kb.ingestion.rss.feedparser.parse", return_value=feed):
                import logging
                with caplog.at_level(logging.WARNING, logger="kb.ingestion.rss"):
                    posts = fetch_recent_posts(days_back=1)

        assert posts == []
        assert any("malformed" in r.message.lower() or "Bad Blog" in r.message for r in caplog.records)

    def test_empty_feed_produces_no_posts(self):
        feed = _make_feed([])

        with patch("kb.ingestion.rss.FEEDS", [("https://example.com/feed", "Empty Blog")]):
            with patch("kb.ingestion.rss.feedparser.parse", return_value=feed):
                posts = fetch_recent_posts(days_back=1)

        assert posts == []

    def test_parse_exception_skips_feed_silently(self, caplog):
        with patch("kb.ingestion.rss.FEEDS", [("https://example.com/feed", "Broken Blog")]):
            with patch("kb.ingestion.rss.feedparser.parse", side_effect=Exception("conn error")):
                import logging
                with caplog.at_level(logging.ERROR, logger="kb.ingestion.rss"):
                    posts = fetch_recent_posts(days_back=1)

        assert posts == []

    def test_no_published_date_entry_included(self):
        """Entries without published_parsed should still be collected (date is None)."""
        entry = _entry(title="No Date", link="https://example.com/no-date", published_parsed=None)
        feed = _make_feed([entry])

        with patch("kb.ingestion.rss.FEEDS", [("https://example.com/feed", "Blog")]):
            with patch("kb.ingestion.rss.feedparser.parse", return_value=feed):
                posts = fetch_recent_posts(days_back=1)

        assert len(posts) == 1
        assert posts[0]["published_date"] is None

    def test_tags_normalized_to_strings(self):
        """feedparser yields tags as dicts with `term`/`scheme`/`label`. Persist
        the human-readable `term` (or `label` fallback) as plain strings, not
        the raw dict — otherwise PaperOut.categories: list[str] explodes when
        the API later serializes the row."""
        entry = _entry(
            title="With Tags",
            link="https://example.com/with-tags",
            published_parsed=_fresh_parsed(),
        )
        entry.tags = [
            {"term": "AI", "scheme": "http://x", "label": None},
            {"term": "Hardware"},
            {"label": "Fallback Label"},   # no `term` → fall back to label
            {"scheme": "http://x"},        # neither → must be dropped
            "plain-string-tag",            # already a string → pass through
        ]
        feed = _make_feed([entry])

        with patch("kb.ingestion.rss.FEEDS", [("https://example.com/feed", "Blog")]):
            with patch("kb.ingestion.rss.feedparser.parse", return_value=feed):
                posts = fetch_recent_posts(days_back=1)

        assert len(posts) == 1
        assert posts[0]["categories"] == [
            "AI",
            "Hardware",
            "Fallback Label",
            "plain-string-tag",
        ]
        # Sanity: no dicts leaked through
        assert all(isinstance(c, str) for c in posts[0]["categories"])

    def test_no_tags_yields_empty_categories(self):
        entry = _entry(
            title="No Tags",
            link="https://example.com/no-tags",
            published_parsed=_fresh_parsed(),
        )
        # _entry already sets tags=[]
        feed = _make_feed([entry])

        with patch("kb.ingestion.rss.FEEDS", [("https://example.com/feed", "Blog")]):
            with patch("kb.ingestion.rss.feedparser.parse", return_value=feed):
                posts = fetch_recent_posts(days_back=1)

        assert len(posts) == 1
        assert posts[0]["categories"] == []

    def test_multiple_feeds_aggregated(self):
        entry1 = _entry("Post A", "https://a.com/1", published_parsed=_fresh_parsed())
        entry2 = _entry("Post B", "https://b.com/1", published_parsed=_fresh_parsed())
        feed1 = _make_feed([entry1])
        feed2 = _make_feed([entry2])

        feeds = [
            ("https://a.com/feed", "Blog A"),
            ("https://b.com/feed", "Blog B"),
        ]
        with patch("kb.ingestion.rss.FEEDS", feeds):
            with patch("kb.ingestion.rss.feedparser.parse", side_effect=[feed1, feed2]):
                posts = fetch_recent_posts(days_back=1)

        assert len(posts) == 2
        source_names = {p["source_name"] for p in posts}
        assert source_names == {"Blog A", "Blog B"}

    def test_per_feed_cold_start_when_days_back_is_none(self):
        """When `days_back=None`, each feed must compute its own
        cold-start-aware window via `_lookback_for_source(source_name)`.

        Concretely: if the DB has a recent row under "MatureBlog" but no
        row under "FreshBlog", the mature feed should use a tight gap
        window (so an old post is filtered out) while the fresh feed
        should use the cold-start window (so the same-aged post is kept).
        This is the user-visible "add a new feed → automatic 30-day
        backfill" guarantee.
        """
        from kb.database import SessionLocal
        from kb.models import Paper

        # Seed a row under "MatureBlog" so its lookback resolves to the
        # tight gap (≈ ingest_gap_min_days), and leave "FreshBlog" empty
        # so it cold-starts.
        db = SessionLocal()
        try:
            db.query(Paper).delete()
            db.add(Paper(
                title="seed",
                authors=[],
                organizations=[],
                abstract="",
                source_type=SourceType.BLOG,
                source_name="MatureBlog",
                url="https://example.test/rss/seed-mature",
                ingested_date=datetime.datetime.now(datetime.UTC),
                published_date=datetime.datetime.now(datetime.UTC),
            ))
            db.commit()
        finally:
            db.close()

        # An entry 10 days old: should be FILTERED OUT by the mature
        # feed's tight 1-day window, but KEPT by the fresh feed's
        # 30-day cold-start window.
        ten_days_ago = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=10)
        old_parsed = (
            ten_days_ago.year, ten_days_ago.month, ten_days_ago.day,
            ten_days_ago.hour, ten_days_ago.minute, ten_days_ago.second,
            0, 0, 0,
        )
        mature_entry = _entry(
            "Post in mature feed",
            "https://mature.example/p10d",
            published_parsed=old_parsed,
        )
        fresh_entry = _entry(
            "Post in fresh feed",
            "https://fresh.example/p10d",
            published_parsed=old_parsed,
        )
        feeds = [
            ("https://mature.example/feed", "MatureBlog"),
            ("https://fresh.example/feed", "FreshBlog"),
        ]
        feed_mature = _make_feed([mature_entry])
        feed_fresh = _make_feed([fresh_entry])

        try:
            with patch("kb.ingestion.rss.FEEDS", feeds):
                with patch(
                    "kb.ingestion.rss.feedparser.parse",
                    side_effect=[feed_mature, feed_fresh],
                ):
                    posts = fetch_recent_posts(days_back=None)

            # Mature feed's 10-day-old post is dropped; fresh feed's is kept.
            urls = {p["url"] for p in posts}
            assert urls == {"https://fresh.example/p10d"}, (
                f"Expected only fresh-feed post; got {urls}"
            )
        finally:
            db = SessionLocal()
            try:
                db.query(Paper).filter(
                    Paper.url == "https://example.test/rss/seed-mature"
                ).delete()
                db.commit()
            finally:
                db.close()


# ---------------------------------------------------------------------------
# save_posts
# ---------------------------------------------------------------------------

class TestSavePosts:
    def _post_dict(self, url: str, title: str = "Blog Post") -> dict:
        return {
            "title": title,
            "authors": ["Author"],
            "organizations": [],
            "abstract": "Summary text",
            "url": url,
            "pdf_url": "",
            "source_type": SourceType.BLOG,
            "source_name": "Test Blog",
            "published_date": datetime.datetime.now(datetime.UTC),
            "categories": [],
            "venue": "",
        }

    def test_saves_new_posts(self):
        posts = [self._post_dict("https://blog.com/post-rss-001")]
        count = save_posts(posts)
        assert count == 1

    def test_idempotent_on_duplicate(self):
        url = "https://blog.com/post-rss-idem001"
        first  = save_posts([self._post_dict(url)])
        second = save_posts([self._post_dict(url)])
        assert first == 1
        assert second == 0

    def test_skips_entry_without_url(self):
        count = save_posts([self._post_dict("")])
        assert count == 0
