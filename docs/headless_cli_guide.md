# Headless & CLI Guide

Leverage the shared deckbuilding engine from the command line, in headless mode, or within containers.

## Table of contents
- [Entry points](#entry-points)
- [Switching modes in Docker](#switching-modes-in-docker)
- [Headless JSON configs](#headless-json-configs)
- [Environment overrides](#environment-overrides)
- [CLI argument reference](#cli-argument-reference)
- [Include/exclude lists from the CLI](#includeexclude-lists-from-the-cli)
- [Practical examples](#practical-examples)

---

## Entry points
- Interactive menu: `python code/main.py`
- Headless runner: `python code/headless_runner.py --config config/deck.json`
- Both executables share the same builder core used by the Web UI.

## Switching modes in Docker
Override the container entrypoint to run the CLI or headless flows inside Docker Compose or plain `docker run`.

```powershell
# Compose example
docker compose run --rm -e APP_MODE=cli web

# Compose with headless automation
docker compose run --rm `
  -e APP_MODE=cli `
  -e DECK_MODE=headless `
  -e DECK_CONFIG=/app/config/deck.json `
  web
```

Set `APP_MODE=cli` to switch from the Web UI to the textual interface. Add `DECK_MODE=headless` to skip prompts and immediately run the configured deck.

## Headless JSON configs
- Drop JSON files into `config/` (e.g., `config/deck.json`).
- Headless mode auto-runs the lone JSON file; if multiple exist, the CLI lists them with summaries (commander + themes).
- Config fields cover commander, bracket, include/exclude lists, theme preferences, owned-mode toggles, and output naming.
- Partner mechanics are optional: set `"enable_partner_mechanics": true` and supply either `"secondary_commander"` or `"background"` for combined commander runs.

## Environment overrides
When running in containers or automation, environment variables can override JSON settings. Typical variables include:
- `DECK_COMMANDER`
- `DECK_PRIMARY_CHOICE`, `DECK_SECONDARY_CHOICE`, `DECK_TERTIARY_CHOICE`
- `DECK_BRACKET_LEVEL`
- `DECK_ADD_LANDS`, `DECK_LAND_COUNT`, `DECK_CREATURE_COUNT`, `DECK_RAMP_COUNT`

Precedence order: **CLI flags > environment variables > JSON config > defaults**.

## CLI argument reference
Run `python code/headless_runner.py --help` to see the current argument surface. Highlights:

- Type indicators make expectations explicit (e.g., `PATH`, `NAME`, `INT`).
- Theme selection accepts human-readable names: `--primary-tag "Airbending"` instead of numeric indexes.
- Bracket selection via `--bracket-level`.
- Ideal counts such as `--land-count`, `--ramp-count`, `--creature-count`, and more.

## Include/exclude lists from the CLI
You can specify comma- or semicolon-separated lists directly through the CLI:

```powershell
python code/headless_runner.py `
  --commander "Jace, Vryn's Prodigy" `
  --include-cards "Sol Ring;Jace, the Mind Sculptor" `
  --exclude-cards "Chaos Orb;Shahrazad" `
  --enforcement-mode strict
```

Semicolons allow card names containing commas. Enforcement modes mirror the Web UI (`off`, `warn`, `strict`).

## Practical examples
```powershell
# Build a Goblins list with tuned counts
python code/headless_runner.py `
  --commander "Krenko, Mob Boss" `
  --primary-tag "Goblin Kindred" `
  --creature-count 35 `
  --land-count 33 `
  --ramp-count 12

# Fire a headless run via Docker using an alternate config folder
docker compose run --rm `
  -e APP_MODE=cli `
  -e DECK_MODE=headless `
  -e DECK_CONFIG=/app/config/custom_decks `
  web
```

The CLI prints a detailed summary at the end of each run, including enforcement results, resolved themes, and export paths. All artifacts land in the same `deck_files/` folder used by the Web UI.
