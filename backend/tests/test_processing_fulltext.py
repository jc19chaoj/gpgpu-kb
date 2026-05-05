"""Tests for kb.processing.fulltext — PDF / HTML / GitHub README loaders + caching."""
from __future__ import annotations

import datetime

import pytest


def _seed_paper(
    *,
    url: str,
    pdf_url: str = "",
    abstract: str = "",
    summary: str = "",
    full_text: str = "",
    source_type=None,
    source_name: str = "arxiv",
    is_processed: int = 1,
) -> int:
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType

    db = SessionLocal()
    try:
        p = Paper(
            title="ft-test",
            abstract=abstract,
            summary=summary,
            authors=["A"],
            organizations=[],
            source_type=source_type or SourceType.PAPER,
            source_name=source_name,
            url=url,
            pdf_url=pdf_url,
            full_text=full_text,
            published_date=datetime.datetime(2026, 4, 25, tzinfo=datetime.UTC),
            is_processed=is_processed,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        return p.id
    finally:
        db.close()


# ─── PDF path (preserved from pre-rename test_processing_pdf.py) ────


def test_fetch_full_text_returns_cached_when_present(client):
    """If `full_text` is already populated we return it and never hit the network."""
    from kb.processing import fulltext as ft_mod

    pid = _seed_paper(
        url="https://example.test/pdf-cached",
        pdf_url="https://example.test/pdf-cached.pdf",
        full_text="cached body content",
    )

    def _no_network(*_args, **_kw):
        raise AssertionError("network must not be called when full_text is cached")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ft_mod, "_download_pdf", _no_network)
        mp.setattr(ft_mod, "_fetch_html_article", _no_network)
        mp.setattr(ft_mod, "_fetch_github_readme", _no_network)
        text = ft_mod.fetch_full_text(pid)

    assert text == "cached body content"


def test_fetch_full_text_downloads_and_caches_pdf(monkeypatch):
    from kb.processing import fulltext as ft_mod

    pid = _seed_paper(
        url="https://arxiv.org/abs/2401.12345",
        pdf_url="https://arxiv.org/pdf/2401.12345.pdf",
    )

    monkeypatch.setattr(ft_mod, "_download_pdf", lambda url: b"pretend-bytes")
    monkeypatch.setattr(ft_mod, "_extract_text", lambda blob: "extracted body text")

    text = ft_mod.fetch_full_text(pid)
    assert text == "extracted body text"

    # Second call must hit the cache (no network), even after _download_pdf is rigged to blow up.
    monkeypatch.setattr(ft_mod, "_download_pdf", lambda url: pytest.fail("should be cached"))
    assert ft_mod.fetch_full_text(pid) == "extracted body text"


def test_fetch_full_text_falls_back_to_abstract_summary_when_no_loader_succeeds(monkeypatch):
    """When extraction fails we use summary+abstract — and we do NOT poison
    the cache with the fallback text."""
    from kb.database import SessionLocal
    from kb.models import Paper
    from kb.processing import fulltext as ft_mod

    pid = _seed_paper(
        url="https://chipsandcheese.com/blog/post-foo",  # not a PDF
        pdf_url="",
        abstract="paper abstract",
        summary="curated summary",
    )

    # HTML extractor returns "" (e.g. trafilatura missing) → fall back.
    monkeypatch.setattr(ft_mod, "_fetch_html_article", lambda url: "")
    monkeypatch.setattr(
        ft_mod,
        "_download_pdf",
        lambda url: pytest.fail("must not download PDFs for non-PDF urls"),
    )

    text = ft_mod.fetch_full_text(pid)
    assert "curated summary" in text
    assert "paper abstract" in text

    db = SessionLocal()
    try:
        row = db.query(Paper).filter(Paper.id == pid).first()
        assert row is not None
        assert row.full_text == ""
    finally:
        db.close()


def test_fetch_full_text_handles_missing_paper():
    from kb.processing import fulltext as ft_mod
    assert ft_mod.fetch_full_text(999_999) == ""


def test_fetch_full_text_falls_back_when_pdf_download_fails(monkeypatch):
    from kb.database import SessionLocal
    from kb.models import Paper
    from kb.processing import fulltext as ft_mod

    pid = _seed_paper(
        url="https://arxiv.org/abs/2401.99999",
        pdf_url="https://arxiv.org/pdf/2401.99999.pdf",
        abstract="fallback abstract",
        summary="fallback summary",
    )

    monkeypatch.setattr(ft_mod, "_download_pdf", lambda url: None)

    text = ft_mod.fetch_full_text(pid)
    assert "fallback abstract" in text
    assert "fallback summary" in text

    db = SessionLocal()
    try:
        row = db.query(Paper).filter(Paper.id == pid).first()
        assert row is not None
        assert row.full_text == "", "transient download failure must not poison the cache"
    finally:
        db.close()


