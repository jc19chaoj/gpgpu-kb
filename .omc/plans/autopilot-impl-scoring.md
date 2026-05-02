# Implementation plan: per-source-type scoring (autopilot 2026-05-01)

## File-by-file changes

### 1. `backend/kb/models.py`
Add columns:
```python
quality_score = Column(Float, default=0.0, index=True)
relevance_score = Column(Float, default=0.0)
score_rationale = Column(Text, default="")
```

### 2. `backend/kb/database.py`
- Idempotent column migration in `init_db()` via `PRAGMA table_info(papers)`.
- Add `("ix_papers_quality_score", "papers", "quality_score")` to `_BACKCOMPAT_INDEXES`.

### 3. `backend/kb/schemas.py`
Extend `PaperOut` with `quality_score`, `relevance_score`, `score_rationale` (defaults so old rows tolerated).

### 4. `backend/kb/processing/llm.py` — biggest change
- Per-type rubrics dict (PAPER, BLOG, PROJECT, TALK).
- `summarize_and_score` always summarizes + always scores.
- JSON keys: `quality_score`, `relevance_score`, `score_rationale`.
- For paper: also mirror to `originality_score`/`impact_score`/`impact_rationale` AND apply quality gate.
- For non-paper: `is_processed=1` on parse success, `0` on failure (retry).

### 5. `backend/kb/main.py`
- sort_by regex extends to include `quality_score|relevance_score`.
- `/api/stats`: add `top_overall` (any source_type, sorted by quality_score).

### 6. `backend/kb/reports.py`
- Order by `max(Paper.quality_score, Paper.relevance_score)` desc (SQLite scalar MAX).
- Markdown line: type-appropriate label pair.

### 7. `backend/scripts/rescore_non_papers.py` (new)
CLI flags: `--dry-run`, `--limit`, `--source-type`.

### 8-10. Tests
- `test_processing_llm.py`: per-type rubric tests, low-score-still-processed for non-paper, paper mirror.
- `test_api_smoke.py`: new sort options + invalid sort rejection + top_overall.
- `test_reports.py`: non-paper inclusion.

### 11-12. Frontend
- `types.ts`: add new fields.
- `paper-card.tsx`: per-type score labels.

## Build order
models → database → schemas → llm.py → main.py → reports.py → backfill script → tests → frontend → run pytest + tsc → review.
