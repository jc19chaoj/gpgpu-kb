# syntax=docker/dockerfile:1.7
# Backend image: FastAPI + SQLAlchemy + (optional) ChromaDB / sentence-transformers
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build deps for any packages that ship sdists (sentence-transformers/torch ship wheels,
# but a few transitive deps occasionally need a compiler). curl is used by the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Allow swapping the pip index at build time. Useful when pypi.org is
# unreachable / rate-limited (e.g. in some regions). Examples:
#   --build-arg PIP_INDEX_URL=https://pypi.org/simple
#ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
#ENV PIP_INDEX_URL=$PIP_INDEX_URL \
#    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

# Install Python deps first so the layer caches across code edits.
# Only pyproject.toml + a stub `kb/__init__.py` are copied here, so changing
# any real source under kb/ does NOT invalidate this (slow) install layer.
# We use an editable install (`pip install -e`) so that when the real source
# is copied in below, it overrides the stub without needing to reinstall.
COPY pyproject.toml ./
RUN mkdir -p kb && : > kb/__init__.py

# INSTALL_EXTRAS controls how heavy the image is.
#   "all" (default)         — convenience aggregate: ml + llm-cloud + fulltext (ChromaDB + sentence-transformers + Anthropic/OpenAI/DeepSeek SDK + trafilatura)
#   "llm-cloud,fulltext"    — cloud LLM only, semantic search/RAG falls back to keyword
#   "fulltext"              — minimal + HTML extraction
#   ""                      — bare bones: ingestion + LLM-via-CLI only (full_text prefetch will no-op)
ARG INSTALL_EXTRAS=all
RUN if [ -z "$INSTALL_EXTRAS" ]; then \
        pip install -e . ; \
    else \
        pip install -e ".[${INSTALL_EXTRAS}]" ; \
    fi

# Pre-download the SentenceTransformer weights into the image so container
# recreation doesn't re-fetch ~90 MB on every cold start. Only runs when the
# `ml` (or aggregate `all`) extra is enabled — otherwise sentence-transformers
# isn't installed and the import would fail. Model name must match
# settings.embedding_model (kb/config.py); change both together if you swap.
ARG KB_EMBEDDING_MODEL=all-MiniLM-L6-v2
RUN if echo ",${INSTALL_EXTRAS}," | grep -qE ',(ml|all),'; then \
        python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${KB_EMBEDDING_MODEL}')" ; \
    fi

# Real source goes in last — code edits only invalidate this thin layer.
COPY kb ./kb

# Persisted data lives under /app/data (mount a volume here in production).
RUN mkdir -p /app/data
VOLUME ["/app/data"]

# Sensible runtime defaults; override via docker-compose env_file or `-e`.
ENV KB_DATABASE_URL="sqlite:////app/data/kb.sqlite" \
    KB_CHROMA_DIR="/app/data/chroma" \
    KB_DATA_DIR="/app/data" \
    KB_CORS_ORIGINS='["http://localhost:3000"]'

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# --timeout-keep-alive 75: uvicorn's default (5s) races with the Next.js
# fetch-agent connection pool when /api/* is reverse-proxied through Next
# (see frontend/next.config.ts rewrites). If the upstream closes a keep-alive
# socket while the proxy still has it pooled, the next reuse fails with
# ECONNRESET and the frontend shows "Sorry, I couldn't process that query".
# Bumping the upstream timeout above any reasonable proxy idle window
# eliminates the race (same pattern as AWS ELB / nginx upstream guidance).
CMD ["uvicorn", "kb.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "75"]
