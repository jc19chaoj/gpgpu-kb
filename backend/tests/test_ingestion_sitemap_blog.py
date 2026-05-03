# tests/test_ingestion_sitemap_blog.py
"""Tests for kb/ingestion/sitemap_blog.py — no network, httpx.Client patched."""
from __future__ import annotations

import datetime
from unittest.mock import patch

import httpx
import pytest

from kb.ingestion.sitemap_blog import (
    SitemapSource,
    _build_post,
    _extract_meta,
    _parse_iso_datetime,
    _parse_loose_datetime,
    _parse_sitemap,
    fetch_recent_sitemap_posts,
)
from kb.models import SourceType


# ---------------------------------------------------------------------------
# Fake httpx.Client
# ---------------------------------------------------------------------------


class _FakeResp:
    """Just enough of httpx.Response for sitemap_blog: content/text/raise_for_status."""

    def __init__(self, body: bytes | str, status: int = 200, url: str = ""):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self._body = body
        self.status_code = status
        self._url = url

    @property
    def content(self) -> bytes:
        return self._body

    @property
    def text(self) -> str:
        return self._body.decode("utf-8", errors="replace")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}",
                request=httpx.Request("GET", self._url or "http://x"),
                response=httpx.Response(self.status_code, request=httpx.Request("GET", self._url or "http://x")),
            )


class _FakeClient:
    """Replaces `httpx.Client` for the duration of one test.

    `routes` maps URL → _FakeResp | Exception. Unmapped GETs raise
    httpx.RequestError so the production code's `except httpx.HTTPError`
    branch is exercised cleanly.
    """

    def __init__(self, routes: dict, **_kwargs):
        self.routes = routes
        self.requested: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url: str):
        self.requested.append(url)
        if url not in self.routes:
            raise httpx.RequestError(
                f"no fake route for {url}",
                request=httpx.Request("GET", url),
            )
        v = self.routes[url]
        if isinstance(v, BaseException):
            raise v
        return v


def _patch_client(routes: dict):
    """Helper: install a _FakeClient factory into the module under test."""
    fake = _FakeClient(routes)

    def factory(*args, **kwargs):
        return fake

    return patch("kb.ingestion.sitemap_blog.httpx.Client", side_effect=factory), fake


# ---------------------------------------------------------------------------
# _parse_iso_datetime
# ---------------------------------------------------------------------------


class TestParseIsoDatetime:
    def test_full_iso_with_z(self):
        dt = _parse_iso_datetime("2026-04-29T18:36:40.816Z")
        assert dt == datetime.datetime(2026, 4, 29, 18, 36, 40, 816_000, tzinfo=datetime.UTC)

    def test_full_iso_with_offset(self):
        dt = _parse_iso_datetime("2026-04-29T10:00:00+08:00")
        assert dt is not None and dt.tzinfo is not None

    def test_naive_iso_assumed_utc(self):
        dt = _parse_iso_datetime("2026-04-29T10:00:00")
        assert dt == datetime.datetime(2026, 4, 29, 10, 0, 0, tzinfo=datetime.UTC)

    def test_date_only_falls_through(self):
        dt = _parse_iso_datetime("2026-04-29")
        assert dt == datetime.datetime(2026, 4, 29, tzinfo=datetime.UTC)

    def test_garbage_returns_none(self):
        assert _parse_iso_datetime("not a date") is None

    def test_empty_returns_none(self):
        assert _parse_iso_datetime("") is None


# ---------------------------------------------------------------------------
# _parse_loose_datetime
# ---------------------------------------------------------------------------


class TestParseLooseDatetime:
    def test_iso_fast_path(self):
        assert _parse_loose_datetime("2026-04-29T10:00:00Z") is not None

    def test_lmsys_human_format(self):
        """LMSYS emits `article:published_time` like `April 29, 2026`."""
        dt = _parse_loose_datetime("April 29, 2026")
        assert dt == datetime.datetime(2026, 4, 29, tzinfo=datetime.UTC)

    def test_short_month(self):
        dt = _parse_loose_datetime("Apr 29, 2026")
        assert dt == datetime.datetime(2026, 4, 29, tzinfo=datetime.UTC)

    def test_unknown_format_returns_none(self):
        assert _parse_loose_datetime("yesterday") is None


