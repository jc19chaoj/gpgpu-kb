# backend/tests/

Pytest suite for the GPGPU KB backend. ~75 tests, runs in <2 s, no network required.

## Layout

| File | Covers |
| --- | --- |
| `conftest.py` | Test infrastructure — sets `KB_DATABASE_URL` to an isolated SQLite tmp dir, autouse `_init_db`, session-scoped `client` fixture for API tests |
| `test_api_smoke.py` | Public API surface (route registration, 404s, validation, `/api/chat` bearer-token guard) |
| `test_ingestion_arxiv.py` | `kb/ingestion/arxiv.py` — per-category dedup, cutoff filter, `save_papers` idempotence |
| `test_ingestion_rss.py` | `kb/ingestion/rss.py` — bozo handling, cutoff, dedup, multi-feed aggregation |
| `test_ingestion_github.py` | `kb/ingestion/github_trending.py` — auth header, 403 rate-limit short-circuit, polite sleep |
| `test_processing_llm.py` | `kb/processing/llm.py` — provider routing, `_clamp_score`, `_sanitize`, `summarize_and_score` happy + fallback paths |
| `test_processing_embeddings.py` | `kb/processing/embeddings.py` — singleton lock, graceful degradation when ML deps absent |
| `test_reports.py` | `kb/reports.py` — happy path, upsert behavior, empty case |
| `fixtures/` | Static JSON samples for arxiv / rss / github responses |

## Running

```bash
cd backend && source .venv/bin/activate
pip install -e '.[dev]'

python -m pytest tests/ -x -q                       # fast loop
python -m pytest tests/ --cov=kb --cov-report=term-missing  # with coverage
python -m pytest tests/test_processing_llm.py -x     # single file
```

## Mocking strategy

External I/O is mocked at the **boundary closest to the call site**:

- **HTTP** — `httpx.Client` is patched as a context manager. Mocks return `unittest.mock.Mock(status_code=…, json=…, headers=…)`.
- **arxiv.Client.results** — patched to return a list of `Mock` objects mimicking `arxiv.Result` (`.title`, `.authors`, `.published`, `.entry_id`, etc.).
- **feedparser.parse** — patched to return a `SimpleNamespace(entries=[…], bozo=False)`.
- **subprocess.run** (for `_call_hermes`) — patched to return a `CompletedProcess` with the canned stdout.
- **anthropic / openai SDKs** — `_PROVIDERS` dict is patched directly so the test never imports the real SDK. Tests assert the dispatch behavior, not the wire-level SDK call.
- **call_llm in reports/llm tests** — patched at the use-site to avoid spawning hermes.

The `_PROVIDERS` indirection in `llm.py` captures function references at import time, so tests must patch `llm_mod._PROVIDERS[key]` rather than module-level names.

## Coverage targets

Per the consensus plan acceptance criteria:

| Path | Target | Current |
| --- | --- | --- |
| `kb/ingestion/*.py` | ≥70% | 90–92% ✅ |
| `kb/reports.py` | ≥70% | 94% ✅ |
| `kb/processing/llm.py` | ≥70% | 65% (cloud SDK happy paths uncovered without real network — acceptable) |
| `kb/processing/embeddings.py` | ≥70% | 59% (most of the file is gated by ML deps; gracefully-degraded path is covered) |
| Overall | – | 74% ✅ |

If you add the `[ml]` extra (`pip install -e '.[ml]'`), the embeddings tests with `@pytest.mark.skipif` will run and bump that file's coverage substantially.

## Fixtures

`tests/fixtures/` holds canned responses recorded once and reused. They are intentionally **small** (1–3 records each) — the goal is "did the code path execute," not "is the upstream API still the same shape."

Treat these fixtures as documentation of the expected response shape. If an upstream provider changes their format, refresh the fixture and re-run the tests.
