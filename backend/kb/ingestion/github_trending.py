# kb/ingestion/github_trending.py
"""Fetch trending open-source projects via GitHub Search API."""
import datetime
import logging
import time

import httpx

from kb.config import settings
from kb.database import SessionLocal
from kb.models import Paper, SourceType

logger = logging.getLogger(__name__)

KEYWORDS = [
    "gpu", "cuda", "triton", "mlir", "transformer", "llm",
    "inference", "training", "benchmark", "compiler", "kernel",
    "attention", "quantization", "sparsity", "tpu", "npu",
    "deep-learning", "machine-learning",
]

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


def _build_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    else:
        logger.warning(
            "[github] No GITHUB_TOKEN set — unauthenticated rate limit is 10 req/min "
            "and the daily pipeline will likely 429. Set KB_GITHUB_TOKEN or GITHUB_TOKEN."
        )
    return headers


def fetch_trending_repos(days_back: int = 2) -> list[dict]:
    """Search GitHub for relevant repos pushed recently.

    `days_back` controls the `pushed:>YYYY-MM-DD` cutoff (default 2 keeps
    the original 2-day buffer for direct callers; the orchestrator passes
    the gap-derived value).
    """
    repos: list[dict] = []
    cutoff = (
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days_back)
    ).strftime("%Y-%m-%d")
    headers = _build_headers()

    with httpx.Client(timeout=15) as client:
        for keyword in KEYWORDS:
            try:
                resp = client.get(
                    GITHUB_SEARCH_URL,
                    params={
                        "q": f"{keyword} pushed:>{cutoff}",
                        "sort": "stars",
                        "order": "desc",
                        "per_page": 5,
                    },
                    headers=headers,
                )
                if resp.status_code == 403 and "rate limit" in resp.text.lower():
                    reset = resp.headers.get("X-RateLimit-Reset", "?")
                    logger.warning("[github] rate limited (resets at %s); aborting", reset)
                    break
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("items", []):
                    repos.append({
                        "title": item["full_name"],
                        "authors": [item["owner"]["login"]],
                        "organizations": (
                            [item["owner"]["login"]]
                            if item["owner"]["type"] == "Organization" else []
                        ),
                        "abstract": item.get("description") or "",
                        "url": item["html_url"],
                        "pdf_url": "",
                        "source_type": SourceType.PROJECT,
                        "source_name": "github",
                        "published_date": datetime.datetime.fromisoformat(
                            item["pushed_at"].replace("Z", "+00:00")
                        ),
                        "categories": item.get("topics", []),
                        "venue": "",
                    })
            except httpx.HTTPStatusError as e:
                logger.warning("[github] %s: HTTP %s", keyword, e.response.status_code)
            except Exception:
                logger.exception("[github] %s: unexpected error", keyword)
            # Be a polite citizen even with auth (5000 req/h is plenty but bursts can throttle)
            time.sleep(0.5)

    logger.info("[github] %d repo candidates fetched", len(repos))
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
