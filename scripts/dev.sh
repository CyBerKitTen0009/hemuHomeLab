#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 scripts/bootstrap.py
if [ ! -x .venv/bin/python ]; then
  uv sync
fi
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm ci)
fi
printf '\n前端：http://localhost:5173\n后端：http://127.0.0.1:8000\n按 Ctrl-C 停止。\n\n'
.venv/bin/python -m uvicorn backend.hcc.main:app --host 127.0.0.1 --port 8000 &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT INT TERM
cd frontend
npm run dev
