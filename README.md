# 🃏 MTG Python Deckbuilder

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-supported-blue.svg)](https://www.docker.com/)

A web-first Commander/EDH deckbuilder with a shared core for CLI, headless, and Docker workflows. It builds curated decks, enforces bracket policies, understands owned cards, and ships a modern FastAPI + HTMX UI.

- **Web UI priority**: All homepage actions map to the sections below.
- **Shared logic**: Web, CLI, and headless runs use the same builder engine and exports.
- **Deterministic outputs**: Random modes respect seeds, include/exclude lists, and bracket rules.
- **Data-aware UX**: Owned library, themes, commanders, diagnostics, and logs live side-by-side.

---

## Table of contents
- [Quick start](#quick-start)
- [Homepage guide](#homepage-guide)
  - [Build a Deck](#build-a-deck)
  - [Run a JSON Config](#run-a-json-config)
  - [Initial Setup](#initial-setup)
  - [Owned Library](#owned-library)
  - [Browse Commanders](#browse-commanders)
  - [Browse Themes](#browse-themes)
  - [Finished Decks](#finished-decks)
  - [Random Build](#random-build)
  - [Diagnostics](#diagnostics)
  - [View Logs](#view-logs)
- [CLI & headless flows](#cli--headless-flows)
- [Data, exports, and volumes](#data-exports-and-volumes)
- [Environment variables](#environment-variables)
- [Project layout](#project-layout)
- [Development setup](#development-setup)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License & attribution](#license--attribution)
- [Further reading](#further-reading)

---

## Quick start
Pick the path that fits your setup. All commands target Windows PowerShell.

### Option 1 — Docker Compose (recommended web experience)
```powershell
docker compose up --build --no-deps -d web
```
The Web UI starts on http://localhost:8080. First boot seeds data, refreshes decks, and tags cards automatically (see env defaults in `docker-compose.yml`). Use `docker compose stop web` / `docker compose start web` to pause or resume.

### Option 2 — Docker Hub image
```powershell
docker run --rm -p 8080:8080 `
  -v "${PWD}/deck_files:/app/deck_files" `
  -v "${PWD}/logs:/app/logs" `
  -v "${PWD}/csv_files:/app/csv_files" `
  -v "${PWD}/config:/app/config" `
  -v "${PWD}/owned_cards:/app/owned_cards" `
  mwisnowski/mtg-python-deckbuilder:latest
```
Brings up the same web UI using the prebuilt image. All volumes persist on the host.

### Option 3 — Run from source
```powershell
python -m venv .venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn code.web.app:app --host 127.0.0.1 --port 8080
```
CLI entry point: `python code/main.py`. Headless convenience runner: `python code/headless_runner.py --config config/deck.json`.

For deeper Docker notes (including headless runs, impersonating CLI via compose, and maintenance scripts) see [`DOCKER.md`](DOCKER.md).

---

## Homepage guide
Every tile on the homepage connects to a workflow. Use these sections as your tour.

### Build a Deck
Start here for interactive deck creation.
- Pick commander, themes (primary/secondary/tertiary), bracket, and optional deck name in the unified modal.
- Add supplemental themes in the **Additional Themes** section (ENABLE_CUSTOM_THEMES): fuzzy suggestions, removable chips, and strict/permissive matching toggles respect `THEME_MATCH_MODE` and `USER_THEME_LIMIT`.
- Partner mechanics (ENABLE_PARTNER_MECHANICS): Step 2 and the quick-start modal auto-enable partner controls for eligible commanders, show only legal partner/background/Doctor options, and keep previews, warnings, and theme chips in sync.
  - Partner suggestions (ENABLE_PARTNER_SUGGESTIONS): ranked chips appear beside the partner selector, recommending popular partner/background/Doctor pairings based on the analytics dataset; selections respect existing partner mode and lock states.
  - Partner: pick a second commander from the filtered dropdown labeled “Partner commander”; the background picker clears automatically.
  - Partner With: the canonical partner pre-fills and surfaces an opt-out chip so you can keep or swap the suggestion.
  - Doctor / Doctor’s Companion: Doctors list legal companions (and vice versa) with role labels, and the opt-out chip mirrors Partner With behavior.
  - Background: choose a Background instead of a second commander; partner selectors hide when not applicable.
- Locks, Replace, Compare, and Permalinks live in Step 5.
- Exports (CSV, TXT, compliance JSON, summary JSON) land in `deck_files/` and reuse your chosen deck name when set. CSV/TXT headers now include commander metadata (names, partner mode, colors) so downstream tools can pick up dual-commander context without extra parsing.
- `ALLOW_MUST_HAVES=1` (default) enables include/exclude enforcement.
- `WEB_AUTO_ENFORCE=1` re-runs bracket enforcement automatically after each build.

### Run a JSON Config
Execute saved configs without manual input.
- Place JSON configs under `config/` (see `config/deck.json` for a template).
- Launch via homepage button or by running the container with `APP_MODE=cli` and `DECK_MODE=headless`.
- Respect include/exclude, owned, and theme overrides defined in the config file or env vars.
- Supplemental themes: add `"additional_themes": ["Theme A", "Theme B"]` plus `"theme_match_mode": "permissive"|"strict"`. Strict mode stops the build when a theme cannot be resolved; permissive keeps going and prints suggestions. Exported configs also include a camelCase alias (`"userThemes"`) and the active catalog version (`"themeCatalogVersion"`); either field name is accepted on import.

### Initial Setup
Refresh data and caches when formats shift.
- Runs card downloads, CSV regeneration, smart tagging (keywords + protection grants), and commander catalog rebuilds.
- Controlled by `SHOW_SETUP=1` (on by default in compose).
- Force a rebuild manually:
  ```powershell
  docker compose run --rm --entrypoint bash web -lc "python -m code.file_setup.setup"
  ```
- Rebuild only the commander catalog:
  ```powershell
  docker compose run --rm --entrypoint bash web -lc "python -m code.scripts.refresh_commander_catalog"
  ```

### Owned Library
Keep track of cards you own.
- Upload `.txt` or `.csv` lists; the app enriches and deduplicates entries.
- Owned-only and Prefer-owned build modes live in the New Deck modal.
- `owned_cards/` is persisted via volume mounting (`OWNED_CARDS_DIR=/app/owned_cards`).
- Enable virtualization for large libraries with `WEB_VIRTUALIZE=1`.

### Browse Commanders
Explore the curated commander catalog.
- Powered by `csv_files/commander_cards.csv`.
- Toggle the tile with `SHOW_COMMANDERS=1`.
- Refresh via Initial Setup or the commander catalog script above.
- MDFC merges and compatibility snapshots are handled automatically; use `--compat-snapshot` on the refresh script to emit an unmerged snapshot.

### Browse Themes
Investigate theme synergies and diagnostics.
- `ENABLE_THEMES=1` keeps the tile visible (default).
- Extra tooling (`/themes/metrics`, uncapped synergies, editorial quality) is gated by `WEB_THEME_PICKER_DIAGNOSTICS=1`.
- Rebuild the merged catalog as needed:
  ```powershell
  docker compose run --rm --entrypoint bash web -lc "python -m code.scripts.build_theme_catalog"
  ```
- Generate the normalized supplemental theme catalog (commander & card counts) for user-added themes:
  ```powershell
  python -m code.scripts.generate_theme_catalog --output config/themes/theme_catalog.csv
  ```
  Add `--logs-dir logs/generated` to mirror the CSV for diffing, or `--csv-dir` to point at alternate datasets.
- Advanced editorial knobs (`EDITORIAL_*`, `SPLASH_ADAPTIVE`, etc.) live in `.env.example` and are summarized in the env table below.

### Finished Decks
Review, compare, and export previous builds.
- Reads from the `deck_files/` volume.
- Compare view can diff two builds, copy summaries, and download text lists.
- Locks, replace history, and compliance metadata persist per deck.

### Random Build
Spin up surprise decks with deterministic fallbacks.
- Enable backend endpoints with `RANDOM_MODES=1` and the UI tile with `RANDOM_UI=1`.
- Fine-tune with `RANDOM_MAX_ATTEMPTS`, `RANDOM_TIMEOUT_MS`, `RANDOM_PRIMARY_THEME`, `RANDOM_SEED`, and `RANDOM_AUTO_FILL`.
- Random flows honor include/exclude lists, owned filters, and bracket enforcement.

### Diagnostics
Peek at health & performance.
- Enabled via `SHOW_DIAGNOSTICS=1`.
- `/diagnostics` summarizes system status, feature flags, and theme metrics.
- `/healthz` offers a lightweight probe (`{status, version, uptime_seconds}`).
- Press `v` inside virtualized lists (when `WEB_VIRTUALIZE=1`) to view grid diagnostics.

### View Logs
Tail and download logs without leaving the browser.
- Enabled via `SHOW_LOGS=1`.
- `/logs` shows recent entries, filtering, and copy-to-clipboard.
- Raw files live under the mounted `logs/` directory.
- `/status/logs?tail=N` returns JSON payloads for automation.

---

## CLI & headless flows
The CLI and headless runners share the builder core.
- Launch menu-driven CLI: `python code/main.py`.
- Run headless (non-interactive) builds: `python code/headless_runner.py --config config/deck.json`.
- In Docker, set `APP_MODE=cli` (and optionally `DECK_MODE=headless`) to switch the container entrypoint to the CLI.
- Config precedence is CLI prompts > environment variables > JSON config > defaults.
- Dual-commander support (feature-flagged): `--secondary-commander` or `--background` (mutually exclusive) can be supplied alongside `--enable-partner-mechanics true` or `ENABLE_PARTNER_MECHANICS=1`; Partner With and Doctor/Doctor’s Companion pairings auto-resolve (respecting opt-outs), dry runs echo the resolved pairing, and JSON configs may include `secondary_commander`, `background`, and `enable_partner_mechanics` keys.

---

## Data, exports, and volumes
| Host path | Container path | Purpose |
| --- | --- | --- |
| `deck_files/` | `/app/deck_files` | CSV/TXT exports, compliance JSON, summary JSON |
| `logs/` | `/app/logs` | Application logs, taxonomy snapshots |
| `csv_files/` | `/app/csv_files` | Card datasets, commander catalog, tagging metadata |
| `config/` | `/app/config` | JSON configs, bracket policies, themes, card lists |
| `owned_cards/` | `/app/owned_cards` | Uploaded owned-card libraries |

Exports follow a stable naming scheme and include a `.summary.json` sidecar containing deck metadata, resolved themes, combined commander payloads, and lock history.

---

## Environment variables
Most defaults are defined in `docker-compose.yml` and documented in `.env.example`. Highlights:

### Core modes & networking
| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_MODE` | `web` | Switch between Web UI (`web`) and CLI (`cli`). |
| `DECK_MODE` | _(unset)_ | `headless` auto-runs the builder in CLI mode. |
| `DECK_CONFIG` | `/app/config/deck.json` | Points the headless runner at a config file or folder. |
| `HOST` / `PORT` / `WORKERS` | `0.0.0.0` / `8080` / `1` | Uvicorn settings for the web server. |

### Partner / Background mechanics (feature-flagged)
| Variable | Default | Purpose |
| --- | --- | --- |
| `ENABLE_PARTNER_MECHANICS` | `0` | Unlock partner/background commander inputs for headless runs and the web builder Step 2 UI. |
| `ENABLE_PARTNER_SUGGESTIONS` | `0` | Surface partner/background/Doctor suggestion chips backed by `config/analytics/partner_synergy.json` (auto-regenerated when missing; override path with `PARTNER_SUGGESTIONS_DATASET`). |

### Homepage visibility & UX
| Variable | Default | Purpose |
| --- | --- | --- |
| `SHOW_SETUP` | `1` | Show the Initial Setup tile. |
| `SHOW_LOGS` | `1` | Enable the logs viewer tile and endpoints. |
| `SHOW_DIAGNOSTICS` | `1` | Unlock diagnostics views and overlays. |
| `SHOW_COMMANDERS` | `1` | Enable the commander browser. |
| `ENABLE_THEMES` | `1` | Keep the theme browser and selector active. |
| `ENABLE_CUSTOM_THEMES` | `1` | Surface the Additional Themes section in the New Deck modal. |
| `WEB_VIRTUALIZE` | `1` | Opt into virtualized lists for large datasets. |
| `ALLOW_MUST_HAVES` | `1` | Enforce include/exclude (must-have) lists. |
| `SHOW_MUST_HAVE_BUTTONS` | `0` | Reveal the must include/exclude buttons and quick-add UI (requires `ALLOW_MUST_HAVES=1`). |
| `THEME` | `dark` | Default UI theme (`system`, `light`, or `dark`). |

### Random build tuning
| Variable | Default | Purpose |
| --- | --- | --- |
| `RANDOM_MODES` | _(unset)_ | Expose random build endpoints. |
| `RANDOM_UI` | _(unset)_ | Show the Random Build homepage tile. |
| `RANDOM_MAX_ATTEMPTS` | `5` | Retry budget when constraints are tight. |
| `RANDOM_TIMEOUT_MS` | `5000` | Per-attempt timeout in milliseconds. |
| `RANDOM_REROLL_THROTTLE_MS` | `350` | Minimum milliseconds between reroll requests (client-side guard). |
| `RANDOM_STRUCTURED_LOGS` | `0` | Emit structured JSON logs for random builds. |
| `RANDOM_TELEMETRY` | `0` | Enable lightweight timing/attempt metrics for diagnostics. |
| `RANDOM_PRIMARY_THEME` / `RANDOM_SECONDARY_THEME` / `RANDOM_TERTIARY_THEME` | _(blank)_ | Override selected themes. |
| `RANDOM_SEED` | _(blank)_ | Deterministic seed for reproducible builds. |
| `RANDOM_AUTO_FILL` | `1` | Allow auto-fill of missing theme slots. |

### Random rate limiting (optional)
| Variable | Default | Purpose |
| --- | --- | --- |
| `RATE_LIMIT_ENABLED` | `0` | Enable server-side rate limiting for random endpoints. |
| `RATE_LIMIT_WINDOW_S` | `10` | Rolling window size in seconds. |
| `RATE_LIMIT_RANDOM` | `10` | Max random attempts per window. |
| `RATE_LIMIT_BUILD` | `10` | Max full builds per window. |
| `RATE_LIMIT_SUGGEST` | `30` | Max suggestion calls per window. |

### Automation & performance
| Variable | Default | Purpose |
| --- | --- | --- |
| `WEB_AUTO_SETUP` | `1` | Auto-run setup when artifacts are missing or stale. |
| `WEB_AUTO_REFRESH_DAYS` | `7` | Refresh `cards.csv` if older than N days. |
| `WEB_TAG_PARALLEL` | `1` | Enable parallel tagging workers. |
| `WEB_TAG_WORKERS` | `4` | Worker count for tagging (compose default). |
| `WEB_AUTO_ENFORCE` | `0` | Auto-apply bracket enforcement after builds. |
| `WEB_THEME_PICKER_DIAGNOSTICS` | `1` | Enable theme diagnostics endpoints. |

### Paths & overrides
| Variable | Default | Purpose |
| --- | --- | --- |
| `CSV_FILES_DIR` | `/app/csv_files` | Alternate dataset location (useful for tests). |
| `DECK_EXPORTS` | `/app/deck_files` | Override where exports land. |
| `OWNED_CARDS_DIR` / `CARD_LIBRARY_DIR` | `/app/owned_cards` | Override owned library path. |
| `CARD_INDEX_EXTRA_CSV` | _(blank)_ | Inject extra CSV data into the card index. |

### Testing aids
| Variable | Default | Purpose |
| --- | --- | --- |
| `EDITORIAL_TEST_USE_FIXTURES` | `0` | When set to `1`, editorial governance tests stage lightweight catalog fixtures instead of requiring generated YAML/JSON data. |

### Supplemental themes
| Variable | Default | Purpose |
| --- | --- | --- |
| `DECK_ADDITIONAL_THEMES` | _(blank)_ | Comma/semicolon separated list of supplemental themes to apply in headless builds. |
| `THEME_MATCH_MODE` | `permissive` | Controls fuzzy resolution strictness (`strict` blocks unresolved themes) and seeds the web UI default. |
| `USER_THEME_LIMIT` | `8` | Maximum number of user-supplied themes allowed in the web builder. |

Refer to `.env.example` for advanced editorial, taxonomy, and experimentation knobs (`EDITORIAL_*`, `SPLASH_ADAPTIVE`, `WEB_THEME_FILTER_PREWARM`, etc.). Document any newly introduced variables in the README, DOCKER guide, compose files, and `.env.example`.

---

## Project layout
```
code/                 FastAPI app, deckbuilding engine, CLI, scripts, and tests
├─ web/               Web UI (FastAPI + Jinja2 + HTMX)
├─ deck_builder/      Core builder logic and services
├─ tagging/           Tag pipelines and utilities
├─ locks/             Card locking utilities
├─ scripts/           Maintenance and editorial tools
├─ tests/             Pytest suite (web, CLI, random, tagging)
config/               JSON configs, bracket policies, themes, card lists
csv_files/            Card datasets, commander catalog, theme outputs
owned_cards/          User-supplied owned lists
logs/                 Application logs and taxonomy snapshots
deck_files/           Generated deck exports (CSV/TXT/JSON)
```

---

## Development setup
1. Create and activate the virtual environment:
   ```powershell
   python -m venv .venv
   .\venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```powershell
   pip install -r requirements.txt -r requirements-dev.txt
   ```
3. Run the web app locally:
   ```powershell
   uvicorn code.web.app:app --host 127.0.0.1 --port 8080
   ```
4. Run tests (prefer targeted files—no wildcards):
   ```powershell
   C:/Users/Matt/mtg_python/mtg_python_deckbuilder/.venv/Scripts/python.exe -m pytest -q code/tests/test_random_determinism.py code/tests/test_permalinks_and_locks.py
   ```
   Use `tasks.json` entries such as `pytest-fast-random` or `pytest-fast-locks` for quick feedback.
5. Linting and type checks follow `pyproject.toml` / `mypy.ini` defaults. Keep changes minimal and well-typed.

When adding features, favor the web UI first, keep public builder APIs stable, and update documentation (CHANGELOG → RELEASE_NOTES_TEMPLATE → DOCKER → README) in that order.

---

## Troubleshooting
- **Blank page after start**: Visit `/healthz`, check `/logs`, ensure `SHOW_LOGS=1`, and inspect host `logs/` for stack traces.
- **Stale data**: Run Initial Setup or delete `csv_files/.tagging_complete.json` to force reseeding.
- **Owned-only build fails**: Confirm owned files were uploaded correctly and that `owned_cards/` is mounted.
- **Random build stalls**: Lower `RANDOM_MAX_ATTEMPTS`, increase `RANDOM_TIMEOUT_MS`, and verify selected themes exist via `/themes/`.
- **Commander list outdated**: Rerun the commander refresh script or Initial Setup.

---

## Contributing
Pull requests are welcome—follow the conventional commit style, keep diffs focused, add or update tests when behavior changes, and document new env vars or workflows. Review `CONTRIBUTING_EDITORIAL.md` for editorial tooling guidance.

---

## License & attribution
Licensed under the [MIT License](LICENSE). Card data and imagery are provided by [Scryfall](https://scryfall.com); please respect their [API terms](https://scryfall.com/docs/api).

---

## Further reading
- [Web UI deep dive](docs/web_ui_deep_dive.md) – advanced Stage 5 tooling, multi-copy packages, virtualization tips, and diagnostics overlays.
- [Theme catalog advanced guide](docs/theme_catalog_advanced.md) – API endpoints, governance policies, editorial tooling, and validation scripts.
- [Headless & CLI guide](docs/headless_cli_guide.md) – automation entry points, environment overrides, and argument walkthroughs.
- [Commander catalog handbook](docs/commander_catalog.md) – required columns, refresh workflow, and staging toggles.
- [Random theme exclusions reference](docs/random_theme_exclusions.md) – curation guidance for curated pools.
- [Theme taxonomy rationale](docs/theme_taxonomy_rationale.md) – roadmap and philosophy behind theme governance.