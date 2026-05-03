# kb/ingestion/sitemap_blog.py
"""Sitemap-driven blog scraper for sites that don't expose a native RSS feed.

Some otherwise high-value blogs (notably LMSYS / SGLang at lmsys.org) ship as
Next.js SPAs with no /feed.xml. They do, however, publish a sitemap.xml that
lists every post URL and a per-page server-rendered HTML payload with full
OpenGraph metadata. This module bridges those two: walk the sitemap, filter
by path prefix and `<lastmod>`, then fetch each candidate page once to extract
title / description / publish-date / author from `<meta property="og:*">` and
`<meta property="article:*">` tags.

Public API mirrors `kb.ingestion.rss.fetch_recent_posts` so the orchestrator
can hand the resulting dicts straight to `kb.ingestion.rss.save_posts` without
schema translation.
"""
from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass, field
from html import unescape
from xml.etree import ElementTree as ET

import httpx

from kb.models import SourceType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SitemapSource:
    """A single sitemap-backed blog source.

    Attributes:
        source_name: Human-readable label written to `Paper.source_name`.
        sitemap_url: Where to GET the sitemap.xml.
        path_prefix: Only sitemap `<loc>` entries that start with this prefix
            AND have additional path beyond it count as articles. We require
            "additional path" to skip the index page itself (e.g. .../blog/).
        default_categories: Static category labels stamped on every post —
            useful so search/filtering can target this source even though the
            page itself doesn't expose tags. Keep lowercase.
    """

    source_name: str
    sitemap_url: str
    path_prefix: str
    default_categories: tuple[str, ...] = field(default_factory=tuple)


# Verified live as of 2026-05.
# LMSYS hosts the official SGLang blog. Its Next.js site has no native RSS
# but every post is SSR'd with full og:* metadata, and sitemap.xml lists
# all article URLs with `<lastmod>` timestamps.
SITEMAP_SOURCES: list[SitemapSource] = [
    SitemapSource(
        source_name="LMSYS / SGLang Blog",
        sitemap_url="https://lmsys.org/sitemap.xml",
        path_prefix="https://lmsys.org/blog/",
        default_categories=("sglang", "lmsys"),
    ),
]


# ---------------------------------------------------------------------------
# Network configuration
# ---------------------------------------------------------------------------

_HTTP_TIMEOUT_S = 10.0
# Per-source budget so a stalling host can't dominate the daily pipeline.
# Practically this caps the number of articles ingested per run, but the next
# run will pick up older ones via the natural date-cutoff filter.
_MAX_ARTICLES_PER_SOURCE = 60
_USER_AGENT = "gpgpu-kb/1.0 (+sitemap-blog-ingester)"

# Sitemap XML namespace. Both lmsys and most Next.js sites emit the standard
# sitemaps.org namespace; we strip it via local-name matching to stay tolerant
# of feeds that omit it.
_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


# ---------------------------------------------------------------------------
# Sitemap parsing
# ---------------------------------------------------------------------------


def _local(tag: str) -> str:
    """Strip XML namespace from a tag name for tolerant matching."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _parse_iso_datetime(value: str) -> datetime.datetime | None:
    """Parse `<lastmod>` style timestamps (`YYYY-MM-DD` or full ISO 8601)."""
    if not value:
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(raw)
    except ValueError:
        # Date-only fallback — sitemaps frequently emit `2026-04-29`.
        try:
            d = datetime.date.fromisoformat(raw[:10])
        except ValueError:
            return None
        return datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    return dt


def _parse_loose_datetime(value: str) -> datetime.datetime | None:
    """Parse human-formatted publish dates seen in `article:published_time`.

    LMSYS emits `April 29, 2026` rather than ISO. Fall through to ISO first
    so well-behaved sites keep working without a special case.
    """
    if not value:
        return None
    iso = _parse_iso_datetime(value)
    if iso is not None:
        return iso
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            d = datetime.datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
        return d.replace(tzinfo=datetime.UTC)
    return None


def _parse_sitemap(xml_bytes: bytes) -> list[tuple[str, datetime.datetime | None]]:
    """Return [(loc, lastmod), ...] from a sitemap.xml byte payload.

    Returns an empty list on any parse failure — never raises. Tolerant of
    sitemaps that omit `<lastmod>` or use a non-default namespace.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.warning("[sitemap_blog] failed to parse sitemap XML: %s", e)
        return []

    out: list[tuple[str, datetime.datetime | None]] = []
    for url_node in root.iter():
        if _local(url_node.tag) != "url":
            continue
        loc = ""
        lastmod_raw = ""
        for child in url_node:
            name = _local(child.tag)
            if name == "loc":
                loc = (child.text or "").strip()
            elif name == "lastmod":
                lastmod_raw = (child.text or "").strip()
        if not loc:
            continue
        out.append((loc, _parse_iso_datetime(lastmod_raw)))
    return out


