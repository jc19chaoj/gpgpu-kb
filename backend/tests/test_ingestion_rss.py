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
