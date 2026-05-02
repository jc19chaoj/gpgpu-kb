"""Source full-text loader for source-anchored chat.

When a `/api/chat` request anchors a single paper via `paper_id`, we want to
feed the entire source content to the LLM rather than relying on RAG. For
arxiv (and any other PDF-bearing) rows we download the PDF and extract its
text once, caching the result on `Paper.full_text`. For non-PDF rows we fall
back to the curated `summary + abstract` so the prompt always has *some*
substance.
"""
from __future__ import annotations

import io
import logging

import httpx

from kb.database import SessionLocal
from kb.models import Paper

logger = logging.getLogger(__name__)

# Hard caps so a malformed URL can't take the API down.
_MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB
_DOWNLOAD_TIMEOUT_S = 30.0
# Truncate extracted text before persisting / before stuffing into the prompt
# so a 200-page survey paper doesn't OOM the LLM client. The chat endpoint
# applies its own additional cap before building the final prompt.
_MAX_EXTRACTED_CHARS = 120_000


def _download_pdf(url: str) -> bytes | None:
    """Best-effort PDF download. Returns None on any failure or oversize body."""
    try:
        with httpx.Client(timeout=_DOWNLOAD_TIMEOUT_S, follow_redirects=True) as client:
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
        from pypdf import PdfReader  # local import keeps import cost off the FastAPI hot path
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


def _abstract_fallback(paper: Paper) -> str:
    """Best non-PDF substitute when we can't / shouldn't fetch the PDF.

    Use summary first (LLM-curated), then abstract. Either alone is far better
    than an empty source-mode prompt.
    """
    parts: list[str] = []
    if paper.summary:
        parts.append(f"# Summary\n{paper.summary}")
    if paper.abstract:
        parts.append(f"# Abstract\n{paper.abstract}")
    return "\n\n".join(parts).strip()


def _looks_like_pdf_url(url: str | None) -> bool:
    if not url:
        return False
    lo = url.lower()
    return lo.endswith(".pdf") or "/pdf/" in lo or "arxiv.org/pdf" in lo


def fetch_full_text(paper_id: int) -> str:
    """Return the best available source text for `paper_id`.

    Caching strategy: if `paper.full_text` is non-empty we return it directly.
    Otherwise we attempt to download and extract from `paper.pdf_url` (or
    `paper.url` if it itself looks like a PDF). On success we persist the
    extracted text. On failure we return the abstract+summary fallback but
    do NOT persist it — that way a transient network error doesn't poison
    the cache.
    """
    db = SessionLocal()
    try:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if paper is None:
            return ""

        if paper.full_text:
            return paper.full_text

        pdf_url: str | None = None
        if _looks_like_pdf_url(paper.pdf_url):
            pdf_url = paper.pdf_url
        elif _looks_like_pdf_url(paper.url):
            pdf_url = paper.url

        if pdf_url:
            blob = _download_pdf(pdf_url)
            if blob:
                text = _extract_text(blob)
                if text:
                    text = text[:_MAX_EXTRACTED_CHARS]
                    paper.full_text = text
                    db.commit()
                    return text

        return _abstract_fallback(paper)
    finally:
        db.close()
