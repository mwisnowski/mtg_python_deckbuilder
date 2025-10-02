#!/usr/bin/env sh
set -e

# Seed default config files into /app/config if missing (handles first-run with mounted volume)
seed_defaults() {
    # Ensure base config directory exists
    mkdir -p /app/config /app/config/card_lists /app/config/themes

    # Copy from baked-in defaults if targets are missing
    if [ -d "/.defaults/config" ]; then
        # deck.json
        [ -f /app/config/deck.json ] || cp "/.defaults/config/deck.json" "/app/config/deck.json" 2>/dev/null || true
        # brackets.yml (power brackets) if present
        [ -f /app/config/brackets.yml ] || { [ -f "/.defaults/config/brackets.yml" ] && cp "/.defaults/config/brackets.yml" "/app/config/brackets.yml"; } 2>/dev/null || true
        # Copy any default card list JSONs that are missing (generic loop)
        if [ -d "/.defaults/config/card_lists" ]; then
            for f in /.defaults/config/card_lists/*.json; do
                [ -f "$f" ] || continue
                base=$(basename "$f")
                [ -f "/app/config/card_lists/$base" ] || cp "$f" "/app/config/card_lists/$base" 2>/dev/null || true
            done
        fi
        # Seed theme catalog defaults (e.g., synergy pairs, clusters, whitelist)
        if [ -d "/.defaults/config/themes" ]; then
            for f in /.defaults/config/themes/*; do
                [ -e "$f" ] || continue
                base=$(basename "$f")
                dest="/app/config/themes/$base"
                if [ -d "$f" ]; then
                    if [ ! -d "$dest" ]; then
                        cp -r "$f" "$dest" 2>/dev/null || true
                    fi
                else
                    [ -f "$dest" ] || cp "$f" "$dest" 2>/dev/null || true
                fi
            done
        fi
    fi
}

seed_defaults

# Ensure we're at repo root so the `code` package resolves correctly
cd /app || exit 1

# Select mode: default to Web UI
MODE="${APP_MODE:-web}"

if [ "$MODE" = "cli" ]; then
    # Run the CLI (interactive menu; use DECK_MODE=headless for non-interactive)
    exec python -m code.main
fi

# Web UI (FastAPI via uvicorn)
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"
WORKERS="${WORKERS:-1}"

exec uvicorn code.web.app:app --host "$HOST" --port "$PORT" --workers "$WORKERS"
