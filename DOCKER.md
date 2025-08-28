# Docker Guide

Run the MTG Deckbuilder (CLI and Web UI) in Docker with persistent volumes and optional headless mode.

## Quick start

### PowerShell (recommended)
```powershell
docker compose build
docker compose run --rm mtg-deckbuilder
```

### From Docker Hub (PowerShell)
```powershell
docker run -it --rm `
    -v "${PWD}/deck_files:/app/deck_files" `
    -v "${PWD}/logs:/app/logs" `
    -v "${PWD}/csv_files:/app/csv_files" `
    -v "${PWD}/owned_cards:/app/owned_cards" `
    -v "${PWD}/config:/app/config" `
    mwisnowski/mtg-python-deckbuilder:latest
```

## Web UI (new)

The web UI runs the same deckbuilding logic behind a browser-based interface.

### PowerShell (recommended)
```powershell
docker compose up --build --no-deps -d web
```

Then open http://localhost:8080

Volumes are the same as the CLI service, so deck exports/logs/configs persist in your working folder.
The app serves a favicon at `/favicon.ico` and exposes a health endpoint at `/healthz`.
Compare view offers a Copy summary button to copy a plain-text diff of two runs. The sidebar has a subtle depth shadow for clearer separation.

Web UI feature highlights:
- Locks: Click a card or the lock control in Step 5; locks persist across reruns.
- Replace: Enable Replace in Step 5, click a card to open Alternatives (filters include Owned-only), then choose a swap.
- Permalinks: Copy a permalink from Step 5 or a Finished deck; paste via “Open Permalink…” to restore.
- Compare: Use the Compare page from Finished Decks; quick actions include Latest two and Swap A/B.

Virtualized lists and lazy images (opt‑in)
- Set `WEB_VIRTUALIZE=1` to enable virtualization in Step 5 grids/lists and the Owned library for smoother scrolling on large sets.
- Example (Compose):
    ```yaml
    services:
        web:
            environment:
                - WEB_VIRTUALIZE=1
    ```
- Example (Docker Hub):
    ```powershell
    docker run --rm -p 8080:8080 `
        -e WEB_VIRTUALIZE=1 `
        -v "${PWD}/deck_files:/app/deck_files" `
        -v "${PWD}/logs:/app/logs" `
        -v "${PWD}/csv_files:/app/csv_files" `
        -v "${PWD}/owned_cards:/app/owned_cards" `
        -v "${PWD}/config:/app/config" `
    -e SHOW_DIAGNOSTICS=1 ` # optional: enables diagnostics tools and overlay
    mwisnowski/mtg-python-deckbuilder:latest `
        bash -lc "cd /app && uvicorn code.web.app:app --host 0.0.0.0 --port 8080"
    ```

### Diagnostics and logs (optional)
Enable internal diagnostics and a read-only logs viewer with environment flags.

- `SHOW_DIAGNOSTICS=1` — adds a Diagnostics nav link and `/diagnostics` tools
- `SHOW_LOGS=1` — enables `/logs` and `/status/logs?tail=200`

When enabled:
- `/logs` supports an auto-refresh toggle with interval, a level filter (All/Error/Warning/Info/Debug), and a Copy button to copy the visible tail.
- `/status/sys` returns a simple system summary (version, uptime, UTC server time, and feature flags) and is shown on the Diagnostics page when `SHOW_DIAGNOSTICS=1`.
 - Virtualization overlay: press `v` on pages with virtualized grids to toggle per-grid overlays and a global summary bubble.

Compose example (web service):
```yaml
environment:
    - SHOW_LOGS=1
    - SHOW_DIAGNOSTICS=1
```

Docker Hub (PowerShell) example:
```powershell
docker run --rm `
    -p 8080:8080 `
    -e SHOW_LOGS=1 -e SHOW_DIAGNOSTICS=1 -e ENABLE_THEMES=1 -e THEME=system `
    -v "${PWD}/deck_files:/app/deck_files" `
    -v "${PWD}/logs:/app/logs" `
    -v "${PWD}/csv_files:/app/csv_files" `
    -v "${PWD}/owned_cards:/app/owned_cards" `
    -v "${PWD}/config:/app/config" `
    mwisnowski/mtg-python-deckbuilder:latest `
    bash -lc "cd /app && uvicorn code.web.app:app --host 0.0.0.0 --port 8080"
```

