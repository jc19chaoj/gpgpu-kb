# backend/tests/test_reports.py
"""Tests for kb/reports.py — daily report generation and upsert."""
from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest


# ─── Helpers ──────────────────────────────────────────────────────

_YESTERDAY = datetime.date.today() - datetime.timedelta(days=1)


def _utc_dt(date: datetime.date, hour: int = 12) -> datetime.datetime:
    return datetime.datetime(date.year, date.month, date.day, hour, 0, 0, tzinfo=datetime.UTC)


def _seed_papers(db, count: int, date: datetime.date) -> list:
    """Insert `count` processed papers ingested on `date`."""
    from kb.models import Paper, SourceType

    papers = []
    for i in range(count):
        p = Paper(
            title=f"Report Test Paper {i}",
            abstract=f"Abstract {i}",
            authors=[f"Author{i}"],
            organizations=["Org"],
            source_type=SourceType.PAPER,
            source_name="arxiv",
            url=f"https://example.com/report-paper-{date.isoformat()}-{i}",
            ingested_date=_utc_dt(date),
            is_processed=1,
            summary=f"Summary of paper {i}",
            originality_score=float(i),
            impact_score=float(i),
        )
        db.add(p)
    db.commit()
    # Refresh to get IDs
    for p in db.query(Paper).filter(Paper.url.like(f"%report-paper-{date.isoformat()}%")).all():
        papers.append(p)
    return papers


# ─── Happy path: DailyReport row created with paper_ids ──────────


def test_generate_daily_report_creates_row_with_paper_ids():
    from kb.database import SessionLocal
    from kb.models import DailyReport
    import kb.reports as reports_mod

    # Use a unique date so previous test runs don't collide.
    test_date = _YESTERDAY - datetime.timedelta(days=100)

    db = SessionLocal()
    try:
        papers = _seed_papers(db, 5, test_date)
        paper_ids = {p.id for p in papers}
    finally:
        db.close()

    with patch.object(reports_mod, "call_llm", return_value="## Daily Report\nGreat findings today."):
        report = reports_mod.generate_daily_report(date=test_date)

    assert report is not None
    assert report.id is not None
    assert report.content == "## Daily Report\nGreat findings today."
    # All seeded paper IDs should appear in the report
    assert paper_ids.issubset(set(report.paper_ids))

    # Verify the row is in the DB
    db = SessionLocal()
    try:
        row = db.query(DailyReport).filter(DailyReport.id == report.id).first()
        assert row is not None
        assert paper_ids.issubset(set(row.paper_ids))
    finally:
        db.close()


# ─── Upsert: second call for same date updates content ────────────


def test_generate_daily_report_upsert_no_integrity_error():
    """Calling generate_daily_report twice for the same date must upsert, not raise."""
    from kb.database import SessionLocal
    from kb.models import DailyReport
    import kb.reports as reports_mod

    test_date = _YESTERDAY - datetime.timedelta(days=101)

    db = SessionLocal()
    try:
        _seed_papers(db, 3, test_date)
    finally:
        db.close()

    with patch.object(reports_mod, "call_llm", return_value="First content"):
        report1 = reports_mod.generate_daily_report(date=test_date)

    assert report1.content == "First content"
    first_id = report1.id

    # Second call for the same date — must not raise IntegrityError
    with patch.object(reports_mod, "call_llm", return_value="Updated content"):
        report2 = reports_mod.generate_daily_report(date=test_date)

    assert report2.content == "Updated content"
    # Same row updated, not a new one
    assert report2.id == first_id

    # Confirm DB state
    db = SessionLocal()
    try:
        rows = db.query(DailyReport).filter(DailyReport.id == first_id).all()
        assert len(rows) == 1
        assert rows[0].content == "Updated content"
    finally:
        db.close()


# ─── Empty case: no papers → placeholder content ──────────────────


def test_generate_daily_report_empty_db_returns_placeholder():
    """When no papers are processed at all, report contains the 'No new papers' placeholder."""
    from kb.models import DailyReport
    import kb.reports as reports_mod

    future_date = datetime.date(2099, 12, 30)

    # Build a minimal fake session: queries return no papers and no existing
    # report; add/commit/refresh work for the DailyReport upsert path.
    created_reports = []

    class _FakeQuery:
        def __init__(self, model):
            self._model = model

        def filter(self, *a, **kw):
            return self

        def order_by(self, *a, **kw):
            return self

        def limit(self, *a):
            return self

        def first(self):
            return None

        def all(self):
            return []

    class _FakeSession:
        def query(self, model):
            return _FakeQuery(model)

        def add(self, obj):
            created_reports.append(obj)

        def commit(self):
            # Assign a fake id so refresh doesn't fail
            for obj in created_reports:
                if not getattr(obj, "id", None):
                    obj.id = 9999

        def refresh(self, obj):
            pass

        def close(self):
            pass

    with patch.object(reports_mod, "call_llm", return_value="should not be called") as mock_llm, \
         patch.object(reports_mod, "SessionLocal", return_value=_FakeSession()):
        report = reports_mod.generate_daily_report(date=future_date)

    mock_llm.assert_not_called()
    assert report is not None
    assert "No new papers" in report.content
    assert future_date.isoformat() in report.content
