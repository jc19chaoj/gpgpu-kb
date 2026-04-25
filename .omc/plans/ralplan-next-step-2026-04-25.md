# Ralplan Consensus Plan — Next Step (2026-04-25)

**Author**: Planner pass + Architect amendment + Critic approval
**Status**: APPROVED — ready for execution
**Consensus**: Architect APPROVE (with mandatory amendment) → Critic APPROVE (fold-in confirmed)
**Predecessor**: `.omc/plans/autopilot-impl.md` (24 audit fixes shipped at commit `65f9ef1`)

---

## 1. Context

The previous autopilot iteration shipped 24 backend + frontend fixes that closed the 🔴 critical and 🟠 high tiers of the audit. Eight items were explicitly deferred:

| # | Deferred item | Reason |
|---|--------------|--------|
| #14 | Server Components rewrite | Multi-day refactor; needs scoped plan |
| #20 | Full test coverage | Smoke tests only; ingestion/processing/reports unverified |
| #21 | Multi-turn chat | Needs product decision (single-turn vs conversational) |
| #37 | `is_processed` Enum | Schema-invasive without Alembic |
| — | Alembic migrations | Manual schema mgmt today |
| — | Docker / deploy | No deployment story documented |
| — | Auth middleware | `/api/chat` exposed as anon LLM proxy |
| — | Observability | logger plumbed but no Grafana/Sentry |

User asked for "the next step" — singular. So we pick **one** focused initiative.

---

## 2. RALPLAN-DR summary

### Principles (P1–P4)
- **P1 — Lock in before extending**: every prior fix needs a regression net before we layer new work, otherwise the audit ROI evaporates the next iteration.
- **P2 — Smallest unit of trustworthy change**: pick a delivery that completes within 1–2 sessions, not a months-long migration.
- **P3 — Data-flow coverage over UI polish**: this is a knowledge-base pipeline (ingest → process → embed → report); breakage in the pipeline is invisible from the UI until reports are empty.
- **P4 — No speculative work without a forcing function**: defer items that don't have a concrete trigger (e.g., schema migrations are only valuable when the schema actually changes).

### Decision Drivers (top 3)
- **D1 — Risk of silent regression**: ingestion/processing have no tests; one refactor can break daily reports without anyone noticing for days.
- **D2 — Time-to-value**: which option delivers a working artifact within 1–2 days of focused work.
- **D3 — Unblocks future work**: which option, once landed, makes _every_ subsequent task safer or faster.

### Viable Options

#### Option A — Pipeline test coverage + minimal CI (RECOMMENDED)
Add unit tests for `ingestion/{arxiv,rss,github_trending}.py` (mock HTTP), `processing/llm.py` (mock subprocess + mock SDK), `processing/embeddings.py` (skip-if-ml-not-installed), `reports.py` (in-memory DB). Add 2 Playwright e2e flows for the frontend (browse + chat). Wire up a GitHub Actions workflow that runs `pytest` + `tsc --noEmit` + `eslint` on push.

| Pros | Cons |
|------|------|
| Locks in all 24 audit fixes against future regression (P1) | No user-visible improvement |
| 1-2 day scope; concrete deliverables (P2) | Adds maintenance burden (CI + 20+ new test files) |
| Catches breakage in invisible pipeline stages (P3) | Mocking external APIs is finicky |
| Foundation under every future task (D3) | — |

#### Option B — Server Components migration (#14)
Rewrite `paper/[id]/page.tsx`, `reports/[id]/page.tsx`, `stats/page.tsx`, and `reports/page.tsx` as Server Components with `fetch(url, { next: { revalidate: 60 } })`. Keep `/` and `/chat` as Client Components for interactivity. Update `lib/api.ts` to support absolute URLs server-side.

| Pros | Cons |
|------|------|
| Visible perf win (first paint, SEO) | Touches all detail pages — high blast radius |
| Idiomatic Next.js 16 usage | No regression net yet (violates P1) |
| Frontend-only, doesn't touch the pipeline | Bookmarks for `/paper/[id]` need real data — also need to expose backend on a routable URL |
| — | Needs design decision on caching (per-request vs ISR vs static) |

#### Option C — Production readiness pack
Add `docker-compose.yml` (backend + frontend), Alembic baseline + first migration, simple bearer-token auth on `/api/chat` (env-set token), `/api/health` extended with DB + LLM probes, basic Sentry/Logfire wiring.

