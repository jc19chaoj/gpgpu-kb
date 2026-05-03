#!/usr/bin/env python3
# kb/daily.py — Full daily pipeline
"""Run the complete daily pipeline: ingest -> process -> embed -> report."""

import logging

from kb.config import settings
from kb.database import SessionLocal, init_db
from kb.ingestion.run import run_ingestion
from kb.models import Paper
from kb.processing.llm import run_processing
from kb.processing.embeddings import index_unindexed_papers
from kb.reports import generate_daily_report

logger = logging.getLogger(__name__)

# Per-run cap for the processing stage.
# Set to None to drain the entire `is_processed=0` backlog every run (no cap).
# Historically capped at 100 to bound API spend; operator preference is now to
# always run to completion. Cold-start detection still works the same way and
# becomes a no-op since both branches now use None.
_PROCESSING_BATCH_SIZE: int | None = None


def _t(en: str, zh: str) -> str:
    return zh if settings.language == "zh" else en


def _is_cold_start() -> bool:
    """True if no paper has ever been processed (is_processed != 0).

    Used to decide whether the per-run processing cap applies. We can't
    just check row count because ingestion may have just inserted hundreds
    of fresh `is_processed=0` rows.
    """
    db = SessionLocal()
    try:
        return db.query(Paper).filter(Paper.is_processed != 0).first() is None
    finally:
        db.close()


def _is_embedding_cold_start() -> bool:
    """True if no processed paper has been embedded yet.

    Kept for logging / observability only — the embedding stage no longer
    applies a per-run cap (operator preference is to always drain the
    entire `is_processed=1 AND chroma_id=""` backlog), so cold-start
    detection is informational.
    """
    db = SessionLocal()
    try:
        return db.query(Paper).filter(
            Paper.is_processed == 1,
            Paper.chroma_id != "",
        ).first() is None
    finally:
        db.close()


def run_daily_pipeline() -> None:
    print("=" * 60)
    print(_t("  GPGPU Knowledge Base - Daily Pipeline",
             "  GPGPU 知识库 - 每日流水线"))
    print("=" * 60)

    # Ensure schema exists. The FastAPI lifespan calls this for the API,
    # but the cron entrypoint runs without lifespan — the first DB hit
    # (now `_compute_days_back` in run_ingestion) would otherwise crash
    # on a fresh checkout.
    init_db()

    print(_t("\n[1/4] INGESTION", "\n[1/4] 数据采集"))
    results = run_ingestion()

    print(_t("\n[2/4] PROCESSING (Summarization + Scoring)",
             "\n[2/4] 处理（摘要 + 打分）"))
    cold_start = _is_cold_start()
    batch_size = None if cold_start else _PROCESSING_BATCH_SIZE
    if cold_start:
        logger.info("[processing] cold start detected — processing entire backlog")

    db = SessionLocal()
    try:
        pending_count = db.query(Paper).filter(Paper.is_processed == 0).count()
    finally:
        db.close()
    cap_label = "no cap" if batch_size is None else str(batch_size)
    logger.info(
        "[processing] %d papers pending in queue (cold_start=%s, cap=%s)",
        pending_count, cold_start, cap_label,
    )

    processed = run_processing(batch_size=batch_size)

    print(_t("\n[3/4] EMBEDDING", "\n[3/4] 向量化"))
    embed_cold_start = _is_embedding_cold_start()
    if embed_cold_start:
        logger.info("[embedding] cold start detected — indexing entire backlog")
    else:
        logger.info("[embedding] indexing entire pending backlog (no cap)")
    indexed = index_unindexed_papers(batch_size=None)

    print(_t("\n[4/4] DAILY REPORT", "\n[4/4] 每日简报"))
    generate_daily_report()

    print("\n" + "=" * 60)
    print(_t("  Pipeline complete!", "  流水线完成！"))
    print(_t(f"  New items: {sum(results.values())}",
             f"  新增条目：{sum(results.values())}"))
    print(_t(f"  Processed: {processed}", f"  处理完成：{processed}"))
    print(_t(f"  Indexed: {indexed}", f"  向量化完成：{indexed}"))
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GPGPU KB daily pipeline")
    parser.add_argument(
        "--lang",
        choices=["en", "zh"],
        default=None,
        help="Output language for LLM-generated content. Overrides KB_LANGUAGE env.",
    )
    args = parser.parse_args()

    if args.lang:
        settings.language = args.lang

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if settings.language != "en":
        logger.info("Language set to %s", settings.language)

    run_daily_pipeline()