# ─── HTML path (trafilatura) ────────────────────────────────────────


def test_fetch_full_text_extracts_html_article_for_blog_rows(monkeypatch):
    """A blog URL → no PDF / no GitHub → HTML extractor runs and the
    extracted body is cached on `full_text`."""
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType
    from kb.processing import fulltext as ft_mod

    pid = _seed_paper(
        url="https://chipsandcheese.com/blog/deep-dive",
        source_type=SourceType.BLOG,
        source_name="Chips and Cheese",
    )

    captured: dict[str, str] = {}

    def _fake_html(url: str) -> str:
        captured["url"] = url
        return "extracted blog body — multiple paragraphs of analysis"

    monkeypatch.setattr(ft_mod, "_fetch_html_article", _fake_html)

    text = ft_mod.fetch_full_text(pid)
    assert text == "extracted blog body — multiple paragraphs of analysis"
    assert captured["url"] == "https://chipsandcheese.com/blog/deep-dive"

    db = SessionLocal()
    try:
        row = db.query(Paper).filter(Paper.id == pid).first()
        assert row is not None
        assert row.full_text == text
    finally:
        db.close()


class _StreamResp:
    """Reusable httpx-stream stand-in: __enter__/__exit__ + iter_bytes."""

    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    def iter_bytes(self):
        yield from self._chunks


def test_fetch_html_article_calls_trafilatura(monkeypatch):
    """Internal: the HTML loader passes httpx-streamed bytes into trafilatura."""
    import sys
    import types

    from kb.processing import fulltext as ft_mod

    fake_module = types.ModuleType("trafilatura")

    def _fake_extract(html, **kwargs):
        assert "<p>hi</p>" in html, "downloaded body should reach trafilatura"
        # Sanity-check we passed the recall-favoring flag.
        assert kwargs.get("favor_recall") is True
        return "  trafilatura output  "

    fake_module.extract = _fake_extract  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "trafilatura", fake_module)

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def stream(self, method, url):
            assert method == "GET"
            return _StreamResp([b"<html><body><p>hi</p></body></html>"])

    monkeypatch.setattr(ft_mod.httpx, "Client", _FakeClient)

    out = ft_mod._fetch_html_article("https://example.test/post")
    assert out == "trafilatura output"


def test_fetch_html_article_returns_empty_on_http_error(monkeypatch):
    """Network failure → "" (caller falls back without poisoning cache)."""
    from kb.processing import fulltext as ft_mod

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def stream(self, method, url):
            raise ft_mod.httpx.ConnectError("network down")

    monkeypatch.setattr(ft_mod.httpx, "Client", _FakeClient)

    assert ft_mod._fetch_html_article("https://example.test/post") == ""


def test_fetch_html_article_aborts_on_oversize_body(monkeypatch):
    """Stream-and-abort: a body that crosses _MAX_HTML_BYTES mid-stream
    must short-circuit to "" without buffering the whole payload."""
    import sys
    import types

    from kb.processing import fulltext as ft_mod

    # trafilatura must NEVER be invoked when we abort early.
    fake_module = types.ModuleType("trafilatura")

    def _fake_extract(*a, **kw):
        raise AssertionError("trafilatura must not run on oversize bodies")

    fake_module.extract = _fake_extract  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "trafilatura", fake_module)

    monkeypatch.setattr(ft_mod, "_MAX_HTML_BYTES", 1024)

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def stream(self, method, url):
            # Three 600-byte chunks → after the second one we cross the
            # 1024-byte cap and the function must short-circuit.
            return _StreamResp([b"a" * 600, b"b" * 600, b"c" * 600])

    monkeypatch.setattr(ft_mod.httpx, "Client", _FakeClient)
    assert ft_mod._fetch_html_article("https://example.test/huge") == ""


# ─── GitHub README path ─────────────────────────────────────────────


def test_fetch_full_text_uses_github_readme_for_project_rows(monkeypatch):
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType
    from kb.processing import fulltext as ft_mod

    pid = _seed_paper(
        url="https://github.com/openai/triton",
        source_type=SourceType.PROJECT,
        source_name="github",
    )

    captured: dict[str, str] = {}

    def _fake_readme(url: str) -> str:
        captured["url"] = url
        return "# Triton\n\nAn open-source GPU programming language."

    # Make sure HTML path is not invoked for GitHub urls.
    monkeypatch.setattr(
        ft_mod,
        "_fetch_html_article",
        lambda url: pytest.fail("GitHub project must not call HTML extractor"),
    )
    monkeypatch.setattr(ft_mod, "_fetch_github_readme", _fake_readme)

    text = ft_mod.fetch_full_text(pid)
    assert text.startswith("# Triton")
    assert captured["url"] == "https://github.com/openai/triton"

    db = SessionLocal()
    try:
        row = db.query(Paper).filter(Paper.id == pid).first()
        assert row is not None
        assert row.full_text.startswith("# Triton")
    finally:
        db.close()


