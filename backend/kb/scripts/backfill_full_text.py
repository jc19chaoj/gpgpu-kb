#!/usr/bin/env python3
"""One-shot backfill: populate `Paper.full_text` for non-PDF rows that
pre-date the HTML / GitHub fulltext loaders.

Targets rows where:
    - source_type ∈ {blog, project, talk}
    - is_processed ∈ {1, 2}      (already processed at least once)
    - full_text is empty

PDF rows are skipped — their fulltext is lazy-loaded on first chat. This
script does NOT re-score anything (populating full_text is a cheap HTTP
fetch; re-scoring against the new body costs LLM tokens). To reflect the
new bodies in scores, run after this:

    python -m kb.scripts.rescore_non_papers --include-already-scored

Usage:
    python -m kb.scripts.backfill_full_text --dry-run
    python -m kb.scripts.backfill_full_text --limit 50
    python -m kb.scripts.backfill_full_text --source-type blog
"""
from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from kb.database import SessionLocal, init_db
from kb.models import Paper, SourceType
from kb.processing.fulltext import _ensure_cached


logger = logging.getLogger(__name__)


_NON_PAPER_TYPES = (SourceType.BLOG, SourceType.PROJECT, SourceType.TALK)
# Mirror the ingest-tail concurrency cap; same rate-limit reasoning.
_BACKFILL_WORKERS = 4


def _eligible_query(db, source_type: SourceType | None):
    types = [source_type] if source_type else list(_NON_PAPER_TYPES)
    return (
        db.query(Paper.id, Paper.title, Paper.url)
        .filter(Paper.source_type.in_(types))
        .filter(Paper.is_processed.in_([1, 2]))
        .filter(Paper.full_text == "")
        .order_by(Paper.id.asc())
    )


def _populate_one(paper_id: int) -> bool:
    """Worker thunk: run the cache-populator and report success."""
    try:
        return _ensure_cached(paper_id)
    except Exception:
        logger.exception("_ensure_cached raised for paper.id=%d", paper_id)
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="List eligible rows without fetching")
    parser.add_argument("--limit", type=int, default=None, help="Cap number of rows processed")
    parser.add_argument(
        "--source-type",
        choices=[t.value for t in _NON_PAPER_TYPES],
        default=None,
        help="Only backfill one source type",
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
        q = _eligible_query(db, src_filter)
        if args.limit is not None:
            q = q.limit(args.limit)
        rows = q.all()
    finally:
        db.close()

    if not rows:
        print("No eligible rows.")
        return 0

    print(f"Found {len(rows)} eligible row(s).")
    if args.dry_run:
        for pid, title, url in rows:
            title_str = (title or "")[:60]
            print(f"  paper.id={pid}  {title_str!r:<62}  {url}")
        print("[dry-run] No changes written.")
        return 0

    ids = [r[0] for r in rows]
    workers = min(_BACKFILL_WORKERS, len(ids))
    ok = 0
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="kb-backfill") as pool:
        futures = {pool.submit(_populate_one, pid): pid for pid in ids}
        for fut in as_completed(futures):
            pid = futures[fut]
            try:
                if fut.result():
                    ok += 1
                    print(f"  populated paper.id={pid}")
                else:
                    print(f"  skipped   paper.id={pid} (extract failed; fallback only)")
            except Exception:
                logger.exception("backfill worker raised for paper.id=%d", pid)

    print(f"Done. {ok}/{len(rows)} populated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