# ---------------------------------------------------------------------------
# Per-page metadata extraction
# ---------------------------------------------------------------------------


# Match `<meta property="og:title" content="..." />` and the `name=` variant
# Twitter cards use. We tolerate any attribute order.
_META_RE = re.compile(
    r'<meta\s+[^>]*?(?:property|name)\s*=\s*"([^"]+)"\s+[^>]*?content\s*=\s*"([^"]*)"',
    re.IGNORECASE,
)
_META_RE_REVERSED = re.compile(
    r'<meta\s+[^>]*?content\s*=\s*"([^"]*)"\s+[^>]*?(?:property|name)\s*=\s*"([^"]+)"',
    re.IGNORECASE,
)


def _extract_meta(html: str) -> dict[str, str]:
    """Extract a flat {meta-name: content} map from raw HTML.

    Both attribute orders are accepted (`property="..." content="..."` and
    the reverse). Values are HTML-unescaped so `&amp;` etc. round-trip.
    Later occurrences of the same key win — pages occasionally repeat tags.
    """
    out: dict[str, str] = {}
    for match in _META_RE.finditer(html):
        out[match.group(1).lower()] = unescape(match.group(2))
    for match in _META_RE_REVERSED.finditer(html):
        # property/name in group 2, content in group 1 for the reversed regex.
        out[match.group(2).lower()] = unescape(match.group(1))
    return out


