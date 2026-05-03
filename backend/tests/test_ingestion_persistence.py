# tests/test_ingestion_persistence.py
"""Tests for kb/ingestion/_persistence.py — the shared save_items helper.

Locks the behavior contracts the three fetcher save_* wrappers
(arxiv.save_papers / rss.save_posts / github_trending.save_repos) used to
implement themselves, so the consolidation can't silently regress.
"""
from __future__ import annotations

import pytest

from kb.database import SessionLocal
from kb.ingestion._persistence import save_items
from kb.models import Paper, SourceType


@pytest.fixture
def clean_papers():
    """Wipe papers so each test sees an empty table. The test DB is
    session-scoped via conftest.py."""
    db = SessionLocal()
    try:
        db.query(Paper).delete()
        db.commit()
    finally:
        db.close()


def _item(url: str, title: str = "T") -> dict:
    return {
        "title": title,
        "authors": [],
        "organizations": [],
        "abstract": "",
        "url": url,
        "pdf_url": "",
        "source_type": SourceType.BLOG,
        "source_name": "test",
        "published_date": None,
        "categories": [],
        "venue": "",
    }


def _row_count() -> int:
    db = SessionLocal()
    try:
        return db.query(Paper).count()
    finally:
        db.close()


def test_save_items_inserts_all_new(clean_papers):
    n = save_items(
        [_item("https://example.test/persist/a"),
         _item("https://example.test/persist/b")],
        log_prefix="test",
    )
    assert n == 2
    assert _row_count() == 2


def test_save_items_skips_empty_url(clean_papers):
    items = [
        _item("https://example.test/persist/has-url"),
        {**_item("ignored"), "url": ""},      # explicit empty
        {**_item("ignored2")},                # has url; will succeed
    ]
    items[2]["url"] = "https://example.test/persist/has-url-2"

    n = save_items(items, log_prefix="test")
    assert n == 2
    assert _row_count() == 2


def test_save_items_skips_url_already_in_db(clean_papers):
    save_items([_item("https://example.test/persist/dup")], log_prefix="test")
    n = save_items(
        [_item("https://example.test/persist/dup", title="T2"),
         _item("https://example.test/persist/new")],
        log_prefix="test",
    )
    # The duplicate must be skipped without raising; only the new one counts.
    assert n == 1
    assert _row_count() == 2


def test_save_items_dedupe_in_memory_collapses_intra_batch_duplicates(clean_papers):
    """GitHub trending may return the same repo across daily/weekly/monthly,
    so save_repos opts into dedupe_in_memory=True. Lock that contract."""
    n = save_items(
        [_item("https://example.test/persist/repo"),
         _item("https://example.test/persist/repo", title="dup-in-batch")],
        log_prefix="test",
        dedupe_in_memory=True,
    )
    assert n == 1
    assert _row_count() == 1
