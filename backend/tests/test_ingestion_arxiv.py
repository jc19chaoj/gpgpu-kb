# tests/test_ingestion_arxiv.py
"""Tests for kb/ingestion/arxiv.py — no network, all patched."""
from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# conftest.py sets KB_DATABASE_URL before any kb.* import
from kb.ingestion.arxiv import fetch_recent_papers, save_papers, ARXIV_CATEGORIES
from kb.models import Paper, SourceType


def _make_result(entry_id: str, title: str, days_ago: float = 0) -> SimpleNamespace:
    """Build a fake arxiv.Result-like object."""
    published = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days_ago)
    return SimpleNamespace(
        entry_id=entry_id,
        title=title,
        summary="Some abstract text",
        authors=[SimpleNamespace(name="Alice"), SimpleNamespace(name="Bob")],
        categories=["cs.LG"],
        pdf_url=f"https://arxiv.org/pdf/{entry_id.split('/')[-1]}",
        published=published,
    )


# ---------------------------------------------------------------------------
# fetch_recent_papers
# ---------------------------------------------------------------------------

class TestFetchRecentPapers:
    def test_returns_papers_within_cutoff(self):
        fresh = _make_result("https://arxiv.org/abs/2401.00001", "Fresh Paper", days_ago=0)
        old   = _make_result("https://arxiv.org/abs/2401.00002", "Old Paper", days_ago=5)

        # client.results yields fresh then old; old triggers the break
        with patch("kb.ingestion.arxiv.arxiv.Client") as MockClient:
            instance = MockClient.return_value
            instance.results.return_value = iter([fresh, old])

            papers = fetch_recent_papers(days_back=1)

        # Only the fresh paper should survive the cutoff filter
        assert len(papers) == 1
        assert papers[0]["title"] == "Fresh Paper"
        assert papers[0]["source_type"] == SourceType.PAPER
        assert papers[0]["source_name"] == "arxiv"

    def test_dedup_across_categories(self):
        """Same URL returned by two different category queries must appear only once."""
        dup = _make_result("https://arxiv.org/abs/2401.99999", "Dup Paper", days_ago=0)

        with patch("kb.ingestion.arxiv.arxiv.Client") as MockClient:
            instance = MockClient.return_value
            # Every category query returns the same paper
            instance.results.return_value = iter([dup])

            # Patch ARXIV_CATEGORIES to just two entries to keep the test fast
            with patch("kb.ingestion.arxiv.ARXIV_CATEGORIES", ["cs.LG", "cs.AI"]):
                papers = fetch_recent_papers(days_back=1)

        urls = [p["url"] for p in papers]
        assert urls.count("https://arxiv.org/abs/2401.99999") == 1

    def test_failed_category_skipped_silently(self):
        with patch("kb.ingestion.arxiv.arxiv.Client") as MockClient:
            instance = MockClient.return_value
            instance.results.side_effect = RuntimeError("network error")

            with patch("kb.ingestion.arxiv.ARXIV_CATEGORIES", ["cs.LG"]):
                papers = fetch_recent_papers(days_back=1)

        assert papers == []

    def test_paper_fields_populated(self):
        result = _make_result("https://arxiv.org/abs/2401.00042", "Field Test", days_ago=0)
        result.authors = [SimpleNamespace(name="Carol")]

        with patch("kb.ingestion.arxiv.arxiv.Client") as MockClient:
            instance = MockClient.return_value
            instance.results.return_value = iter([result])

            with patch("kb.ingestion.arxiv.ARXIV_CATEGORIES", ["cs.LG"]):
                papers = fetch_recent_papers(days_back=1)

        assert len(papers) == 1
        p = papers[0]
        assert p["url"] == "https://arxiv.org/abs/2401.00042"
        assert p["authors"] == ["Carol"]
        assert p["pdf_url"].endswith("2401.00042")
        assert isinstance(p["published_date"], datetime.datetime)


# ---------------------------------------------------------------------------
# save_papers
# ---------------------------------------------------------------------------

class TestSavePapers:
    def _paper_dict(self, url: str, title: str = "Title") -> dict:
        return {
            "title": title,
            "authors": ["Author"],
            "organizations": [],
            "abstract": "Abstract",
            "url": url,
            "pdf_url": "",
            "source_type": SourceType.PAPER,
            "source_name": "arxiv",
            "published_date": datetime.datetime.now(datetime.UTC),
            "categories": [],
            "venue": "",
        }

    def test_saves_new_papers(self):
        from kb.database import SessionLocal
        papers = [
            self._paper_dict("https://arxiv.org/abs/save001"),
            self._paper_dict("https://arxiv.org/abs/save002"),
        ]
        count = save_papers(papers)
        assert count == 2

        db = SessionLocal()
        try:
            stored = db.query(Paper).filter(Paper.url.in_([
                "https://arxiv.org/abs/save001",
                "https://arxiv.org/abs/save002",
            ])).all()
            assert len(stored) == 2
        finally:
            db.close()

    def test_idempotent_on_duplicate_url(self):
        papers = [self._paper_dict("https://arxiv.org/abs/idem001", "Idem Paper")]

        first  = save_papers(papers)
        second = save_papers(papers)

        assert first == 1
        assert second == 0  # already exists, skip

    def test_skips_entry_without_url(self):
        p = self._paper_dict("")
        count = save_papers([p])
        assert count == 0

    def test_mixed_new_and_existing(self):
        existing_url = "https://arxiv.org/abs/mixed001"
        new_url      = "https://arxiv.org/abs/mixed002"

        save_papers([self._paper_dict(existing_url)])
        count = save_papers([
            self._paper_dict(existing_url),
            self._paper_dict(new_url),
        ])
        assert count == 1
