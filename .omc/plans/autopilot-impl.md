# Autopilot Implementation Plan: Fix Audit Issues (Batch 1)

**Generated**: 2026-04-25
**Scope**: Fix all issues from project audit (`#1`–`#37`) in a single batch
**Source spec**: Review report from prior turn (37 issues across 🔴 critical / 🟠 high / 🟡 medium / 🟢 polish)

---

## Scope decision

### In scope (this batch)
| Tier | Issues |
|------|--------|
| 🔴 Critical | #1 route order · #2 chat unauth/limits · #3 CORS · #4 prompt injection |
| 🟠 High | #5 GitHub auth · #6 dead RSS · #7 arxiv coverage · #8 embed singleton · #9 silent except · #10 datetime UTC · #11 daily-report upsert · #12 detached session · #13 SQL escape |
| 🟡 Medium | #15 server components (defer) · #16 indexes · #17 LLM provider abstraction · #18 /search alias · #19 SearchBar persistence · #22 score clamp |
| 🟢 Polish | #24 lifespan · #25 top-level import · #26 rename `_call_llm` · #27 cors env · #28 db url env · #29 .env.example · #31 sys.path · #32 header version · #36 embed model env · #37 (skip — schema invasive) |

### Deferred (with rationale)
- **#14 Server Components rewrite** — multi-day refactor; scope as separate plan
- **#20 Full test coverage** — add 5 smoke tests as foundation only
- **#21 Multi-turn chat** — needs product decision (single-turn RAG vs conversational)
- **#37 `is_processed` Enum** — schema-invasive; defer until Alembic in place
- **Alembic** — out of scope; instead add `CREATE INDEX IF NOT EXISTS` for backward-compat indexing on existing DB

---

## Files to change (15 files) and what changes

### Backend

#### `backend/kb/config.py`
- Expand Settings: `database_url`, `embedding_model`, `llm_provider`, `github_token`, `chat_query_max_len`, `chat_top_k_max`, `anthropic_api_key`, `openai_api_key`, `log_level`
- Keep `KB_` env prefix; default values unchanged for dev parity

#### `backend/kb/database.py`
- Read URL from `settings.database_url`
- Add `CREATE INDEX IF NOT EXISTS` calls in `init_db()` for backward compat (because `create_all` skips existing tables)
- Indexes: `papers.url` (unique), `papers.source_type`, `papers.is_processed`, `papers.impact_score`, `papers.ingested_date`

#### `backend/kb/models.py`
- Replace `datetime.datetime.utcnow` → tz-aware `_utcnow()` helper using `datetime.UTC`
- All `DateTime` columns → `DateTime(timezone=True)`
- Add `index=True` to: `url` (also `unique=True`), `source_type`, `is_processed`, `impact_score`, `ingested_date`
- Same UTC fix for `DailyReport.generated_date`

#### `backend/kb/schemas.py`
- `ChatRequest.query: str = Field(min_length=1, max_length=2000)`
- `ChatRequest.top_k: int = Field(5, ge=1, le=20)`
- `SearchRequest.query` same constraints

