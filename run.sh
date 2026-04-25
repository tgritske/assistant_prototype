#!/usr/bin/env bash
# Convenience launcher — starts backend + frontend in parallel.
# Stops both cleanly on Ctrl-C.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [ ! -f backend/.env ]; then
  echo "▶ backend/.env not found. Copy .env.example and fill in ANTHROPIC_API_KEY."
  exit 1
fi

if [ ! -d backend/.venv ]; then
  echo "▶ Creating Python venv…"
  (cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt)
fi

if [ -z "$(ls -A backend/demo_audio 2>/dev/null)" ]; then
  echo "▶ Generating demo audio (one-time)…"
  (cd backend && source .venv/bin/activate && python generate_demos.py)
fi

if [ ! -d frontend/node_modules ]; then
  echo "▶ Installing frontend deps…"
  (cd frontend && npm install)
fi

cleanup() {
  echo ""
  echo "▶ Shutting down…"
  kill 0
}
trap cleanup INT TERM

(cd backend && source .venv/bin/activate && uvicorn main:app --reload --reload-exclude '.venv/*' --port 8000) &
(cd frontend && npm run dev) &

wait