### Setup speed: parallel tagging (Web)
First-time setup or stale data triggers card tagging. The web service uses parallel workers by default.

Configure via environment variables on the `web` service:
- `WEB_TAG_PARALLEL=1|0` — enable/disable parallel tagging (default: 1)
- `WEB_TAG_WORKERS=<N>` — number of worker processes (default: 4 in compose)

If parallel initialization fails, the service falls back to sequential tagging and continues.

### From Docker Hub (PowerShell)
If you prefer not to build locally, pull `mwisnowski/mtg-python-deckbuilder:latest` and run uvicorn:
```powershell
docker run --rm `
    -p 8080:8080 `
    -v "${PWD}/deck_files:/app/deck_files" `
    -v "${PWD}/logs:/app/logs" `
    -v "${PWD}/csv_files:/app/csv_files" `
    -v "${PWD}/owned_cards:/app/owned_cards" `
    -v "${PWD}/config:/app/config" `
    mwisnowski/mtg-python-deckbuilder:latest `
    bash -lc "cd /app && uvicorn code.web.app:app --host 0.0.0.0 --port 8080"
```

Health check:
```text
GET http://localhost:8080/healthz  ->  { "status": "ok", "version": "dev", "uptime_seconds": 123 }
```

Theme preference reset (client-side): use the header’s Reset Theme control to clear the saved browser preference; the server default (THEME) applies on next paint.

## Volumes
- `/app/deck_files` ↔ `./deck_files`
- `/app/logs` ↔ `./logs`
- `/app/csv_files` ↔ `./csv_files`
- `/app/owned_cards` ↔ `./owned_cards` (owned cards lists: .txt/.csv)
- Optional: `/app/config` ↔ `./config` (JSON configs for headless)

## Interactive vs headless
- Interactive: attach a TTY (compose run or `docker run -it`)
- Headless auto-run:
    ```powershell
    docker compose run --rm -e DECK_MODE=headless mtg-deckbuilder
    ```
- Headless with JSON config:
    ```powershell
    docker compose run --rm `
        -e DECK_MODE=headless `
        -e DECK_CONFIG=/app/config/deck.json `
        mtg-deckbuilder
    ```

### Common env vars
- DECK_MODE=headless
- DECK_CONFIG=/app/config/deck.json
- DECK_COMMANDER, DECK_PRIMARY_CHOICE
- DECK_ADD_LANDS, DECK_FETCH_COUNT
 - DECK_TAG_MODE=AND|OR (combine mode used by the builder)

### Web UI tuning env vars
- WEB_TAG_PARALLEL=1|0 (parallel tagging on/off)
- WEB_TAG_WORKERS=<N> (process count; set based on CPU/memory)
- WEB_VIRTUALIZE=1 (enable virtualization)
- SHOW_DIAGNOSTICS=1 (enables diagnostics pages and overlay hotkey `v`)

## Manual build/run
```powershell
docker build -t mtg-deckbuilder .
docker run -it --rm `
    -v "${PWD}/deck_files:/app/deck_files" `
    -v "${PWD}/logs:/app/logs" `
    -v "${PWD}/csv_files:/app/csv_files" `
    -v "${PWD}/owned_cards:/app/owned_cards" `
    -v "${PWD}/config:/app/config" `
    mtg-deckbuilder
```

## Troubleshooting
- No prompts? Use `docker compose run --rm` (not `up`) or add `-it` to `docker run`
- Files not saving? Verify volume mounts and that folders exist
- Headless not picking config? Ensure `./config` is mounted to `/app/config` and `DECK_CONFIG` points to a JSON file
- Owned-cards prompt not seeing files? Ensure `./owned_cards` is mounted to `/app/owned_cards`

## Tips
- Use `docker compose run`, not `up`, for interactive mode
- Exported decks appear in `deck_files/`
- JSON run-config is exported only in interactive runs; headless skips it