def _build_post(
    url: str,
    meta: dict[str, str],
    sitemap_lastmod: datetime.datetime | None,
    source: SitemapSource,
) -> dict | None:
    """Combine sitemap + page metadata into a save_posts-compatible dict.

    Returns None if the page lacks a title (the only field we genuinely
    can't fake — everything else has a sane fallback).
    """
    title = meta.get("og:title") or meta.get("twitter:title") or ""
    title = title.strip()
    if not title:
        return None

    description = (
        meta.get("og:description")
        or meta.get("twitter:description")
        or meta.get("description")
        or ""
    )

    published = _parse_loose_datetime(meta.get("article:published_time", ""))
    if published is None:
        published = sitemap_lastmod

    author_raw = meta.get("article:author", "").strip()
    if author_raw:
        # `Jiadong Guo, Xin Ji, Letian Ruan` → list[str].
        authors = [a.strip() for a in author_raw.split(",") if a.strip()]
    else:
        authors = []

    canonical_url = (meta.get("og:url") or url).strip() or url

    return {
        "title": title[:500],
        "authors": authors,
        "organizations": [],
        "abstract": description[:2000],
        "url": canonical_url,
        "pdf_url": "",
        "source_type": SourceType.BLOG,
        "source_name": source.source_name,
        "published_date": published,
        "categories": list(source.default_categories),
        "venue": "",
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def fetch_recent_sitemap_posts(days_back: int | None = 1) -> list[dict]:
    """Walk every configured sitemap source and return fresh post dicts.

    The result is shape-compatible with `kb.ingestion.rss.fetch_recent_posts`,
    so the orchestrator can call `kb.ingestion.rss.save_posts(posts)` on the
    combined list. Date filtering uses the more reliable of the two signals:
    sitemap `<lastmod>` first (cheap, no fetch), then `article:published_time`
    on the fetched HTML if `<lastmod>` was missing.

    `days_back` semantics:
        * int → applied uniformly to every configured `SitemapSource`
          (legacy behavior, useful for tests and one-off backfills).
        * None → each source gets its own per-`source_name` cold-start-aware
          window via `kb.ingestion.run._lookback_for_source`. A new entry in
          `SITEMAP_SOURCES` (no rows yet under that `source_name`) therefore
          auto-triggers a `settings.ingest_empty_db_days` backfill on its
          first daily run, while mature sources keep their tight window.
    """
    # Lazy import to avoid the run.py ↔ sitemap_blog.py circular: run.py
    # imports `fetch_recent_sitemap_posts` from this module at top level,
    # so a top-level back-import here would fail during partial load.
    from kb.ingestion.run import _lookback_for_source

    now = datetime.datetime.now(datetime.UTC)
    posts: list[dict] = []

    for source in SITEMAP_SOURCES:
        per_source_days = (
            days_back if days_back is not None
            else _lookback_for_source(source.source_name)
        )
        cutoff = now - datetime.timedelta(days=per_source_days)
        logger.info(
            "[sitemap_blog] %s: lookback=%dd", source.source_name, per_source_days
        )

        try:
            posts.extend(_fetch_one_source(source, cutoff))
        except Exception:
            # Per-source isolation: a malformed sitemap or a flaky host must
            # not poison the rest of the run.
            logger.exception("[sitemap_blog] %s: source failed", source.source_name)
            continue

    return posts


def _fetch_one_source(
    source: SitemapSource,
    cutoff: datetime.datetime,
) -> list[dict]:
    posts: list[dict] = []

    with httpx.Client(
        timeout=_HTTP_TIMEOUT_S,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT, "Accept": "*/*"},
    ) as client:
        try:
            sitemap_resp = client.get(source.sitemap_url)
            sitemap_resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning(
                "[sitemap_blog] %s: sitemap fetch failed (%s)",
                source.source_name,
                e,
            )
            return posts

        entries = _parse_sitemap(sitemap_resp.content)
        if not entries:
            logger.info("[sitemap_blog] %s: sitemap had no <url> entries", source.source_name)
            return posts

        candidates: list[tuple[str, datetime.datetime | None]] = []
        for loc, lastmod in entries:
            # Require the URL to live under path_prefix AND have additional
            # path beyond it — skips the blog index page itself.
            if not loc.startswith(source.path_prefix):
                continue
            if len(loc.rstrip("/")) <= len(source.path_prefix.rstrip("/")):
                continue
            # Cheap pre-filter: if sitemap says "this page hasn't moved since
            # before the cutoff", don't bother fetching it.
            if lastmod is not None and lastmod < cutoff:
                continue
            candidates.append((loc, lastmod))

        # Newest-first so the per-source budget keeps the most relevant items.
        candidates.sort(
            key=lambda t: t[1] or datetime.datetime.min.replace(tzinfo=datetime.UTC),
            reverse=True,
        )
        candidates = candidates[:_MAX_ARTICLES_PER_SOURCE]

        kept = 0
        for loc, lastmod in candidates:
            try:
                resp = client.get(loc)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning(
                    "[sitemap_blog] %s: GET %s failed (%s)",
                    source.source_name,
                    loc,
                    e,
                )
                continue

            meta = _extract_meta(resp.text)
            post = _build_post(loc, meta, lastmod, source)
            if post is None:
                logger.warning(
                    "[sitemap_blog] %s: no usable metadata at %s",
                    source.source_name,
                    loc,
                )
                continue

            # Second-chance date filter: if sitemap lacked <lastmod>, the
            # article:published_time we just parsed might still be older
            # than the cutoff window — drop it now.
            published = post.get("published_date")
            if published is not None and published < cutoff:
                continue

            posts.append(post)
            kept += 1

    logger.info("[sitemap_blog] %s: %d posts", source.source_name, kept)
    return posts
