#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Starting backend..."
source "$ROOT/backend/.venv/bin/activate"
python "$ROOT/backend/main.py" > "$ROOT/backend.log" 2>&1 &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID (log: backend.log)"

echo "Starting frontend..."
npm --prefix "$ROOT/frontend" run dev > "$ROOT/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "  Frontend PID: $FRONTEND_PID (log: frontend.log)"

echo ""
echo "App running at http://localhost:3000"
echo "To stop: kill $BACKEND_PID $FRONTEND_PID"
