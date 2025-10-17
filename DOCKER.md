# Docker Guide

Spin up the MTG Python Deckbuilder inside containers. The image defaults to the Web UI; switch to the CLI/headless runner by flipping environment variables. All commands assume Windows PowerShell.

## Build a Deck (Web UI)

- Build the image (first run only) and start the `web` service in detached mode:

```powershell
docker compose up --build --no-deps -d web
```

- Open http://localhost:8080 to use the browser experience. First launch seeds data, downloads the latest card catalog, and tags cards automatically (`WEB_AUTO_SETUP=1`, `WEB_TAG_PARALLEL=1`, `WEB_TAG_WORKERS=4` in `docker-compose.yml`).

- Stop or restart the service when you're done:

```powershell
docker compose stop web
docker compose start web
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

Per-face MDFC snapshot (opt-in)
- `DFC_PER_FACE_SNAPSHOT=1` — write merged MDFC face metadata to `logs/dfc_per_face_snapshot.json`; disable parallel tagging (`WEB_TAG_PARALLEL=0`) if you need the snapshot during setup.
- `DFC_PER_FACE_SNAPSHOT_PATH=/app/logs/custom_snapshot.json` — optional path override for the snapshot artifact.

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

```powershell
docker run --rm -p 8080:8080 `
  -v "${PWD}/deck_files:/app/deck_files" `
  -v "${PWD}/logs:/app/logs" `
  -v "${PWD}/csv_files:/app/csv_files" `
  -v "${PWD}/config:/app/config" `
  -v "${PWD}/owned_cards:/app/owned_cards" `
  mwisnowski/mtg-python-deckbuilder:latest
```

### MDFC merge rollout (staging)

The web service now runs the MDFC merge by default. Set `DFC_COMPAT_SNAPSHOT=1` on the web service when you need the legacy unmerged compatibility snapshot (`csv_files/compat_faces/`). Combine this with `python -m code.scripts.refresh_commander_catalog --compat-snapshot` inside the container to regenerate the commander files before smoke testing.

Follow the QA steps in `docs/qa/mdfc_staging_checklist.md` after toggling the flag.

Compose example:

```yaml
services:
    web:
        environment:
            - DFC_COMPAT_SNAPSHOT=1
```

Verify the refresh inside the container:

```powershell
docker compose run --rm web bash -lc "python -m code.scripts.refresh_commander_catalog"
```

Downstream consumers can diff `csv_files/compat_faces/commander_cards_unmerged.csv` against historical exports during the staging window.

### Setup speed: parallel tagging (Web)
First-time setup or stale data triggers card tagging. The web service uses parallel workers by default.

## Run a JSON Config

Use the homepage “Run a JSON Config” button or run the same flow in-container:

```powershell
docker compose run --rm `
  -e APP_MODE=cli `
  -e DECK_MODE=headless `
  -e DECK_CONFIG=/app/config/deck.json `
  web
