#!/usr/bin/env python3
"""One-shot backfill: rescore non-paper rows on the universal axes.

Before the per-source-type scoring system landed, blog/project/talk rows were
marked is_processed=1 with quality_score/relevance_score = 0.0 (they bypassed
the paper-centric rubric entirely). This script finds those rows and runs the
new scoring on them so they participate in the unified sort and daily report.

Usage:
    python -m kb.scripts.rescore_non_papers --dry-run
    python -m kb.scripts.rescore_non_papers --limit 50
    python -m kb.scripts.rescore_non_papers --source-type blog
"""
from __future__ import annotations

import argparse
import logging
import sys

from kb.database import SessionLocal, init_db
from kb.models import Paper, SourceType
from kb.processing.llm import summarize_and_score


logger = logging.getLogger(__name__)


_NON_PAPER_TYPES = (SourceType.BLOG, SourceType.PROJECT, SourceType.TALK)


def _eligible_query(db, source_type: SourceType | None, include_already_scored: bool):
    """Rows that pre-date the universal scoring system: non-paper, processed,
    but with the new score axis still at the column default.

    `include_already_scored=True` drops the `quality_score == 0.0` filter
    so rows with prior scores are re-scored too — useful after running
    `backfill_full_text` to refresh scores against the newly cached
    article bodies."""
    types = [source_type] if source_type else list(_NON_PAPER_TYPES)
    q = (
        db.query(Paper.id)
        .filter(Paper.source_type.in_(types))
        .filter(Paper.is_processed == 1)
    )
    if not include_already_scored:
        q = q.filter(Paper.quality_score == 0.0)
    return q.order_by(Paper.id.asc())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="List eligible rows without rescoring")
    parser.add_argument("--limit", type=int, default=None, help="Cap number of rows processed")
    parser.add_argument(
        "--source-type",
        choices=[t.value for t in _NON_PAPER_TYPES],
        default=None,
        help="Only rescore one source type",
    )
    parser.add_argument(
        "--include-already-scored",
        action="store_true",
        help=(
            "Also re-score rows whose quality_score is already non-zero. "
            "Useful after `backfill_full_text` to refresh scores against "
            "newly cached article bodies."
        ),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    init_db()

    src_filter = SourceType(args.source_type) if args.source_type else None

    db = SessionLocal()
    try:
        q = _eligible_query(db, src_filter, args.include_already_scored)
        if args.limit is not None:
            q = q.limit(args.limit)
        ids = [row[0] for row in q.all()]
    finally:
        db.close()

    if not ids:
        print("No eligible rows.")
        return 0

    print(f"Found {len(ids)} eligible row(s).")
    if args.dry_run:
        for pid in ids:
            print(f"  paper.id={pid}")
        print("[dry-run] No changes written.")
        return 0

    ok = 0
    for pid in ids:
        try:
            if summarize_and_score(pid):
                ok += 1
                print(f"  rescored paper.id={pid}")
            else:
                print(f"  skipped paper.id={pid} (LLM failed; will retry next run)")
        except Exception:
            logger.exception("Rescoring paper.id=%d raised", pid)

    print(f"Done. {ok}/{len(ids)} rescored.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