# ---------------------------------------------------------------------------
# _parse_sitemap
# ---------------------------------------------------------------------------


_SITEMAP_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://lmsys.org/blog</loc><lastmod>2026-04-29T18:36:40.816Z</lastmod></url>
  <url><loc>https://lmsys.org/blog/2026-04-29-p2p-update</loc><lastmod>2026-04-29</lastmod></url>
  <url><loc>https://lmsys.org/blog/2026-04-25-deepseek-v4</loc><lastmod>2026-04-25</lastmod></url>
  <url><loc>https://lmsys.org/about</loc></url>
</urlset>
"""


class TestParseSitemap:
    def test_extracts_loc_and_lastmod(self):
        entries = _parse_sitemap(_SITEMAP_XML)
        urls = [loc for loc, _ in entries]
        assert "https://lmsys.org/blog/2026-04-29-p2p-update" in urls
        assert "https://lmsys.org/about" in urls
        # lastmod parsed where present
        for loc, lastmod in entries:
            if loc == "https://lmsys.org/blog/2026-04-29-p2p-update":
                assert lastmod == datetime.datetime(2026, 4, 29, tzinfo=datetime.UTC)
            if loc == "https://lmsys.org/about":
                assert lastmod is None

    def test_malformed_xml_returns_empty(self):
        assert _parse_sitemap(b"<not xml>") == []

    def test_no_url_nodes_returns_empty(self):
        empty = b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'
        assert _parse_sitemap(empty) == []


# ---------------------------------------------------------------------------
# _extract_meta
# ---------------------------------------------------------------------------


class TestExtractMeta:
    def test_property_then_content(self):
        html = '<meta property="og:title" content="Hello"/>'
        assert _extract_meta(html)["og:title"] == "Hello"

    def test_content_then_property(self):
        html = '<meta content="Hello" property="og:title"/>'
        assert _extract_meta(html)["og:title"] == "Hello"

    def test_name_attribute(self):
        html = '<meta name="description" content="abc"/>'
        assert _extract_meta(html)["description"] == "abc"

    def test_html_entity_unescaped(self):
        html = '<meta property="og:title" content="Foo &amp; Bar"/>'
        assert _extract_meta(html)["og:title"] == "Foo & Bar"

    def test_multiple_metas_collected(self):
        html = (
            '<meta property="og:title" content="T"/>'
            '<meta property="og:description" content="D"/>'
            '<meta property="article:author" content="Jane, John"/>'
        )
        meta = _extract_meta(html)
        assert meta["og:title"] == "T"
        assert meta["og:description"] == "D"
        assert meta["article:author"] == "Jane, John"


# ---------------------------------------------------------------------------
# _build_post
# ---------------------------------------------------------------------------


class TestBuildPost:
    def _src(self, **overrides) -> SitemapSource:
        return SitemapSource(
            source_name=overrides.get("source_name", "Test Blog"),
            sitemap_url=overrides.get("sitemap_url", "https://x/sitemap.xml"),
            path_prefix=overrides.get("path_prefix", "https://x/blog/"),
            default_categories=overrides.get("default_categories", ("test",)),
        )

    def test_full_metadata_to_dict(self):
        post = _build_post(
            url="https://x/blog/foo",
            meta={
                "og:title": "Hello",
                "og:description": "World",
                "og:url": "https://x/blog/foo/",
                "article:published_time": "April 29, 2026",
                "article:author": "Jane Doe, John Roe",
            },
            sitemap_lastmod=None,
            source=self._src(),
        )
        assert post is not None
        assert post["title"] == "Hello"
        assert post["abstract"] == "World"
        assert post["url"] == "https://x/blog/foo/"  # canonical via og:url
        assert post["authors"] == ["Jane Doe", "John Roe"]
        assert post["source_type"] == SourceType.BLOG
        assert post["source_name"] == "Test Blog"
        assert post["categories"] == ["test"]
        assert post["published_date"] == datetime.datetime(2026, 4, 29, tzinfo=datetime.UTC)

    def test_missing_title_returns_none(self):
        post = _build_post(
            url="https://x/blog/foo",
            meta={"og:description": "no title"},
            sitemap_lastmod=None,
            source=self._src(),
        )
        assert post is None

    def test_published_falls_back_to_sitemap_lastmod(self):
        lastmod = datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC)
        post = _build_post(
            url="https://x/blog/foo",
            meta={"og:title": "T"},
            sitemap_lastmod=lastmod,
            source=self._src(),
        )
        assert post is not None
        assert post["published_date"] == lastmod

    def test_loc_used_when_og_url_absent(self):
        post = _build_post(
            url="https://x/blog/foo",
            meta={"og:title": "T"},
            sitemap_lastmod=None,
            source=self._src(),
        )
        assert post is not None
        assert post["url"] == "https://x/blog/foo"


# ---------------------------------------------------------------------------
# fetch_recent_sitemap_posts (end-to-end with mocked httpx)
# ---------------------------------------------------------------------------


def _lmsys_post_html(
    title: str = "Updating 1T parameters in seconds",
    description: str = "RDMA-based weight transfer in SGLang.",
    pub: str = "April 29, 2026",
    author: str = "Jiadong Guo, Xin Ji",
    canonical: str = "https://lmsys.org/blog/2026-04-29-p2p-update/",
) -> str:
    return (
        f'<head>'
        f'<meta property="og:title" content="{title}"/>'
        f'<meta property="og:description" content="{description}"/>'
        f'<meta property="og:url" content="{canonical}"/>'
        f'<meta property="article:published_time" content="{pub}"/>'
        f'<meta property="article:author" content="{author}"/>'
        f'</head><body>...</body>'
    )


_TEST_SOURCE = SitemapSource(
    source_name="Test LMSYS",
    sitemap_url="https://lmsys.org/sitemap.xml",
    path_prefix="https://lmsys.org/blog/",
    default_categories=("sglang", "lmsys"),
)


def _build_sitemap(entries: list[tuple[str, str | None]]) -> bytes:
    """Build a sitemap.xml byte string from [(loc, lastmod_or_None), ...]."""
    body = ['<?xml version="1.0" encoding="UTF-8"?>']
    body.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for loc, lastmod in entries:
        body.append("<url>")
        body.append(f"<loc>{loc}</loc>")
        if lastmod:
            body.append(f"<lastmod>{lastmod}</lastmod>")
        body.append("</url>")
    body.append("</urlset>")
    return "".join(body).encode("utf-8")


@pytest.fixture
def lmsys_only(monkeypatch):
    """Pin SITEMAP_SOURCES to the test source so prod config can't drift in."""
    monkeypatch.setattr(
        "kb.ingestion.sitemap_blog.SITEMAP_SOURCES",
        [_TEST_SOURCE],
    )