```

- `APP_MODE=cli` routes the entrypoint to the CLI menu.
- `DECK_MODE=headless` skips prompts and calls `headless_runner`.
- Mount JSON configs under `config/` so both the UI and CLI can pick them up.
- Dual-commander support is feature-flagged: set `ENABLE_PARTNER_MECHANICS=1` and pass `--secondary-commander` _or_ `--background` (mutually exclusive) to layer partners/backgrounds into headless runs; Partner With and Doctor/Doctor’s Companion pairings auto-resolve (with opt-out), and `--dry-run` echoes the resolved pairing for verification.
- Partner suggestions share the same dataset for headless and web flows; set `ENABLE_PARTNER_SUGGESTIONS=1` (and ensure `config/analytics/partner_synergy.json` exists) to expose ranked pairings in the UI and API.

Override counts, theme tags, or include/exclude lists by setting the matching environment variables before running the container (see “Environment variables” below).

## Initial Setup

The homepage “Initial Setup” tile appears when `SHOW_SETUP=1` (enabled in compose). It re-runs:

1. Card downloads and color-filtered CSV generation.
2. Commander catalog rebuild (including multi-face merges).
3. Tagging and caching.

To force a rebuild from the host:

```powershell
docker compose run --rm --entrypoint bash web -lc "python -m code.file_setup.setup"
```

Add `--entrypoint bash ... "python -m code.scripts.refresh_commander_catalog"` when you only need the commander catalog (with MDFC merge and optional compatibility snapshot).

## Owned Library

Store `.txt` or `.csv` lists in `owned_cards/` (mounted to `/app/owned_cards`). The Web UI uses them for:

- Owned-only or prefer-owned builds.
- The Owned Library management page (virtualized when `WEB_VIRTUALIZE=1`).
- Alternative suggestions that respect ownership.

Use `/owned` to upload files and export enriched lists. These files persist through the `owned_cards` volume.

## Browse Commanders

`SHOW_COMMANDERS=1` exposes the commander browser tile.

- Data lives in `csv_files/commander_cards.csv`.
- Refresh the catalog (including MDFC merges) from within the container:

```powershell
docker compose run --rm --entrypoint bash web -lc "python -m code.scripts.refresh_commander_catalog"
```

Pass `--compat-snapshot` if you also need an unmerged compatibility CSV under `csv_files/compat_faces/`.

## Finished Decks

The Finished Decks page reads the `deck_files/` volume for completed builds:

- Each run produces CSV, TXT, compliance JSON, and summary JSON sidecars.
- Locks and replace history persist per deck.
- Compare view can diff and export summaries.

Ensure the deck exports volume remains mounted so these artifacts survive container restarts.

## Browse Themes

The Themes browser exposes the merged theme catalog with search, filters, and diagnostics.

- `ENABLE_THEMES=1` keeps the selector visible.
- `WEB_THEME_PICKER_DIAGNOSTICS=1` unlocks uncapped synergies, extra metadata, and `/themes/metrics`.
- Regenerate the catalog manually:

```powershell
docker compose run --rm --entrypoint bash web -lc "python -m code.scripts.build_theme_catalog"
```

Advanced options (e.g., `EDITORIAL_*` variables) live in `.env.example`.

## Random Build

Enable the Surprise/Reroll flow by setting:

- `RANDOM_MODES=1` to expose backend random endpoints.
- `RANDOM_UI=1` to show the Random Build tile.
- Optional tunables: `RANDOM_MAX_ATTEMPTS`, `RANDOM_TIMEOUT_MS`, `RANDOM_PRIMARY_THEME`, `RANDOM_SEED`, and auto-fill flags.

Headless parity is available by pairing `APP_MODE=cli` with `DECK_MODE=headless` and the same random variables.

## Diagnostics

`SHOW_DIAGNOSTICS=1` unlocks `/diagnostics` for system summaries, feature flags, and performance probes. Highlights:

- `/healthz` returns `{status, version, uptime_seconds}` for external monitoring.
- Press `v` on pages with virtualized grids (when `WEB_VIRTUALIZE=1`) to toggle the range overlay.
- `WEB_AUTO_ENFORCE=1` (optional) applies bracket enforcement automatically after each build.

## View Logs

`SHOW_LOGS=1` enables the logs tile and `/logs` interface:

- Tail the container log with filtering and copy-to-clipboard.
- `/status/logs?tail=200` offers a lightweight JSON endpoint.
- Raw files live under `logs/` on the host; rotate or archive them as needed.

## Environment variables (Docker quick reference)

See `.env.example` for the full catalog. Common knobs:

### Core mode and networking

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_MODE` | `web` | Switch between Web UI (`web`) and CLI (`cli`). |
| `DECK_MODE` | _(unset)_ | `headless` auto-runs the headless builder when the CLI starts. |
| `DECK_CONFIG` | `/app/config/deck.json` | JSON config file or directory (auto-discovery). |
| `HOST` / `PORT` / `WORKERS` | `0.0.0.0` / `8080` / `1` | Uvicorn binding when `APP_MODE=web`. |

