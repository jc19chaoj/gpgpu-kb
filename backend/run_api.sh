#!/bin/bash
# run_api.sh — Start the FastAPI server
cd "$(dirname "$0")"
mkdir -p data
source .venv/bin/activate 2>/dev/null || source venv/bin/activate 2>/dev/null || true
uvicorn kb.main:app --host 0.0.0.0 --port 8000 --reload --timeout-keep-alive 75
