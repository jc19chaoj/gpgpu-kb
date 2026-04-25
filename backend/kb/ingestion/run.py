# kb/ingestion/run.py
"""Run all ingestion pipelines. Called by cron job."""
import logging

from kb.ingestion.arxiv import fetch_recent_papers, save_papers
from kb.ingestion.rss import fetch_recent_posts, save_posts
from kb.ingestion.github_trending import fetch_trending_repos, save_repos

logger = logging.getLogger(__name__)


def run_ingestion(days_back: int = 1) -> dict[str, int]:
    """Run all ingestion sources. Returns counts."""
    results: dict[str, int] = {}

    logger.info("[ingestion] Fetching ArXiv papers...")
    try:
        papers = fetch_recent_papers(days_back=days_back)
        results["arxiv"] = save_papers(papers)
    except Exception:
        logger.exception("[ingestion] arxiv stage failed")
        results["arxiv"] = 0
    logger.info("[ingestion]   %d new papers", results["arxiv"])

    logger.info("[ingestion] Fetching blog posts...")
    try:
        posts = fetch_recent_posts(days_back=days_back)
        results["blogs"] = save_posts(posts)
    except Exception:
        logger.exception("[ingestion] rss stage failed")
        results["blogs"] = 0
    logger.info("[ingestion]   %d new posts", results["blogs"])

    logger.info("[ingestion] Fetching GitHub repos...")
    try:
        repos = fetch_trending_repos()
        results["github"] = save_repos(repos)
    except Exception:
        logger.exception("[ingestion] github stage failed")
        results["github"] = 0
    logger.info("[ingestion]   %d new repos", results["github"])

    total = sum(results.values())
    logger.info("[ingestion] Done. %d total new items.", total)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_ingestion()