### Partner mechanics & suggestions

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENABLE_PARTNER_MECHANICS` | `0` | Unlock partner/background commander inputs for headless runs and Step 2 of the web UI. |
| `ENABLE_PARTNER_SUGGESTIONS` | `0` | Serve partner/background/Doctor suggestion chips based on `config/analytics/partner_synergy.json` (auto-regenerated when missing; override path with `PARTNER_SUGGESTIONS_DATASET`). |

### Homepage visibility & UX

| Variable | Default | Purpose |
| --- | --- | --- |
| `SHOW_SETUP` | `1` | Show the Initial Setup card. |
| `SHOW_LOGS` | `1` | Enable the View Logs tile and endpoints. |
| `SHOW_DIAGNOSTICS` | `1` | Enable Diagnostics tools and overlays. |
| `SHOW_COMMANDERS` | `1` | Expose the commander browser. |
| `ENABLE_THEMES` | `1` | Keep the theme selector and themes explorer visible. |
| `WEB_VIRTUALIZE` | `1` | Opt-in to virtualized lists/grids for large result sets. |
| `ALLOW_MUST_HAVES` | `1` | Enable include/exclude enforcement in Step 5. |
| `SHOW_MUST_HAVE_BUTTONS` | `0` | Surface the must include/exclude buttons and quick-add UI (requires `ALLOW_MUST_HAVES=1`). |
| `THEME` | `dark` | Initial UI theme (`system`, `light`, or `dark`). |
| `WEB_STAGE_ORDER` | `new` | Build stage execution order: `new` (creatures→spells→lands) or `legacy` (lands→creatures→spells). |
| `WEB_IDEALS_UI` | `slider` | Ideal counts interface: `slider` (range inputs with live validation) or `input` (text boxes with placeholders). |
| `ENABLE_CARD_DETAILS` | `0` | Show card detail pages with similar card recommendations at `/cards/<name>`. |
| `SIMILARITY_CACHE_ENABLED` | `1` | Use pre-computed similarity cache for fast card detail pages. |

### Random build controls

| Variable | Default | Purpose |
| --- | --- | --- |
| `RANDOM_MODES` | _(unset)_ | Enable random build endpoints. |
| `RANDOM_UI` | _(unset)_ | Show the Random Build homepage tile. |
| `RANDOM_MAX_ATTEMPTS` | `5` | Retry budget for constrained random rolls. |
| `RANDOM_TIMEOUT_MS` | `5000` | Per-attempt timeout in milliseconds. |
| `RANDOM_REROLL_THROTTLE_MS` | `350` | Minimum ms between reroll requests (client guard). |
| `RANDOM_STRUCTURED_LOGS` | `0` | Emit structured JSON logs for random builds. |
| `RANDOM_TELEMETRY` | `0` | Enable lightweight timing/attempt counters. |
| `RANDOM_PRIMARY_THEME` / `RANDOM_SECONDARY_THEME` / `RANDOM_TERTIARY_THEME` | _(blank)_ | Override theme slots for random runs. |
| `RANDOM_SEED` | _(blank)_ | Deterministic seed. |
| `RANDOM_AUTO_FILL` | `1` | Allow automatic backfill of missing theme slots. |

### Automation & performance

| Variable | Default | Purpose |
| --- | --- | --- |
| `WEB_AUTO_SETUP` | `1` | Auto-run data setup when artifacts are missing or stale. |
| `WEB_AUTO_REFRESH_DAYS` | `7` | Refresh `cards.csv` if older than N days. |
| `WEB_TAG_PARALLEL` | `1` | Use parallel workers during tagging. |
| `WEB_TAG_WORKERS` | `4` | Worker count for parallel tagging. |
| `WEB_AUTO_ENFORCE` | `0` | Re-export decks after auto-applying compliance fixes. |
| `WEB_THEME_PICKER_DIAGNOSTICS` | `1` | Enable theme diagnostics endpoints. |

### Paths and data overrides

| Variable | Default | Purpose |
| --- | --- | --- |
| `CSV_FILES_DIR` | `/app/csv_files` | Point the app at an alternate dataset (e.g., test snapshots). |
| `DECK_EXPORTS` | `/app/deck_files` | Override where the web UI looks for exports. |
| `OWNED_CARDS_DIR` / `CARD_LIBRARY_DIR` | `/app/owned_cards` | Override owned library directory. |
| `CARD_INDEX_EXTRA_CSV` | _(blank)_ | Inject a synthetic CSV into the card index for testing. |

### Supplemental themes

| Variable | Default | Purpose |
| --- | --- | --- |
| `DECK_ADDITIONAL_THEMES` | _(blank)_ | Comma/semicolon separated list of supplemental themes for headless builds (JSON exports also include the camelCase `userThemes` alias and `themeCatalogVersion` metadata; either alias is accepted on import). |
| `THEME_MATCH_MODE` | `permissive` | Controls fuzzy theme resolution (`strict` blocks unresolved inputs). |

### Random rate limiting (optional)

| Variable | Default | Purpose |
| --- | --- | --- |
| `RATE_LIMIT_ENABLED` | `0` | Enable server-side rate limiting for random endpoints. |
| `RATE_LIMIT_WINDOW_S` | `10` | Rolling window in seconds. |
| `RATE_LIMIT_RANDOM` | `10` | Max random attempts per window. |
| `RATE_LIMIT_BUILD` | `10` | Max full builds per window. |
| `RATE_LIMIT_SUGGEST` | `30` | Max suggestion calls per window. |

Advanced editorial and theme-catalog knobs (`EDITORIAL_*`, `SPLASH_ADAPTIVE`, etc.) are documented inline in `docker-compose.yml` and `.env.example`.

## Shared volumes

| Host path | Container path | Contents |
| --- | --- | --- |
| `deck_files/` | `/app/deck_files` | CSV/TXT exports, summary JSON, compliance reports. |
| `logs/` | `/app/logs` | Application logs and taxonomy snapshots. |
| `csv_files/` | `/app/csv_files` | Card datasets, commander catalog, tagging flags. |
| `config/` | `/app/config` | JSON configs, bracket policy, card list overrides. |
| `owned_cards/` | `/app/owned_cards` | Uploaded inventory files for owned-only flows. |

## Maintenance commands

Run ad-hoc tasks by overriding the entrypoint:

```powershell
# Theme catalog rebuild
docker compose run --rm --entrypoint bash web -lc "python -m code.scripts.build_theme_catalog"

# Snapshot taxonomy (writes logs/taxonomy_snapshots/)
docker compose run --rm --entrypoint bash web -lc "python -m code.scripts.snapshot_taxonomy"

# Preview the MDFC commander diff
docker compose run --rm --entrypoint bash web -lc "python -m code.scripts.preview_dfc_catalog_diff"
```

Use the `--compat-snapshot` or other script arguments as needed.

## Troubleshooting

- **Container starts but UI stays blank:** check `/healthz` and `/logs` (enable with `SHOW_LOGS=1`), then inspect the `logs/` volume.
- **Files missing on the host:** ensure the host directories exist before starting Compose; Windows will create empty folders if the path is invalid.
- **Long first boot:** dataset downloads and tagging can take several minutes the first time. Watch progress at `/setup`.
- **Random build hangs:** lower `RANDOM_MAX_ATTEMPTS` or raise `RANDOM_TIMEOUT_MS`, and confirm your theme overrides are valid slugs via `/themes/`.
- **Commander catalog outdated:** rerun the refresh command above or delete `csv_files/.tagging_complete.json` to force a full rebuild on next start.
