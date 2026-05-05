"""Source full-text loader for source-anchored chat *and* scoring.

Backed by `Paper.full_text` as a write-through cache. Three loader paths
are dispatched off the row's source/url:

  1. PDF rows (arxiv etc.)         → httpx download + pypdf extract.
  2. GitHub project rows           → REST API for the raw README.
  3. Anything else with a URL      → httpx GET + trafilatura article
                                     extraction (boilerplate stripped).

Each loader returns "" on any failure so callers can transparently fall
back to `summary + abstract` without poisoning the cache.

Public surface:
  * `fetch_full_text(paper_id)`            — single-row, cache-aware. Used
                                              by /api/chat[/stream] and as
                                              the unit of work below.
  * `prefetch_pending_full_text(...)`      — bulk parallel fill for non-
                                              paper rows whose `full_text`
                                              is still empty. Called as
                                              the tail of ingestion so
                                              scoring sees full content.
"""
from __future__ import annotations

import io
import logging
import re
from concurrent.futures import ThreadPoolExecutor

import httpx

from kb.config import settings
from kb.database import SessionLocal
from kb.models import Paper, SourceType

logger = logging.getLogger(__name__)


# ─── Caps & timeouts ──────────────────────────────────────────────
#
# `_MAX_EXTRACTED_CHARS` was 120k when the column held arxiv PDFs only.
# Bumped to 200k now that long READMEs (numpy, pytorch, etc.) and deep-
# dive blog posts share the same column.
_MAX_EXTRACTED_CHARS = 200_000

# Hard caps on raw download size — defensive against a misconfigured URL.
_MAX_PDF_BYTES = 20 * 1024 * 1024     # 20 MB
_MAX_HTML_BYTES = 8 * 1024 * 1024     # 8 MB (rendered articles rarely > 2 MB)
_MAX_README_BYTES = 4 * 1024 * 1024   # 4 MB

_PDF_TIMEOUT_S = 30.0
_HTML_TIMEOUT_S = 15.0
_GITHUB_TIMEOUT_S = 15.0

# Concurrency for the prefetch tail step. Conservative on purpose so we
# don't trip rate limits on small blog hosts (Chips and Cheese, Lilian
# Weng's GitHub Pages, etc.). The processing stage runs at 8 in parallel
# but it talks to one cloud LLM, not N origin servers.
_PREFETCH_WORKERS = 4

# Two User-Agent strings:
#
#   * `_HTML_USER_AGENT` — sent to **HTML article hosts** (`_fetch_html_article`).
#     A bare "gpgpu-kb/1.0 …" UA gets a blanket 403 from CDNs in front of
#     openai.com (and a few others), which used to spam the daily-pipeline log
#     with dozens of WARNING lines. A common desktop Chrome UA gets through
#     without changing TLS fingerprint or other signals — for any site that
#     still blocks it, the existing `try/except → ""` path keeps the cache
#     empty and the run uneventful.
#
#   * `_API_USER_AGENT` — sent to **api.github.com** (`_fetch_github_readme`)
#     and to PDF downloads. GitHub's API explicitly recommends a meaningful
#     UA identifying the integration, and PDF hosts (arxiv etc.) don't bot-
#     filter, so a project-identifying UA stays.
_HTML_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_API_USER_AGENT = "gpgpu-kb/1.0 (+fulltext-loader)"


# ─── PDF path (preserved from kb.processing.pdf) ──────────────────


def _looks_like_pdf_url(url: str | None) -> bool:
    if not url:
        return False
    lo = url.lower()
    return lo.endswith(".pdf") or "/pdf/" in lo or "arxiv.org/pdf" in lo


def _download_pdf(url: str) -> bytes | None:
    """Best-effort PDF download. Returns None on any failure or oversize body."""
    try:
        with httpx.Client(timeout=_PDF_TIMEOUT_S, follow_redirects=True) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                buf = bytearray()
                for chunk in resp.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > _MAX_PDF_BYTES:
                        logger.warning("PDF at %s exceeded %d bytes; aborting", url, _MAX_PDF_BYTES)
                        return None
                return bytes(buf)
    except httpx.HTTPError as e:
        logger.warning("PDF download failed for %s: %s", url, e)
        return None


