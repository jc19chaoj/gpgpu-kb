# kb/ingestion/github_trending.py
"""Fetch top trending GitHub projects across daily / weekly / monthly windows.

Scrapes https://github.com/trending — the same UI most engineers see — and
takes the top ``TOP_N_PER_PERIOD`` repos from each of the three timeframes
the page exposes (``daily`` / ``weekly`` / ``monthly``). Repos appearing in
multiple periods are returned once, with each period preserved as a
``trending-<period>`` tag in ``categories`` for downstream filtering.

Compared with the previous keyword-search implementation:
    * No ``KEYWORDS`` fanout — relevance scoring is deferred to the LLM
      stage (see ``kb.processing.llm.summarize_and_score``).
    * No GitHub Search API quota usage; the trending HTML endpoint is
      unauthenticated and stable.
    * No reliance on ``GITHUB_TOKEN`` for the fetch path.

Trending has no official API; we therefore depend on the page's HTML
structure. Failures (HTTP error, malformed markup, parser miss) fall
back to an empty list so the orchestrator continues with the other
sources unaffected.
"""
from __future__ import annotations

import datetime
import logging
import re
import time
from dataclasses import dataclass
from html import unescape

import httpx

from kb.database import SessionLocal
from kb.models import Paper, SourceType

logger = logging.getLogger(__name__)


TRENDING_URL = "https://github.com/trending"
PERIODS: tuple[str, ...] = ("daily", "weekly", "monthly")
TOP_N_PER_PERIOD = 10

_HTTP_TIMEOUT_S = 15.0
_USER_AGENT = "gpgpu-kb/1.0 (+github-trending-scraper)"
# Polite sleep between the three trending page GETs — the endpoint is rate
# limited at the IP level and three requests is well under any threshold,
# but a small spacer keeps us friendly under cron.
_INTER_PERIOD_SLEEP_S = 0.5


# Each trending repo lives inside ``<article class="Box-row">``. Within the
# block we extract:
#   - the first ``/owner/repo`` href (the heading link)
#   - ``<p class="...col-9...">`` description
#   - ``<span itemprop="programmingLanguage">`` language label
# Class names have been stable in GitHub's Primer markup for years; we
# nonetheless tolerate optional extra classes via "anywhere in class list"
# matching so a future cosmetic class change is unlikely to fully break us.
_ARTICLE_RE = re.compile(
    r'<article\b[^>]*class="[^"]*\bBox-row\b[^"]*"[^>]*>(.*?)</article>',
    re.IGNORECASE | re.DOTALL,
)
_OWNER_REPO_RE = re.compile(
    r'href="/([^/"\s]+)/([^/"\s#?]+)"',
    re.IGNORECASE,
)
_DESCRIPTION_RE = re.compile(
    r'<p\b[^>]*class="[^"]*\bcol-9\b[^"]*"[^>]*>(.*?)</p>',
    re.IGNORECASE | re.DOTALL,
)
_LANG_RE = re.compile(
    r'<span\b[^>]*itemprop="programmingLanguage"[^>]*>([^<]+)</span>',
    re.IGNORECASE,
)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class _Scraped:
    """Single repo extracted from one trending HTML page."""

    owner: str
    repo: str
    description: str
    language: str


def _clean_text(html_fragment: str) -> str:
    """Strip tags + collapse whitespace from a small HTML fragment."""
    no_tags = _TAG_STRIP_RE.sub(" ", html_fragment)
    return _WHITESPACE_RE.sub(" ", unescape(no_tags)).strip()


def _scrape_trending(client: httpx.Client, period: str) -> list[_Scraped]:
    """GET https://github.com/trending?since={period}; return top-N rows.

    Returns ``[]`` on any HTTP / parse failure rather than raising — the
    orchestrator wraps the whole stage in a try/except too, but failing
    closed here keeps a single bad period from poisoning the others.
    """
    try:
        resp = client.get(TRENDING_URL, params={"since": period})
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("[github] trending %s scrape failed: %s", period, e)
        return []

    html = getattr(resp, "text", "") or ""

    out: list[_Scraped] = []
    seen: set[tuple[str, str]] = set()
    for art in _ARTICLE_RE.finditer(html):
        block = art.group(1)
        m = _OWNER_REPO_RE.search(block)
        if not m:
            continue
        owner = unescape(m.group(1)).strip()
        repo = unescape(m.group(2)).strip()
        if not owner or not repo:
            continue
        key = (owner, repo)
        if key in seen:
            continue
        seen.add(key)

        desc_m = _DESCRIPTION_RE.search(block)
        description = _clean_text(desc_m.group(1)) if desc_m else ""

        lang_m = _LANG_RE.search(block)
        language = unescape(lang_m.group(1)).strip() if lang_m else ""

        out.append(_Scraped(owner=owner, repo=repo,
                            description=description, language=language))
        if len(out) >= TOP_N_PER_PERIOD:
            break

    logger.info("[github] trending %s: %d repos scraped", period, len(out))
    return out