def test_fetch_github_readme_handles_404(monkeypatch):
    """Repo without a README → 404 → return "" so cache is untouched."""
    from kb.processing import fulltext as ft_mod

    class _FakeResp:
        status_code = 404
        content = b""

        def raise_for_status(self):  # not called on 404 path
            raise AssertionError("raise_for_status called on 404")

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url):
            return _FakeResp()

    monkeypatch.setattr(ft_mod.httpx, "Client", _FakeClient)

    assert ft_mod._fetch_github_readme("https://github.com/foo/bar") == ""


def test_fetch_github_readme_decodes_raw_markdown(monkeypatch):
    from kb.processing import fulltext as ft_mod

    class _FakeResp:
        status_code = 200
        content = "# Hello\n\nbody — ünîcode\n".encode("utf-8")

        def raise_for_status(self):
            pass

    class _FakeClient:
        def __init__(self, *a, **kw):
            self.kwargs = kw

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url):
            assert url == "https://api.github.com/repos/openai/triton/readme"
            return _FakeResp()

    monkeypatch.setattr(ft_mod.httpx, "Client", _FakeClient)

    out = ft_mod._fetch_github_readme("https://github.com/openai/triton")
    assert out.startswith("# Hello")
    assert "ünîcode" in out


def test_fetch_github_readme_returns_empty_for_non_github_url():
    from kb.processing import fulltext as ft_mod
    assert ft_mod._fetch_github_readme("https://example.com/not-github") == ""


# ─── Bulk prefetch ──────────────────────────────────────────────────


def test_prefetch_pending_full_text_only_targets_non_paper_rows(monkeypatch):
    """Prefetch ignores paper rows (their PDFs are heavy + lazy-loaded)
    and only touches blog/project/talk rows whose full_text is empty."""
    from kb.models import SourceType
    from kb.processing import fulltext as ft_mod

    blog_id = _seed_paper(
        url="https://chipsandcheese.com/blog/deep-dive-prefetch",
        source_type=SourceType.BLOG,
        source_name="Chips and Cheese",
        is_processed=0,
    )
    paper_id = _seed_paper(
        url="https://arxiv.org/abs/9999.00000",
        pdf_url="https://arxiv.org/pdf/9999.00000.pdf",
        source_type=SourceType.PAPER,
        source_name="arxiv",
        is_processed=0,
    )

    visited: list[int] = []

    real_ensure = ft_mod._ensure_cached

    def _spy_ensure(pid: int) -> bool:
        visited.append(pid)
        return real_ensure(pid)

    monkeypatch.setattr(ft_mod, "_ensure_cached", _spy_ensure)
    monkeypatch.setattr(
        ft_mod,
        "_fetch_html_article",
        lambda url: "html body for the blog row",
    )
    # If the prefetch ever tries to download a PDF the test fails — paper
    # rows must be excluded by source_type.
    monkeypatch.setattr(
        ft_mod,
        "_download_pdf",
        lambda url: pytest.fail("paper rows must be excluded from prefetch"),
    )

    n = ft_mod.prefetch_pending_full_text()
    assert n == 1
    assert blog_id in visited
    assert paper_id not in visited


def test_prefetch_pending_full_text_skips_already_filled(monkeypatch):
    """Idempotent: a row whose full_text is already populated isn't even
    in the eligible set, so the worker is never called for it."""
    from kb.models import SourceType
    from kb.processing import fulltext as ft_mod

    pid = _seed_paper(
        url="https://chipsandcheese.com/blog/already-filled-prefetch",
        source_type=SourceType.BLOG,
        source_name="Chips and Cheese",
        full_text="previously cached body",
        is_processed=1,
    )

    monkeypatch.setattr(
        ft_mod,
        "_ensure_cached",
        lambda pid: pytest.fail("must not re-fetch already-cached row"),
    )

    n = ft_mod.prefetch_pending_full_text()
    # Already-cached row isn't selected by the eligible-rows query.
    assert n == 0
    _ = pid


# ─── New regression test for the `.git` clone-URL stripping ─────────


def test_fetch_github_readme_strips_dot_git_suffix(monkeypatch):
    """A GitHub clone URL ending in `.git` must hit
    `/repos/owner/repo/readme`, not `/repos/owner/repo.git/readme`
    (which silently 404s on the real API)."""
    from kb.processing import fulltext as ft_mod

    captured: dict[str, str] = {}

    class _FakeResp:
        status_code = 200
        content = b"# README"

        def raise_for_status(self):
            pass

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url):
            captured["url"] = url
            return _FakeResp()

    monkeypatch.setattr(ft_mod.httpx, "Client", _FakeClient)

    out = ft_mod._fetch_github_readme("https://github.com/foo/bar.git")
    assert out == "# README"
    assert captured["url"] == "https://api.github.com/repos/foo/bar/readme"
