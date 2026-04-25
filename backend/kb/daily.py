#!/usr/bin/env python3
# kb/daily.py — Full daily pipeline
"""Run the complete daily pipeline: ingest -> process -> embed -> report."""

import logging

from kb.database import init_db
from kb.ingestion.run import run_ingestion
from kb.processing.llm import run_processing
from kb.processing.embeddings import index_unindexed_papers
from kb.reports import generate_daily_report

logger = logging.getLogger(__name__)


def run_daily_pipeline() -> None:
    print("=" * 60)
    print("  GPGPU Knowledge Base - Daily Pipeline")
    print("=" * 60)

    # Ensure schema exists. The FastAPI lifespan calls this for the API,
    # but the cron entrypoint runs without lifespan — the first DB hit
    # (now `_compute_days_back` in run_ingestion) would otherwise crash
    # on a fresh checkout.
    init_db()

    print("\n[1/4] INGESTION")
    results = run_ingestion()

    print("\n[2/4] PROCESSING (Summarization + Scoring)")
    processed = run_processing(batch_size=30)

    print("\n[3/4] EMBEDDING")
    indexed = index_unindexed_papers(batch_size=100)

    print("\n[4/4] DAILY REPORT")
    generate_daily_report()

    print("\n" + "=" * 60)
    print("  Pipeline complete!")
    print(f"  New items: {sum(results.values())}")
    print(f"  Processed: {processed}")
    print(f"  Indexed: {indexed}")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_daily_pipeline()
