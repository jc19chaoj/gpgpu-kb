"""Tests for kb.processing.pdf — PDF download + text extraction + caching."""
from __future__ import annotations

import datetime

import pytest


def _seed_paper(*, url: str, pdf_url: str = "", abstract: str = "", summary: str = "", full_text: str = "") -> int:
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType

    db = SessionLocal()
    try:
        p = Paper(
            title="pdf-test",
            abstract=abstract,
            summary=summary,
            authors=["A"],
            organizations=[],
            source_type=SourceType.PAPER,
            source_name="arxiv",
            url=url,
            pdf_url=pdf_url,
            full_text=full_text,
            published_date=datetime.datetime(2026, 4, 25, tzinfo=datetime.UTC),
            is_processed=1,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        return p.id
    finally:
        db.close()


def test_fetch_full_text_returns_cached_when_present(client):
    """If `full_text` is already populated we return it and never hit the network."""
    from kb.processing import pdf as pdf_mod

    pid = _seed_paper(
        url="https://example.test/pdf-cached",
        pdf_url="https://example.test/pdf-cached.pdf",
        full_text="cached body content",
    )

    def _no_network(*_args, **_kw):
        raise AssertionError("network must not be called when full_text is cached")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pdf_mod, "_download_pdf", _no_network)
        text = pdf_mod.fetch_full_text(pid)

    assert text == "cached body content"


def test_fetch_full_text_downloads_and_caches(monkeypatch):
    from kb.processing import pdf as pdf_mod

    pid = _seed_paper(
        url="https://arxiv.org/abs/2401.12345",
        pdf_url="https://arxiv.org/pdf/2401.12345.pdf",
    )

    monkeypatch.setattr(pdf_mod, "_download_pdf", lambda url: b"pretend-bytes")
    monkeypatch.setattr(pdf_mod, "_extract_text", lambda blob: "extracted body text")

    text = pdf_mod.fetch_full_text(pid)
    assert text == "extracted body text"

    # Second call must hit the cache (no network), even after we re-monkeypatch
    # _download_pdf to blow up.
    monkeypatch.setattr(pdf_mod, "_download_pdf", lambda url: pytest.fail("should be cached"))
    assert pdf_mod.fetch_full_text(pid) == "extracted body text"


def test_fetch_full_text_falls_back_to_abstract_summary(monkeypatch):
    """When the URL doesn't look like a PDF we skip the download and use
    summary+abstract instead — and we do NOT poison the cache with the
    fallback text."""
    from kb.database import SessionLocal
    from kb.models import Paper
    from kb.processing import pdf as pdf_mod

    pid = _seed_paper(
        url="https://chipsandcheese.com/blog/post-foo",  # not a PDF
        pdf_url="",
        abstract="paper abstract",
        summary="curated summary",
    )

    monkeypatch.setattr(pdf_mod, "_download_pdf", lambda url: pytest.fail("must not download"))

    text = pdf_mod.fetch_full_text(pid)
    assert "curated summary" in text
    assert "paper abstract" in text

    # full_text column must remain empty so a future ingest of a real PDF
    # url will be allowed to populate the cache.
    db = SessionLocal()
    try:
        row = db.query(Paper).filter(Paper.id == pid).first()
        assert row is not None
        assert row.full_text == ""
    finally:
        db.close()


def test_fetch_full_text_handles_missing_paper():
    from kb.processing import pdf as pdf_mod
    assert pdf_mod.fetch_full_text(999_999) == ""


def test_fetch_full_text_falls_back_when_download_fails(monkeypatch):
    """Network failure → no cache write, abstract+summary fallback returned."""
    from kb.database import SessionLocal
    from kb.models import Paper
    from kb.processing import pdf as pdf_mod

    pid = _seed_paper(
        url="https://arxiv.org/abs/2401.99999",
        pdf_url="https://arxiv.org/pdf/2401.99999.pdf",
        abstract="fallback abstract",
        summary="fallback summary",
    )

    monkeypatch.setattr(pdf_mod, "_download_pdf", lambda url: None)

    text = pdf_mod.fetch_full_text(pid)
    assert "fallback abstract" in text
    assert "fallback summary" in text

    db = SessionLocal()
    try:
        row = db.query(Paper).filter(Paper.id == pid).first()
        assert row is not None
        assert row.full_text == "", "transient download failure must not poison the cache"
    finally:
        db.close()