def fetch_trending_repos(days_back: int | None = 2) -> list[dict]:
    """Top-N trending GitHub projects across daily / weekly / monthly windows.

    Iterates the three timeframes the public GitHub trending page exposes
    and keeps the top ``TOP_N_PER_PERIOD`` repos from each. Cross-period
    duplicates are merged into a single record whose ``categories`` lists
    every period it trended in (e.g. ``["trending-daily","trending-weekly"]``).

    ``days_back`` is accepted for orchestrator-signature parity with the
    other fetchers. The trending windows themselves are fixed by GitHub's
    UI (1 day / 7 days / 30 days roughly), so the parameter is logged but
    does not influence which repos are returned.
    """
    if days_back is None:
        # Lazy import to avoid the run.py ↔ github_trending.py top-level
        # circular dependency.
        from kb.ingestion.run import _lookback_for_source

        days_back = _lookback_for_source("github")
    logger.info(
        "[github] days_back=%s (informational; trending windows are fixed by "
        "GitHub UI: daily / weekly / monthly)",
        days_back,
    )

    # owner/repo -> (first scraped row, [periods it appeared in])
    by_repo: dict[tuple[str, str], tuple[_Scraped, list[str]]] = {}

    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": _USER_AGENT,
    }
    with httpx.Client(
        timeout=_HTTP_TIMEOUT_S,
        follow_redirects=True,
        headers=headers,
    ) as client:
        for idx, period in enumerate(PERIODS):
            for s in _scrape_trending(client, period):
                key = (s.owner, s.repo)
                if key not in by_repo:
                    by_repo[key] = (s, [period])
                else:
                    by_repo[key][1].append(period)
            # Polite spacer between trending GETs; skip after the last one.
            if idx < len(PERIODS) - 1:
                time.sleep(_INTER_PERIOD_SLEEP_S)

    repos: list[dict] = []
    now = datetime.datetime.now(datetime.UTC)
    for (owner, repo), (s, periods) in by_repo.items():
        full_name = f"{owner}/{repo}"
        categories = [f"trending-{p}" for p in periods]
        if s.language:
            # Lowercase language tag so it merges cleanly with topic-style
            # categories on other source types (e.g. "python" / "rust").
            categories.append(s.language.lower())

        repos.append({
            "title": full_name,
            "authors": [owner],
            # Without the metadata API we can't classify User vs Organization
            # reliably; leave organizations empty so we never mis-tag a user
            # as an org. Downstream search has `authors` to fall back on.
            "organizations": [],
            "abstract": s.description,
            "url": f"https://github.com/{full_name}",
            "pdf_url": "",
            "source_type": SourceType.PROJECT,
            "source_name": "github",
            # Trending HTML doesn't surface ``pushed_at``; using the ingest
            # moment is semantically "when we observed it as trending",
            # which is what surfaces this item in recency-sorted views.
            "published_date": now,
            "categories": categories,
            "venue": "",
        })

    logger.info("[github] %d unique trending repos fetched", len(repos))
    return repos


def save_repos(repos: list[dict]) -> int:
    """Save GitHub repos to DB, skip duplicates."""
    db = SessionLocal()
    new_count = 0
    seen: set[str] = set()
    try:
        for r in repos:
            url = r.get("url")
            if not url or url in seen:
                continue
            existing = db.query(Paper).filter(Paper.url == url).first()
            if existing:
                continue
            db.add(Paper(**r))
            seen.add(url)
            new_count += 1
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[github] save failed")
        raise
    finally:
        db.close()
    return new_count