| Pros | Cons |
|------|------|
| Unblocks deploy | Five disjoint subprojects in one — fights P2 |
| Shipping prerequisite | Auth needs product decision (who's the user?) |
| Forces serious thinking about config | Without tests (Option A) any deploy is fragile |

### Invalidation note
None of A/B/C is strictly dominant. **Option A wins on P1 + D1 + D3** (the non-negotiables right now); B becomes correct after A; C becomes correct after A and after a decision on hosting target.

---

## 3. Recommended next step — Option A + Step-0 auth guard

### 3.0 Step 0 (FOLDED IN per Architect/Critic consensus) — bearer-token guard on `/api/chat`

**Why before tests**: writing 870 LoC of tests for an endpoint that is publicly callable and burns billable API keys is putting the cart before the horse. Critic verdict: mandatory fold-in.

**Implementation** (~15 LoC + 1 test case, total scope rises to ~885 LoC):
- `backend/kb/config.py`: add `chat_token: str | None = None` (read `KB_CHAT_TOKEN`).
- `backend/kb/main.py`: add a small `Depends(verify_chat_token)` to `POST /api/chat` only. The dependency:
  - If `settings.chat_token` is `None` → pass (preserves frictionless local dev).
  - Otherwise compare against `Authorization: Bearer <token>` header in constant time; return 401 on mismatch.
- `backend/.env.example`: document `KB_CHAT_TOKEN`.
- `backend/tests/test_api_smoke.py`: add `test_chat_rejects_unauthenticated_when_token_set` (set env, expect 401) and ensure existing chat tests run with token unset.

**Acceptance**: `curl -X POST /api/chat -d '{"query":"hi"}'` returns 401 when `KB_CHAT_TOKEN` is set in env, 200 (validation-permitting) when unset.

### 3.1 Scope (concrete deliverables)

**Backend tests** (`backend/tests/`):
- `test_ingestion_arxiv.py` — patch `arxiv.Client.results` with a fake iterator; assert per-category dedup, cutoff filtering, save_papers idempotence.
- `test_ingestion_rss.py` — patch `feedparser.parse` to return a fixture object; assert dead feeds skip silently, valid posts persist.
- `test_ingestion_github.py` — patch `httpx.Client.get` to return a fake `Response`; assert auth header injection, 403 rate-limit short-circuit, polite-sleep is called.
- `test_processing_llm.py` — patch `_call_hermes` (and the SDK callers) to return canned strings; assert clamp behavior on out-of-range scores, JSON parse fallback, prompt-injection sanitization keeps untrusted content delimited.
- `test_processing_embeddings.py` — when ML deps absent, EmbeddingStore reports `available=False` and search returns `[]`. Skip the with-deps tests if `chromadb` not importable.
- `test_reports.py` — seed DB with processed papers, run `generate_daily_report`, assert upsert path overwrites instead of raising IntegrityError.
- Existing `test_api_smoke.py` stays; add 2 more cases:
  - `test_search_returns_keyword_match_when_semantic_unavailable` (fallback path)
  - `test_chat_response_handles_no_results`

**Frontend tests** (new `frontend/tests/e2e/`):
- `playwright.config.ts` with web-server config that runs `next start` against a static fixture API.
- `browse.spec.ts` — visit `/`, assert ≥1 paper card renders or "No papers" empty state shows.
- `chat.spec.ts` — visit `/chat`, type a query, assert the loading indicator and a response appears.
- Mock the FastAPI backend with Playwright's `route()` interception to keep e2e self-contained.

**CI workflow** (`.github/workflows/ci.yml`):
- Job 1 (backend): `actions/setup-python@v5`, `pip install -e '.[ml,dev]'`, `pytest -x`.
- Job 2 (frontend-typecheck): `actions/setup-node@v4`, `npm ci`, `npx tsc --noEmit`, `npx eslint src/`.
- Job 3 (frontend-e2e): same setup + `npx playwright install --with-deps chromium`, `npx playwright test`.
- Trigger on `push` to any branch and on PRs.

**Documentation** (small):
- README "Development" section: how to run tests locally.
- `backend/tests/README.md`: how mocks are organized.

### 3.2 Acceptance criteria (testable)

- [ ] **Step 0**: `curl -i -X POST :8000/api/chat -d '{"query":"hi","top_k":1}'` returns 401 when `KB_CHAT_TOKEN` is set without an `Authorization` header; returns 422/200 when the env is unset (current behavior)
- [ ] `cd backend && pytest -x` shows ≥19 passing tests (7 existing + ≥12 new), 0 failures, in <10s
- [ ] Coverage of `kb/ingestion/*.py`, `kb/processing/*.py`, `kb/reports.py` exceeds 70% lines (measured with `pytest --cov`)
- [ ] `cd frontend && npx playwright test` runs both e2e specs against a mocked backend in <60s
- [ ] `git push` triggers GitHub Actions; all three CI jobs go green
- [ ] One injected regression (e.g., revert the route reorder) makes the relevant test fail — proves the net catches the audit fix it covers

### 3.3 Verification steps

1. Run `pytest -x -q` after each new test file is added; ensure no flake.
2. Add `pytest-cov`; run `pytest --cov=kb --cov-report=term-missing`; identify files <70% and fill gaps.
3. Run `npx playwright test --headed` once interactively to confirm flows work.
4. Push a throwaway commit that swaps the route order in `main.py`; confirm CI fails on the regression test; revert.

### 3.4 File-level plan (counts)

| Path | Action | LoC est |
|------|--------|---------|
| `backend/kb/config.py` | add `chat_token` | +1 |
| `backend/kb/main.py` | add `verify_chat_token` Depends | +14 |
| `backend/.env.example` | document `KB_CHAT_TOKEN` | +2 |
| `backend/tests/test_ingestion_arxiv.py` | new | 60 |
| `backend/tests/test_ingestion_rss.py` | new | 60 |
| `backend/tests/test_ingestion_github.py` | new | 80 |
| `backend/tests/test_processing_llm.py` | new | 110 |
| `backend/tests/test_processing_embeddings.py` | new | 50 |
| `backend/tests/test_reports.py` | new | 80 |
| `backend/tests/test_api_smoke.py` | extend | +30 |
| `backend/tests/conftest.py` | extend | +20 |
| `backend/tests/fixtures/` | new dir w/ JSON | 100 |
| `backend/pyproject.toml` | add `pytest-cov` | +1 |
| `frontend/playwright.config.ts` | new | 30 |
| `frontend/tests/e2e/browse.spec.ts` | new | 50 |
| `frontend/tests/e2e/chat.spec.ts` | new | 60 |
| `frontend/package.json` | add `@playwright/test` devDep | +1 |
| `.github/workflows/ci.yml` | new | 80 |
| `README.md` | extend | +20 |
| `backend/tests/README.md` | new | 40 |
| **Total new code** | | ~885 |

### 3.5 Sequencing (build order)

0. **Step 0 — auth guard on `/api/chat`** (config + Depends + .env.example + 1 test). Verify with curl.
1. Add fixtures + extend conftest (foundation)
2. Backend ingestion tests (3 files, sequential build but tests within each file can mock independently)
3. Backend processing tests (2 files)
4. Backend reports test
5. Add `pytest-cov`; verify coverage threshold ≥70% on `kb/{ingestion,processing,reports}.py`
6. Frontend Playwright config + 2 specs (mocked backend via `route()` interception)
7. CI workflow (3 jobs: backend pytest, frontend typecheck+eslint, frontend e2e)
8. README + tests/README docs
9. Final verification: inject regression (e.g., revert route reorder), confirm CI catches it, revert

### 3.6 Out of scope (explicit non-goals for this iteration)

- Full e2e coverage of every page (browse + chat are smoke surface)
- Property-based / hypothesis testing
- Backend integration tests against real ArXiv / GitHub
- Visual regression (screenshot diffing)
- Performance benchmarks
- Coverage of UI atom components (button, card, etc.)

### 3.7 Risk register

| Risk | Mitigation |
|------|-----------|
| Mocked tests pass but real APIs broke | Quarterly manual `python -m kb.daily` smoke run; keep mocks faithful to current API shapes |
| Playwright flakiness on CI | Use `--retries 2` and explicit `page.waitForResponse` instead of timeouts |
| `pytest-cov` slows feedback loop | Coverage opt-in via `pytest -m cov`; default fast path stays bare `pytest` |
| GitHub Actions minutes cost | Cap CI to push + PR only; matrix has no Python/Node version sprawl |
| ML deps in CI bloat install time | Run ML-dependent tests in a separate job that's allowed to skip on PRs |

---

## 4. ADR — Architecture Decision Record

**Decision**: ship Option A (pipeline test coverage + minimal CI), prefixed with Step 0 (`/api/chat` bearer-token guard) folded in per Architect/Critic consensus.

**Drivers**: D1 silent-regression risk, D2 time-to-value (1–2 days), D3 unblocks future work, plus the live finding that `/api/chat` is an unauthenticated LLM proxy.

**Alternatives considered**:
- **B (Server Components rewrite)** — rejected as next step. Architect's steelman: visible perf win + idiomatic Next 16. Why we said no: violates P1 (no regression net) — the same refactor done after Option A becomes far safer.
- **C (Production readiness pack)** — rejected as a single deliverable because it bundles 4–5 disjoint subprojects (Docker + Alembic + auth + health + Sentry), violating P2. The Architect correctly identified that the **auth subset of C** is a live security finding and should ship now (Step 0); the rest of C remains deferred until a deploy target is decided.

**Why chosen**: locks in the 24 audit fixes against regression; closes the only live security gap with 15 LoC; foundation under B and the rest of C.

**Consequences**:
- (+) Every future iteration moves with regression confidence
- (+) CI catches breakage before merge
- (+) `/api/chat` becomes safe to expose publicly behind a token
- (-) ~885 LoC of test/auth code to maintain
- (-) GitHub Actions minutes cost (well within free tier)
- (-) Mock fidelity risk (Architect's soft suggestion: prefer recorded-fixture replay over hand-crafted mocks where practical) — flagged for executor judgement

**Follow-ups** (next iterations after this lands):
1. Option B — Server Components migration (now safe to refactor with regression net)
2. Decision on multi-turn chat (#21) — product question
3. Alembic baseline + first migration (in preparation for #37 enum migration)
4. Remaining Option C — Docker/health/observability (only after deploy target is decided)

---

## 5. Consensus signatures

- **Planner**: drafted RALPLAN-DR + plan; recommended Option A
- **Architect**: APPROVE with mandatory amendment (Step 0 auth) + soft suggestion (fixture-replay mocks)
- **Critic**: APPROVE conditional on Step 0 fold-in; auth amendment is mandatory not optional
- **Final state**: amendment folded in; plan locked at ~885 LoC, 1–2 day delivery
