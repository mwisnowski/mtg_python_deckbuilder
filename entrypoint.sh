#!/usr/bin/env sh
set -e

# Always operate from the code directory for imports to work
cd /app/code || exit 1

# Select mode: default to Web UI
MODE="${APP_MODE:-web}"

if [ "$MODE" = "cli" ]; then
    # Run the CLI (interactive menu; use DECK_MODE=headless for non-interactive)
    exec python main.py
fi

# Web UI (FastAPI via uvicorn)
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"
WORKERS="${WORKERS:-1}"

exec uvicorn web.app:app --host "$HOST" --port "$PORT" --workers "$WORKERS"
