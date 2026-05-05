# GPGPU Knowledge Base

Self-updating research knowledge base for GPGPU chip architecture.
Collects, summarizes, and scores high-impact papers, blogs, talks, and open-source projects,
with semantic search and an LLM-powered RAG chat over the corpus.

## Quick Start

```bash
# Install backend deps
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
mkdir -p data
python -c "from kb.database import init_db; init_db()"

# (Optional) One-shot full install: ML + cloud LLM + HTML extraction.
# This is what most users want; it covers semantic search/RAG, cloud
# providers, and full-article fetching for blog/project rows.
pip install -e '.[all]'

# Or pick individual extras:
#   '.[ml]'        — ChromaDB + sentence-transformers (semantic search / RAG)
#   '.[llm-cloud]' — Anthropic / OpenAI / DeepSeek SDKs
#   '.[fulltext]'  — trafilatura (blog / project article-body extraction)

# Start backend
./run_api.sh

# In another terminal, start frontend
cd frontend
npm install
npm run dev
```

Or start both at once:
```bash
./start.sh
```

- Backend: http://localhost:8000 (API docs: http://localhost:8000/docs)
- Frontend: http://localhost:3000

## Configuration

All backend settings can be overridden via env vars (prefix `KB_`) or a `backend/.env` file.

| Var | Default | Notes |
| --- | --- | --- |
| `KB_LLM_PROVIDER` | `hermes` | `hermes` (local CLI), `anthropic`, `openai` |
| `KB_ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Used when provider is `anthropic` |
| `KB_OPENAI_MODEL` | `gpt-4o-mini` | Used when provider is `openai` |
| `KB_LLM_TIMEOUT_SECONDS` | `180` | Per-call LLM timeout |
| `KB_DATABASE_URL` | `sqlite:///./data/kb.sqlite` | SQLAlchemy URL |
| `KB_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model |
| `KB_CHROMA_DIR` | `./data/chroma` | ChromaDB persistence dir |
| `KB_ARXIV_PER_CATEGORY` | `50` | ArXiv results per category per run |
| `KB_CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed origins |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GITHUB_TOKEN` | – | Provider/auth keys (also accepted with `KB_` prefix) |
| `KB_CHAT_TOKEN` | – | If set, `POST /api/chat` requires `Authorization: Bearer <token>`; unset = open (local dev) |

## Daily Pipeline

Run manually:
```bash
cd backend
source .venv/bin/activate
python -m kb.daily
```

Or schedule via Hermes:
```
hermes cron create \
  --name "GPGPU KB Daily" \
  --schedule "0 7 * * *" \
  --workdir ~/gpgpu-kb/backend \
  --prompt "Run the daily KB pipeline: source .venv/bin/activate && python -m kb.daily"
```

## API

Base URL: `http://localhost:8000`. Interactive docs at `/docs`.

| Endpoint | Description |
| --- | --- |
| `GET /api/papers` | Paginated list (filter by `source_type`, sort by date / scores) |
| `GET /api/papers/search?q=...&semantic=true` | Semantic search with keyword fallback |
| `GET /api/papers/{id}` | Paper detail incl. summary and scores |
| `POST /api/chat` | RAG chat: retrieves relevant papers, answers via LLM with sources |
| `GET /api/reports` / `GET /api/reports/{id}` | Daily reports |
| `GET /api/stats` | Corpus stats (total, processed, by source type, top-impact) |
| `GET /api/health` | Liveness check |

## Architecture

```
backend/
  kb/
    database.py          # SQLite via SQLAlchemy
    models.py            # Paper, DailyReport models
    schemas.py           # Pydantic API schemas
    config.py            # Settings from env (KB_* / .env)
    main.py              # FastAPI app: papers, search, chat, reports, stats
    reports.py           # Daily report generator (LLM-powered)
    daily.py             # Full pipeline runner (ingest → process → report)
    ingestion/
      arxiv.py           # ArXiv API (cs.AR, cs.AI, cs.LG, ...)
      rss.py             # 13 curated RSS feeds
      github_trending.py # GitHub Search API for relevant repos
      run.py             # Orchestrator
    processing/
      llm.py             # Summarization + scoring via configured provider
      embeddings.py      # ChromaDB + sentence-transformers (optional)
  tests/                 # pytest suite

frontend/                # Next.js 16 + React 19 + Tailwind v4 + shadcn/ui
  src/
    app/
      page.tsx                # Browse with filter/sort + search
      chat/page.tsx           # RAG chat interface
      paper/[id]/page.tsx     # Paper detail with scores
      reports/page.tsx        # Daily report list
      reports/[id]/page.tsx   # Report detail (markdown)
      stats/page.tsx          # KB statistics
    components/
      layout/                 # Sidebar + Header
      ui/                     # shadcn/ui primitives (button, card, dialog, ...)
      paper-card.tsx          # Paper list item
      search-bar.tsx          # Search input
    lib/
      api.ts                  # API client
      types.ts                # TypeScript interfaces
      utils.ts                # Helpers
```

