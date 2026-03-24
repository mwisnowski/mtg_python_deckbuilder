#!/bin/bash
set -euo pipefail

# Primary entry point for the MTG Python Deckbuilder Web UI from Docker Hub.
# Override any flag by exporting it before running:
#   export THEME=light
#   export ENABLE_BUDGET_MODE=0

echo "MTG Python Deckbuilder - Web UI (Docker Hub)"
echo "==========================================="

# Create directories if they don't exist
mkdir -p deck_files logs csv_files config owned_cards

# --- Core UI flags ---
: "${SHOW_LOGS:=1}"
: "${SHOW_DIAGNOSTICS:=1}"
: "${WEB_VIRTUALIZE:=1}"

# --- Theming (system|light|dark) ---
: "${ENABLE_THEMES:=1}"
: "${THEME:=dark}"

# --- Budget Mode ---
: "${ENABLE_BUDGET_MODE:=1}"
: "${PRICE_LAZY_REFRESH:=1}"

# --- Builder features ---
: "${ENABLE_BATCH_BUILD:=1}"
: "${WEB_STAGE_ORDER:=new}"
: "${WEB_IDEALS_UI:=slider}"
: "${ALLOW_MUST_HAVES:=1}"
: "${ENABLE_PARTNER_MECHANICS:=1}"

# --- Theme catalog badges ---
: "${SHOW_THEME_QUALITY_BADGES:=1}"
: "${SHOW_THEME_POOL_BADGES:=1}"
: "${SHOW_THEME_POPULARITY_BADGES:=1}"
: "${SHOW_THEME_FILTERS:=1}"

echo "Starting Web UI on http://localhost:8080"
echo "Flags: SHOW_LOGS=${SHOW_LOGS}  SHOW_DIAGNOSTICS=${SHOW_DIAGNOSTICS}  WEB_VIRTUALIZE=${WEB_VIRTUALIZE}  THEME=${THEME}"
echo "       ENABLE_BUDGET_MODE=${ENABLE_BUDGET_MODE}  ENABLE_BATCH_BUILD=${ENABLE_BATCH_BUILD}  WEB_STAGE_ORDER=${WEB_STAGE_ORDER}"

docker run --rm \
  -p 8080:8080 \
  -e SHOW_LOGS="${SHOW_LOGS}" -e SHOW_DIAGNOSTICS="${SHOW_DIAGNOSTICS}" -e WEB_VIRTUALIZE="${WEB_VIRTUALIZE}" \
  -e ENABLE_THEMES="${ENABLE_THEMES}" -e THEME="${THEME}" \
  -e ENABLE_BUDGET_MODE="${ENABLE_BUDGET_MODE}" -e PRICE_LAZY_REFRESH="${PRICE_LAZY_REFRESH}" \
  -e ENABLE_BATCH_BUILD="${ENABLE_BATCH_BUILD}" -e WEB_STAGE_ORDER="${WEB_STAGE_ORDER}" -e WEB_IDEALS_UI="${WEB_IDEALS_UI}" \
  -e ALLOW_MUST_HAVES="${ALLOW_MUST_HAVES}" -e ENABLE_PARTNER_MECHANICS="${ENABLE_PARTNER_MECHANICS}" \
  -e SHOW_THEME_QUALITY_BADGES="${SHOW_THEME_QUALITY_BADGES}" -e SHOW_THEME_POOL_BADGES="${SHOW_THEME_POOL_BADGES}" \
  -e SHOW_THEME_POPULARITY_BADGES="${SHOW_THEME_POPULARITY_BADGES}" -e SHOW_THEME_FILTERS="${SHOW_THEME_FILTERS}" \
  -v "$(pwd)/deck_files:/app/deck_files" \
  -v "$(pwd)/logs:/app/logs" \
  -v "$(pwd)/csv_files:/app/csv_files" \
  -v "$(pwd)/owned_cards:/app/owned_cards" \
  -v "$(pwd)/config:/app/config" \
  mwisnowski/mtg-python-deckbuilder:latest \
  bash -lc "cd /app && uvicorn code.web.app:app --host 0.0.0.0 --port 8080"

echo
echo "Open: http://localhost:8080"
echo "Tips:"
echo "  export THEME=light|dark|system before running to change the theme"
echo "  export ENABLE_BUDGET_MODE=0 to disable budget controls"
echo "  export SHOW_LOGS=0 or SHOW_DIAGNOSTICS=0 to hide those pages"
