#!/bin/bash
set -euo pipefail

echo "MTG Python Deckbuilder - Web UI (Docker Hub)"
echo "==========================================="

# Create directories if they don't exist
mkdir -p deck_files logs csv_files config owned_cards

# Flags (override by exporting before running)
: "${SHOW_LOGS:=1}"
: "${SHOW_DIAGNOSTICS:=1}"

echo "Starting Web UI on http://localhost:8080"
echo "Flags: SHOW_LOGS=${SHOW_LOGS}  SHOW_DIAGNOSTICS=${SHOW_DIAGNOSTICS}"

docker run --rm \
  -p 8080:8080 \
  -e SHOW_LOGS=${SHOW_LOGS} -e SHOW_DIAGNOSTICS=${SHOW_DIAGNOSTICS} \
  -v "$(pwd)/deck_files:/app/deck_files" \
  -v "$(pwd)/logs:/app/logs" \
  -v "$(pwd)/csv_files:/app/csv_files" \
  -v "$(pwd)/owned_cards:/app/owned_cards" \
  -v "$(pwd)/config:/app/config" \
  mwisnowski/mtg-python-deckbuilder:latest \
  bash -lc "cd /app && uvicorn code.web.app:app --host 0.0.0.0 --port 8080"

echo
echo "Open: http://localhost:8080"
echo "Tip: export SHOW_LOGS=0 or SHOW_DIAGNOSTICS=0 to hide those pages."