> Note: the frontend tracks the latest Next.js (16.x) — see `frontend/AGENTS.md`
> before assuming earlier conventions.

## Scoring

Papers are scored on two dimensions (0-10):

- **Originality**: How novel is the core idea?
- **Impact**: Author pedigree, organization prestige, venue quality, generality

Scores are generated by LLM analysis of the full paper summary.

## Semantic Search & RAG Chat

`/api/papers/search` and `/api/chat` use ChromaDB + sentence-transformers
(`all-MiniLM-L6-v2` by default). The embedding store is pre-warmed at FastAPI
startup so the first request doesn't pay the model-load cost. If the `[ml]`
extra is not installed, search degrades gracefully to keyword `LIKE` matching
and chat returns an empty-context answer.

## Development & Testing

```bash
# Backend tests (~75 tests, ~1s)
cd backend
source .venv/bin/activate
pip install -e '.[dev]'
python -m pytest tests/ -x -q
python -m pytest tests/ --cov=kb --cov-report=term-missing  # with coverage

# Frontend type-check + lint
cd frontend
npm ci
npx tsc --noEmit
npx eslint src/

# Frontend e2e (Playwright, fully mocked backend)
npx playwright install chromium  # one-time
npm run build && npm run test:e2e
```

CI runs all three jobs on every push and PR — see `.github/workflows/ci.yml`.
Test layout details: `backend/tests/README.md`.

## cpolar (Remote Access)

```bash
cpolar http 3000
```

This exposes the Next.js frontend on a public URL.

## Docker Deployment

A two-service Compose stack is provided (`docker-compose.yml` at the repo root):

```bash
# 1. Configure
cp .env.docker.example .env
# edit .env — at minimum set OPENAI_API_KEY (or ANTHROPIC_API_KEY / DEEPSEEK_API_KEY)
# and KB_LLM_PROVIDER. Optionally set GITHUB_TOKEN and KB_CHAT_TOKEN.

# 2. Build + run
docker compose up -d --build

# 3. Open
#   Frontend:  http://localhost:3000
#   Backend:   http://localhost:8000/docs
```

### Services

| Service | Image | Port | Notes |
| --- | --- | --- | --- |
| `backend` | `gpgpu-kb-backend` (`python:3.12-slim`) | `8000` | FastAPI; SQLite + ChromaDB persisted in the `kb_data` volume |
| `frontend` | `gpgpu-kb-frontend` (`node:20-alpine`) | `3000` | Next.js 16 standalone build |
| `daily` | reuses backend image | – | One-shot pipeline; opt-in via `--profile cron` |

### Daily pipeline (ingest → process → embed → report)

```bash
# Run the full pipeline once against the same volume:
docker compose --profile cron run --rm daily

# Schedule it from the host (example: 07:00 daily):
( crontab -l 2>/dev/null ; \
  echo '0 7 * * * cd /path/to/gpgpu-kb && docker compose --profile cron run --rm daily >> data/daily.log 2>&1' \
) | crontab -
```

### Persistence

All mutable state (`kb.sqlite` + `chroma/`) lives in the named volume `kb_data`,
mounted at `/app/data` inside the backend and daily containers. Back it up with:

```bash
docker run --rm -v gpgpu-kb_kb_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/kb-data-$(date +%F).tgz -C /data .
```

### Production tips

1. **Build args are baked**: `NEXT_PUBLIC_API_URL` is a Next.js public env, so it
   is compiled into the client bundle. If you put the backend behind a domain,
   rebuild the frontend image:
   ```bash
   docker compose build --build-arg NEXT_PUBLIC_API_URL=https://kb.example.com frontend
   ```
2. **Slim the backend** by skipping the ML stack (~2 GB) when you don't need
   semantic search/RAG. Default is `all` (ml + llm-cloud + fulltext); set
   `BACKEND_INSTALL_EXTRAS` to drop pieces:
   ```bash
   BACKEND_INSTALL_EXTRAS=llm-cloud,fulltext docker compose build backend
   ```
   Search will fall back to keyword `LIKE` matching automatically. Drop
   `fulltext` too only if you don't care about blog/project full-article
   extraction (those rows then fall back to og:description blurbs).
3. **Always set `KB_CHAT_TOKEN`** when exposing the API publicly, otherwise
   `/api/chat` is an open LLM proxy. Front the frontend with HTTPS (Caddy /
   Traefik / Cloudflare Tunnel) — the bundled images do not terminate TLS.
4. **CORS**: `KB_CORS_ORIGINS` defaults to `localhost:3000`. Add the production
   origin (e.g. `https://kb.example.com`) before deploying.
5. **`hermes` provider does not work in containers** — pick `openai`,
   `anthropic`, or `deepseek` and provide the matching API key.