class TestFetchRecentSitemapPosts:
    def test_happy_path(self, lmsys_only):
        sitemap = _build_sitemap([
            ("https://lmsys.org/blog", "2026-04-29"),                      # index, must skip
            ("https://lmsys.org/blog/2026-04-29-p2p-update", "2026-04-29"),
            ("https://lmsys.org/about", None),                             # off-prefix, must skip
        ])
        article_url = "https://lmsys.org/blog/2026-04-29-p2p-update"
        routes = {
            "https://lmsys.org/sitemap.xml": _FakeResp(sitemap),
            article_url: _FakeResp(_lmsys_post_html()),
        }
        ctx, fake = _patch_client(routes)
        with ctx:
            posts = fetch_recent_sitemap_posts(days_back=30)

        assert len(posts) == 1
        p = posts[0]
        assert p["title"].startswith("Updating 1T")
        assert p["source_type"] == SourceType.BLOG
        assert p["source_name"] == "Test LMSYS"
        assert p["categories"] == ["sglang", "lmsys"]
        assert p["authors"] == ["Jiadong Guo", "Xin Ji"]
        # canonical URL came from og:url, not the raw sitemap loc
        assert p["url"] == "https://lmsys.org/blog/2026-04-29-p2p-update/"
        assert p["published_date"] == datetime.datetime(2026, 4, 29, tzinfo=datetime.UTC)
        # The off-prefix `/about` and the `/blog` index were never fetched.
        assert "https://lmsys.org/about" not in fake.requested
        assert "https://lmsys.org/blog" not in fake.requested

    def test_sitemap_fetch_failure_returns_empty(self, lmsys_only):
        # No route for the sitemap → _FakeClient raises httpx.RequestError.
        ctx, _fake = _patch_client({})
        with ctx:
            posts = fetch_recent_sitemap_posts(days_back=30)
        assert posts == []

    def test_malformed_sitemap_returns_empty(self, lmsys_only):
        ctx, _fake = _patch_client({
            "https://lmsys.org/sitemap.xml": _FakeResp(b"<not xml>"),
        })
        with ctx:
            posts = fetch_recent_sitemap_posts(days_back=30)
        assert posts == []

    def test_lastmod_older_than_cutoff_skipped_without_fetch(self, lmsys_only):
        """`<lastmod>` lets us avoid GET-ing pages that haven't changed in
        ages — important for keeping daily runs cheap."""
        old_date = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=400)).date().isoformat()
        sitemap = _build_sitemap([
            ("https://lmsys.org/blog/very-old-post", old_date),
        ])
        ctx, fake = _patch_client({
            "https://lmsys.org/sitemap.xml": _FakeResp(sitemap),
        })
        with ctx:
            posts = fetch_recent_sitemap_posts(days_back=30)
        assert posts == []
        # We must NOT have requested the article body at all.
        assert "https://lmsys.org/blog/very-old-post" not in fake.requested

    def test_one_page_failure_does_not_kill_others(self, lmsys_only):
        good_url = "https://lmsys.org/blog/good-post"
        bad_url = "https://lmsys.org/blog/bad-post"
        sitemap = _build_sitemap([
            (good_url, "2026-04-29"),
            (bad_url, "2026-04-28"),
        ])
        routes = {
            "https://lmsys.org/sitemap.xml": _FakeResp(sitemap),
            good_url: _FakeResp(_lmsys_post_html(canonical=good_url)),
            # bad_url omitted → RequestError
        }
        ctx, _fake = _patch_client(routes)
        with ctx:
            posts = fetch_recent_sitemap_posts(days_back=30)
        assert len(posts) == 1
        assert posts[0]["url"] == good_url

    def test_page_without_title_skipped(self, lmsys_only):
        url = "https://lmsys.org/blog/no-title"
        sitemap = _build_sitemap([(url, "2026-04-29")])
        ctx, _fake = _patch_client({
            "https://lmsys.org/sitemap.xml": _FakeResp(sitemap),
            # HTML has og:description but no og:title
            url: _FakeResp('<meta property="og:description" content="..." />'),
        })
        with ctx:
            posts = fetch_recent_sitemap_posts(days_back=30)
        assert posts == []

    def test_secondary_cutoff_when_sitemap_lacks_lastmod(self, lmsys_only):
        """If `<lastmod>` is missing we still fetch, but the per-page
        `article:published_time` must enforce the cutoff."""
        url = "https://lmsys.org/blog/ancient"
        sitemap = _build_sitemap([(url, None)])
        ctx, _fake = _patch_client({
            "https://lmsys.org/sitemap.xml": _FakeResp(sitemap),
            url: _FakeResp(_lmsys_post_html(pub="January 1, 2020")),
        })
        with ctx:
            posts = fetch_recent_sitemap_posts(days_back=30)
        assert posts == []

    def test_published_falls_back_to_sitemap_lastmod_when_meta_missing(self, lmsys_only):
        """No `article:published_time` on the page → use sitemap `<lastmod>`."""
        url = "https://lmsys.org/blog/no-pub-meta"
        recent_iso = (
            datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
        ).date().isoformat()
        sitemap = _build_sitemap([(url, recent_iso)])
        # HTML missing article:published_time entirely.
        html = (
            '<meta property="og:title" content="No Pub Meta"/>'
            '<meta property="og:description" content="..." />'
        )
        ctx, _fake = _patch_client({
            "https://lmsys.org/sitemap.xml": _FakeResp(sitemap),
            url: _FakeResp(html),
        })
        with ctx:
            posts = fetch_recent_sitemap_posts(days_back=30)
        assert len(posts) == 1
        assert posts[0]["published_date"] is not None
        assert posts[0]["published_date"].date().isoformat() == recent_iso

    def test_per_source_cold_start_when_days_back_is_none(self, monkeypatch):
        """When called with `days_back=None`, each `SitemapSource` must use
        its own cold-start-aware lookback (`_lookback_for_source`) — so a
        brand-new sitemap source picks up `settings.ingest_empty_db_days`
        (default 30) even when other sources have very recent rows.

        Concretely: seed a row under "MatureSitemap" so its lookback is the
        tight gap (≈ 1 day) and leave "FreshSitemap" with no rows so it
        cold-starts. A 10-day-old article under each source should be
        DROPPED for the mature one but KEPT for the fresh one.
        """
        from kb.database import SessionLocal
        from kb.models import Paper

        mature_source = SitemapSource(
            source_name="MatureSitemap",
            sitemap_url="https://mature.example/sitemap.xml",
            path_prefix="https://mature.example/blog/",
            default_categories=("mature",),
        )
        fresh_source = SitemapSource(
            source_name="FreshSitemap",
            sitemap_url="https://fresh.example/sitemap.xml",
            path_prefix="https://fresh.example/blog/",
            default_categories=("fresh",),
        )
        monkeypatch.setattr(
            "kb.ingestion.sitemap_blog.SITEMAP_SOURCES",
            [mature_source, fresh_source],
        )

        db = SessionLocal()
        try:
            db.query(Paper).delete()
            db.add(Paper(
                title="seed",
                authors=[],
                organizations=[],
                abstract="",
                source_type=SourceType.BLOG,
                source_name="MatureSitemap",
                url="https://example.test/sitemap/seed-mature",
                ingested_date=datetime.datetime.now(datetime.UTC),
                published_date=datetime.datetime.now(datetime.UTC),
            ))
            db.commit()
        finally:
            db.close()

        ten_days_ago = (
            datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=10)
        ).date().isoformat()

        mature_url = "https://mature.example/blog/post-10d"
        fresh_url = "https://fresh.example/blog/post-10d"
        mature_sitemap = _build_sitemap([(mature_url, ten_days_ago)])
        fresh_sitemap = _build_sitemap([(fresh_url, ten_days_ago)])

        routes = {
            "https://mature.example/sitemap.xml": _FakeResp(mature_sitemap),
            "https://fresh.example/sitemap.xml": _FakeResp(fresh_sitemap),
            mature_url: _FakeResp(_lmsys_post_html(
                pub=ten_days_ago, canonical=mature_url,
            )),
            fresh_url: _FakeResp(_lmsys_post_html(
                pub=ten_days_ago, canonical=fresh_url,
            )),
        }

        try:
            ctx, fake = _patch_client(routes)
            with ctx:
                posts = fetch_recent_sitemap_posts(days_back=None)

            urls = {p["url"] for p in posts}
            # Mature source's lookback ≈ 1 day → 10-day-old <lastmod>
            # is dropped *before* fetching the article body.
            assert mature_url not in fake.requested
            # Fresh source cold-starts → 10-day-old article fits the
            # 30-day window and is kept.
            assert urls == {fresh_url}, (
                f"Expected only fresh-source post; got {urls}"
            )
        finally:
            db = SessionLocal()
            try:
                db.query(Paper).filter(
                    Paper.url == "https://example.test/sitemap/seed-mature"
                ).delete()
                db.commit()
            finally:
                db.close()
