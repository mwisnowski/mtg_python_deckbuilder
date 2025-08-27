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
docker compose build web
docker compose up --no-deps web
```

Then open http://localhost:8080

Volumes are the same as the CLI service, so deck exports/logs/configs persist in your working folder.
The app serves a favicon at `/favicon.ico` and exposes a health endpoint at `/healthz`.

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
