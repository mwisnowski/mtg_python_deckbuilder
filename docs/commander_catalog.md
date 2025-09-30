# Commander Catalog Onboarding

The Commander Browser and deck builder both read from `csv_files/commander_cards.csv`. This file is generated during setup and must stay in sync with the fields the web UI expects. Use this guide whenever you need to add a new commander, refresh the dataset, or troubleshoot missing entries.

## Where the file lives

- Default path: `csv_files/commander_cards.csv`
- Override: set `CSV_FILES_DIR` (env var) before launching the app; the loader resolves `commander_cards.csv` inside that directory.
- Caching: the web layer caches the parsed file in process. Restart the app or call `clear_commander_catalog_cache()` in a shell if you edit the CSV while the server is running.

## Required columns

The loader normalizes these columns; keep the header names exact. Optional fields can be blank but should still be present.

| Column | Notes |
| --- | --- |
| `name` | Printed front name. Used as the fallback display label.
| `faceName` | Front face name for MDFCs/split cards. Defaults to `name` when empty.
| `side` | Leave blank or `A` for the primary face. Secondary faces become distinct slugs.
| `colorIdentity` | WUBRG characters (any casing). `C` marks colorless identities.
| `colors` | Printed colors; mainly used for ordering badges.
| `manaCost` | Optional but keeps rows sortable in the UI.
| `manaValue` | Numeric converted mana cost.
| `type` | Full type line (e.g., `Legendary Creature — Phyrexian Angel`).
| `creatureTypes` | Python/JSON list or comma-separated string of creature subtypes.
| `text` | Oracle text. Enables partner/background detection and hover tooltips.
| `power` / `toughness` | Optional stats. Leave blank for non-creatures.
| `keywords` | Comma-separated keywords (Flying, Vigilance, …).
| `themeTags` | Python/JSON list of curated themes (e.g., `['Angels', 'Life Gain']`).
| `edhrecRank` | Optional EDHREC popularity rank (integer).
| `layout` | Layout string from MTGJSON (`normal`, `modal_dfc`, etc.).

Additional columns are preserved but ignored by the browser; feel free to keep upstream metadata.

## Recommended refresh workflow

1. Ensure dependencies are installed: `pip install -r requirements.txt`.
2. Regenerate the commander CSV using the setup module:
   ```powershell
   python -c "from file_setup.setup import regenerate_csvs_all; regenerate_csvs_all()"
   ```
   This downloads the latest MTGJSON card dump (if needed), reapplies commander eligibility rules, and rewrites `commander_cards.csv`.
3. (Optional) If you only need a fresh commander list and already have up-to-date `cards.csv`, run:
   ```powershell
   python -c "from file_setup.setup import determine_commanders; determine_commanders()"
   ```
4. Restart the web server (or your desktop app) so the cache reloads the new file.
5. Validate with the targeted test:
   ```powershell
   python -m pytest -q code/tests/test_commander_catalog_loader.py
   ```
   The test confirms required columns exist, normalization still works, and caching invalidates correctly.

## Manual edits (quick fixes)

If you need to hotfix a single row before a full regeneration:

1. Open the CSV in a UTF-8 aware editor (Excel can re-save with a UTF-8 BOM — prefer a text editor when possible).
2. Add or edit the row, ensuring the slug-worthy fields (`name`, `faceName`, `side`) are unique.
3. Keep the `themeTags` value as a Python/JSON list (e.g., `['Artifacts']`), or a comma-delimited list without stray quotes.
4. Save the file and restart the server so the cache refreshes.
5. Backfill the curated themes in `config/themes/` if the new commander should surface dedicated tags.

> Manual edits are acceptable for emergency fixes but commit regenerated data as soon as possible so automation stays trustworthy.

## Troubleshooting

- **`Commander catalog is unavailable` error**: The app could not find the CSV. Verify the file exists under `CSV_FILES_DIR` and has a header row.
- **Row missing in the browser**: Ensure the commander passed eligibility (legendary rules) and the row’s `layout`/`side` data is correct. Slug collisions are auto-deduped (`-2`, `-3`, …) but rely on unique `name`+`side` combos.
- **Theme chips absent**: Confirm `themeTags` contains at least one value and that the theme slug exists in the theme catalog; otherwise the UI hides the chips.

For deeper issues, enable verbose logs with `SHOW_LOGS=1` before restarting the web process.