def _extract_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes via pypdf. Empty string on failure."""
    try:
        from pypdf import PdfReader  # local import keeps cost off the FastAPI hot path
    except ImportError:
        logger.error("pypdf not installed; pip install pypdf")
        return ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        parts: list[str] = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception as e:  # one bad page shouldn't kill the whole doc
                logger.debug("PDF page extract failed: %s", e)
        return "\n\n".join(p for p in parts if p)
    except Exception as e:
        logger.warning("PDF parse failed: %s", e)
        return ""


# ─── HTML path (trafilatura) ──────────────────────────────────────


def _fetch_html_article(url: str) -> str:
    """Download an HTML page and extract its main article text.

    Uses trafilatura for boilerplate-stripped extraction (recommended by
    most production article-scraping workflows for Q4 / Q5 cleanliness).
    Returns "" on any download or parse failure.
    """
    try:
        import trafilatura  # type: ignore
    except ImportError:
        logger.error(
            "trafilatura not installed; install the optional 'fulltext' extras: "
            "pip install -e '.[fulltext]'"
        )
        return ""

    try:
        with httpx.Client(
            timeout=_HTML_TIMEOUT_S,
            follow_redirects=True,
            headers={
                "User-Agent": _HTML_USER_AGENT,
                # Mirror what a real browser sends — some bot filters check
                # the Accept-Language header alongside UA. Cheap to add.
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as client:
            # Stream + abort on oversize so an attacker-controlled URL
            # serving 500 MB cannot OOM the process before we get to
            # check the size. Mirrors `_download_pdf`.
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                buf = bytearray()
                for chunk in resp.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > _MAX_HTML_BYTES:
                        logger.warning(
                            "HTML page %s exceeds %d bytes; skipping fulltext extract",
                            url, _MAX_HTML_BYTES,
                        )
                        return ""
                # `errors="replace"` is defensive for the rare site that
                # serves invalid byte sequences in a UTF-8-declared body.
                html = buf.decode("utf-8", errors="replace")
    except httpx.HTTPStatusError as e:
        # 4xx = host explicitly refused us (bot wall, geofence, gone, etc.) —
        # retrying won't help, so demote to DEBUG to avoid log-spam from sites
        # like openai.com that aggressively bot-filter regardless of UA.
        # 5xx is server-side and worth seeing.
        sc = e.response.status_code
        log_fn = logger.debug if 400 <= sc < 500 else logger.warning
        log_fn("HTML fetch failed for %s: %s", url, e)
        return ""
    except httpx.HTTPError as e:
        # Timeout / DNS / connection-reset — transient, keep visible.
        logger.warning("HTML fetch failed for %s: %s", url, e)
        return ""

    try:
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            favor_recall=True,  # prefer keeping a borderline paragraph over dropping it
        )
    except Exception as e:
        logger.warning("trafilatura extract failed for %s: %s", url, e)
        return ""

    return (text or "").strip()


# ─── GitHub README path ───────────────────────────────────────────


_GITHUB_REPO_RE = re.compile(r"github\.com/([^/]+)/([^/?#]+)", re.IGNORECASE)


def _fetch_github_readme(url: str) -> str:
    """Resolve a github.com/owner/repo URL to the raw README via the REST API.

    Uses `Accept: application/vnd.github.raw` so we get plain markdown
    rather than the base64-wrapped JSON response. `KB_GITHUB_TOKEN` /
    `GITHUB_TOKEN` is forwarded if set — otherwise the unauthenticated
    rate limit (60 req/h per IP) applies, which is fine for the daily
    prefetch volume.
    """
    m = _GITHUB_REPO_RE.search(url)
    if not m:
        return ""
    owner = m.group(1).strip()
    # Strip trailing slash / fragment / query from the repo segment, and
    # the `.git` clone-URL suffix that makes `GET /repos/owner/repo.git/readme`
    # silently 404 against the real GitHub API.
    repo = m.group(2).strip().rstrip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        return ""

    api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    headers = {
        "Accept": "application/vnd.github.raw",
        "User-Agent": _API_USER_AGENT,
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    try:
        with httpx.Client(
            timeout=_GITHUB_TIMEOUT_S,
            follow_redirects=True,
            headers=headers,
        ) as client:
            resp = client.get(api_url)
            if resp.status_code == 404:
                logger.info("GitHub README missing for %s/%s", owner, repo)
                return ""
            resp.raise_for_status()
            blob = resp.content
            if len(blob) > _MAX_README_BYTES:
                # Mirror the PDF / HTML "oversize → return empty" policy.
                # Truncating mid-byte risks splitting a UTF-8 sequence and
                # produces an inconsistent cache write across the three
                # loader paths. The downstream `_MAX_EXTRACTED_CHARS` cap
                # in `fetch_full_text` is for *character* truncation of
                # successfully extracted text, not for raw bytes.
                logger.warning(
                    "GitHub README for %s/%s exceeds %d bytes; skipping",
                    owner, repo, _MAX_README_BYTES,
                )
                return ""
            return blob.decode("utf-8", errors="replace").strip()
    except httpx.HTTPStatusError as e:
        # Other 4xx (403 rate-limited, 451 unavailable, ...) are also non-
        # actionable from our side. Match the HTML loader's policy.
        sc = e.response.status_code
        log_fn = logger.debug if 400 <= sc < 500 else logger.warning
        log_fn("GitHub README fetch failed for %s/%s: %s", owner, repo, e)
        return ""
    except httpx.HTTPError as e:
        logger.warning("GitHub README fetch failed for %s/%s: %s", owner, repo, e)
        return ""


# ─── Dispatcher ───────────────────────────────────────────────────


def _abstract_fallback(paper: Paper) -> str:
    """Best non-extracted substitute when we can't / shouldn't fetch.

    Use summary first (LLM-curated), then abstract. Either alone is far
    better than an empty source-mode prompt.
    """
    parts: list[str] = []
    if paper.summary:
        parts.append(f"# Summary\n{paper.summary}")
    if paper.abstract:
        parts.append(f"# Abstract\n{paper.abstract}")
    return "\n\n".join(parts).strip()


def _extract_for_paper(paper: Paper) -> str:
    """Run the right loader for this row. Returns extracted text only —
    callers handle caching and abstract fallback. Empty string means "no
    extracted content; do NOT cache" (transient failures are indistinguish-
    able from "this URL really has no body" at this level)."""
    pdf_url: str | None = None
    if _looks_like_pdf_url(paper.pdf_url):
        pdf_url = paper.pdf_url
    elif _looks_like_pdf_url(paper.url):
        pdf_url = paper.url

    if pdf_url:
        blob = _download_pdf(pdf_url)
        if blob is None:
            return ""
        return _extract_text(blob)

    if (
        paper.source_type == SourceType.PROJECT
        and paper.url
        and "github.com/" in paper.url
    ):
        return _fetch_github_readme(paper.url)

    if paper.url:
        return _fetch_html_article(paper.url)

    return ""


def fetch_full_text(paper_id: int) -> str:
    """Return the best available source text for `paper_id`.

    Cache strategy: if `paper.full_text` is non-empty we return it
    directly. Otherwise we run the right loader, persist on success,
    and fall back to `_abstract_fallback` on failure WITHOUT writing —
    a transient network blip mustn't poison the cache.
    """
    db = SessionLocal()
    try:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if paper is None:
            return ""

        if paper.full_text:
            return paper.full_text

        text = _extract_for_paper(paper)
        if text:
            text = text[:_MAX_EXTRACTED_CHARS]
            paper.full_text = text
            db.commit()
            return text

        return _abstract_fallback(paper)
    finally:
        db.close()


# ─── Bulk prefetch (called as the tail of ingestion) ──────────────


# Source types we proactively prefetch at ingestion time. Papers (PDF)
# are excluded — fetching every arxiv PDF on every daily run would burn
# bandwidth, and the existing on-demand path in /api/chat already handles
# them lazily.
_PREFETCH_TYPES: tuple[SourceType, ...] = (
    SourceType.BLOG,
    SourceType.PROJECT,
    SourceType.TALK,
)


def _ensure_cached(paper_id: int) -> bool:
    """Single-session "fetch + cache, report whether cache was populated".

    Used as the prefetch worker. Mirrors `fetch_full_text` minus the
    abstract-fallback step — prefetch only cares whether real content
    was extracted into the cache, never about returning a string. One
    `SessionLocal` per call (versus the two `fetch_full_text` would
    require + a third re-query) keeps the 4-worker pool from piling
    up SQLite connections under load.
    """
    db = SessionLocal()
    try:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if paper is None:
            return False
        if paper.full_text:
            return True
        text = _extract_for_paper(paper)
        if text:
            text = text[:_MAX_EXTRACTED_CHARS]
            paper.full_text = text
            db.commit()
            return True
        return False
    finally:
        db.close()


def prefetch_pending_full_text(batch_size: int | None = None) -> int:
    """Populate `full_text` for non-paper rows where it's still empty.

    Idempotent — once a row has any cached body it's skipped on every
    subsequent call. Designed to be called as the tail of ingestion so
    the downstream scoring stage sees full article bodies / READMEs
    instead of the 200-char og:description / GitHub trending blurb.

    Returns the count of rows whose cache was actually populated. Rows
    where extraction failed silently (network blip, malformed HTML)
    leave the column empty so the next run can retry.
    """
    db = SessionLocal()
    try:
        q = (
            db.query(Paper.id)
            .filter(Paper.source_type.in_(list(_PREFETCH_TYPES)))
            .filter(Paper.full_text == "")
            .order_by(Paper.id.desc())
        )
        if batch_size is not None:
            q = q.limit(batch_size)
        ids = [row[0] for row in q.all()]
    finally:
        db.close()

    if not ids:
        logger.info("[fulltext] prefetch: 0 pending rows")
        return 0

    def _worker(pid: int) -> bool:
        try:
            return _ensure_cached(pid)
        except Exception:
            logger.exception("[fulltext] prefetch raised for paper.id=%d", pid)
            return False

    workers = min(_PREFETCH_WORKERS, len(ids))
    n_ok = 0
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="kb-fulltext") as pool:
        for ok in pool.map(_worker, ids):
            if ok:
                n_ok += 1

    logger.info("[fulltext] prefetch: %d/%d rows populated", n_ok, len(ids))
    return n_ok