#### `backend/kb/main.py`
1. **Reorder routes**: `/api/papers/search` before `/api/papers/{paper_id}` — fixes #1 (404/422 bug)
2. Replace `@app.on_event("startup")` with `lifespan` async context manager (#24)
3. Pre-load embedding store in lifespan (mitigates #8 cold-start)
4. CORS: `allow_credentials=False`, `allow_methods=["GET", "POST"]`, origins from settings (#3, #27)
5. Top-level import of `call_llm` (#25)
6. Use renamed `call_llm` (#26)
7. Escape `%` and `_` in ILIKE patterns (#13)
8. Configure logging with `settings.log_level`

#### `backend/kb/processing/llm.py`
1. Rename `_call_llm` → `call_llm` (public) (#26)
2. Add provider abstraction: `KB_LLM_PROVIDER=hermes|anthropic|openai` (default: hermes)
   - `_call_hermes(prompt)`, `_call_anthropic(prompt)`, `_call_openai(prompt)`
   - Anthropic/OpenAI lazy-imported; raise clear error if not installed
3. Catch `subprocess.TimeoutExpired` explicitly + log
4. Sanitize untrusted content with `=== UNTRUSTED CONTENT START/END ===` delimiters in prompt (#4)
5. `clamp(value, 0.0, 10.0)` helper for scores; coerce non-numeric to 5.0 (#22)
6. Use `logging.getLogger(__name__)` instead of bare except `print` (#9)
7. Fix detached-session pattern: keep work inside one session scope (#12)

#### `backend/kb/processing/embeddings.py`
1. `threading.Lock` around singleton init (#8)
2. Embedding model name from `settings.embedding_model` (#36)
3. Use logger (#9)

#### `backend/kb/ingestion/arxiv.py`
1. Per-category query loop with own `MAX_RESULTS=50` (#7) — gives up to 9×50=450 candidates/day
2. `datetime.UTC` (#10)
3. Logger

#### `backend/kb/ingestion/rss.py`
1. Remove dead feeds: `openai/blog/rss.xml`, `anthropic.com/blog/rss.xml`, `distill.pub/feed.xml` (#6)
2. Add valid replacements: SemiAnalysis, ML Sys Wonderland, NVIDIA Developer Blog
3. Logger; keep error-skip but record cause
4. `datetime.UTC` (#10)

#### `backend/kb/ingestion/github_trending.py`
1. `Authorization: Bearer ${GITHUB_TOKEN}` from settings (#5)
2. `time.sleep(0.5)` between keywords; respect 429
3. Logger
4. `datetime.UTC` (#10)

#### `backend/kb/reports.py`
1. Upsert: query existing report by date, update or create (#11)
2. `datetime.UTC` (#10)
3. Use `call_llm` (renamed)
4. Logger

#### `backend/kb/daily.py`
- Remove `sys.path.insert` antipattern (#31)

#### `backend/pyproject.toml`
- Add `[project.optional-dependencies] dev` with `pytest`, `pytest-asyncio`, `httpx`
- Add optional `llm-cloud` group with `anthropic`, `openai`

#### `backend/.env.example` (new) (#29)
- Document: `KB_DATABASE_URL`, `KB_LLM_PROVIDER`, `KB_GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, etc.

#### `backend/tests/test_api_smoke.py` (new) (#20)
- 5 smoke tests using `TestClient`:
  1. `/api/papers` returns paginated 200
  2. `/api/papers/{nonexistent}` returns 404 (NOT 422)
  3. `/api/papers/search?q=foo` returns 200 (regression test for #1)
  4. `/api/stats` returns dict with expected keys
  5. `ChatRequest` rejects `query=""` and `top_k=999`

### Frontend

#### `frontend/src/components/search-bar.tsx`
- Initialize `q` state from `useSearchParams.get("q") ?? ""` (#19)
- Wrap in Suspense boundary inside layout (already done via app/page) — verify

#### `frontend/src/app/search/page.tsx`
- Delete file; route `/search?q=` redirects via `next.config.ts` to `/?q=` (#18)
- Update `search-bar.tsx` to push `/?q=...` instead of `/search?q=...`

#### `frontend/next.config.ts`
- Add redirect: `/search` → `/`

#### `frontend/src/components/layout/header.tsx`
- Read version from `package.json` import (#32)

---

## Execution order (dependencies)

**Group A (config layer, must come first)**:
1. `backend/kb/config.py` — settings expanded
2. `backend/.env.example` — documentation companion

**Group B (data layer, depends on A)**:
3. `backend/kb/database.py` — uses settings
4. `backend/kb/models.py` — UTC + indexes

**Group C (processing, depends on B)**:
5. `backend/kb/processing/llm.py` — rename + provider + clamp + sanitize + log
6. `backend/kb/processing/embeddings.py` — lock + config + log

**Group D (ingestion, depends on B+C)**:
7. `backend/kb/ingestion/arxiv.py`
8. `backend/kb/ingestion/rss.py`
9. `backend/kb/ingestion/github_trending.py`
10. `backend/kb/reports.py`
11. `backend/kb/daily.py`

**Group E (API, depends on all)**:
12. `backend/kb/schemas.py`
13. `backend/kb/main.py` — final, integrates everything

**Group F (tooling)**:
14. `backend/pyproject.toml`
15. `backend/tests/test_api_smoke.py`

**Group G (frontend, independent)**:
16. `frontend/src/components/search-bar.tsx`
17. `frontend/src/app/search/page.tsx` (delete)
18. `frontend/next.config.ts`
19. `frontend/src/components/layout/header.tsx`

---

## Phase 3 (QA) gates

1. `python -c "from kb.main import app; print(app.routes)"` — import sanity + route registration
2. `python -m pytest backend/tests/ -x` — smoke tests pass
3. `cd frontend && npx tsc --noEmit` — TypeScript no errors
4. `cd frontend && npx eslint src/` — lint clean

## Phase 4 (Validation) gates

Self-review checklist:
- [ ] All 37 in-scope issues addressed (cross-reference)
- [ ] No new imports broken
- [ ] Backward compat for existing DB (indexes via `IF NOT EXISTS`)
- [ ] No regressions in route shape (paginate/sort/search still work)
- [ ] Defaults preserved (env-driven but old hardcoded values still default)

## Phase 5 (Cleanup)

- Keep this plan as historical record in `.omc/plans/`
- No state files generated (single-pass execution, no resumable state)

---

## Risk register

| Risk | Mitigation |
|------|-----------|
| Existing SQLite DB schema mismatch (timezone columns) | SQLAlchemy treats `DateTime(timezone=True)` as TEXT in SQLite — backward compatible |
| `unique=True` on `url` collides with existing duplicates | Pre-flight: pre-existing data unlikely to violate; if so, init_db catches and logs |
| LLM provider switch breaks existing hermes flow | Default `KB_LLM_PROVIDER=hermes` → no behavior change unless opted in |
| Frontend `/search` route deletion breaks bookmarks | next.config.ts redirect preserves URLs |

