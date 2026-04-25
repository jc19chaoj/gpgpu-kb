#!/bin/bash
# start.sh — Start both backend and frontend
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Starting GPGPU Knowledge Base ==="

# Start backend
echo "[backend] Starting FastAPI on port 8000..."
cd "$SCRIPT_DIR/backend"
mkdir -p data
#source .venv/bin/activate 2>/dev/null || source venv/bin/activate 2>/dev/null || true
uvicorn kb.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend
echo "[frontend] Starting Next.js on port 3000..."
cd "$SCRIPT_DIR/frontend"
if [ ! -x "node_modules/.bin/next" ]; then
  echo "[frontend] node_modules missing or incomplete; running npm install..."
  npm install
fi
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:8000 (API docs: http://localhost:8000/docs)"
echo "Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop both."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
