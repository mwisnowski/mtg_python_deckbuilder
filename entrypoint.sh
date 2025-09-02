#!/usr/bin/env sh
set -e

# Seed default config files into /app/config if missing (handles first-run with mounted volume)
seed_defaults() {
    # Ensure base config directory exists
    mkdir -p /app/config /app/config/card_lists

    # Copy from baked-in defaults if targets are missing
    if [ -d "/.defaults/config" ]; then
        # deck.json
        [ -f /app/config/deck.json ] || cp "/.defaults/config/deck.json" "/app/config/deck.json" 2>/dev/null || true
        # combos.json and synergies.json
        [ -f /app/config/card_lists/combos.json ] || cp "/.defaults/config/card_lists/combos.json" "/app/config/card_lists/combos.json" 2>/dev/null || true
        [ -f /app/config/card_lists/synergies.json ] || cp "/.defaults/config/card_lists/synergies.json" "/app/config/card_lists/synergies.json" 2>/dev/null || true
    fi

    # Back-compat: if someone expects combo.json, symlink to combos.json when present
    if [ ! -e /app/config/card_lists/combo.json ] && [ -f /app/config/card_lists/combos.json ]; then
        ln -s "combos.json" "/app/config/card_lists/combo.json" 2>/dev/null || true
    fi
}

seed_defaults

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
