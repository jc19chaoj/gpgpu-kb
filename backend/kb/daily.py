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
    # `run_ingestion` returns a flat dict mixing per-source ingest counts
    # (arxiv / blogs / sitemap_blogs / github → "new items added to DB")
    # with side-effect counters from the tail steps (e.g.
    # ``fulltext_prefetched`` → "rows whose full_text cache was populated
    # this run", which retroactively backfills HISTORIC blog/project rows
    # and is NOT a new-item count). Naively summing all values double-
    # counts those side-effect totals into the headline "new items"
    # number — the symptom is e.g. "新增条目：32 / 处理完成：2" where
    # 30 of the "new" items are actually existing rows that just got
    # their full_text filled in. Track the two cohorts separately.
    _INGEST_SOURCE_KEYS: tuple[str, ...] = ("arxiv", "blogs", "sitemap_blogs", "github")
    new_items_total = sum(results.get(k, 0) for k in _INGEST_SOURCE_KEYS)

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

    fulltext_prefetched = results.get("fulltext_prefetched", 0)

    print("\n" + "=" * 60)
    print(_t("  Pipeline complete!", "  流水线完成！"))
    print(_t(f"  New items: {new_items_total}",
             f"  新增条目：{new_items_total}"))
    print(_t(f"  Processed: {processed}", f"  处理完成：{processed}"))
    print(_t(f"  Indexed: {indexed}", f"  向量化完成：{indexed}"))
    # Side-effect counter for transparency. Hidden when zero so a normal
    # incremental run isn't visually noisier — only shown after a backfill
    # or a freshly-added source where it carries useful signal.
    if fulltext_prefetched:
        print(_t(f"  Full-text backfilled: {fulltext_prefetched}",
                 f"  全文回填：{fulltext_prefetched}"))
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
    # httpx logs every request at INFO ("HTTP Request: GET ... 200 OK"), which
    # buries our own pipeline logs and surfaces non-actionable 4xx noise from
    # bot-walled hosts (openai.com returns 403 to every fulltext prefetch).
    # Our code already gracefully degrades, so the HTTP layer only needs WARNING+.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    if settings.language != "en":
        logger.info("Language set to %s", settings.language)

    run_daily_pipeline()
