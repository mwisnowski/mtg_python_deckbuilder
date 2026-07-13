# MTG Python Deckbuilder

## [Unreleased]
### Added
- **Deck Import & Analysis — Post-M6 improvements** (Roadmap 24 continued):
  - Per-card duplicate resolution: each duplicate card gets its own lazy-loaded replacement pool (tiered by type + functional role), radio-select with HTMX swap
  - Fill suggestions for under-100 decks: 3 independent sections (role shortfalls, theme fit, general synergy), each scored by composite fitness — theme match (+3 pts), shortfall role (+2.5 pts), other staple role (+1 pt), EDHRec popularity; cards sorted by score descending within each section; teal role pills highlight cards that address a deck shortfall, muted pills show other covered roles
  - Theme autocomplete on the import form: segment-aware, keyboard-navigable dropdown fetching `/cards/theme-autocomplete`
  - Random placeholder examples in the theme input: 3 themes sampled from the catalog on each page load, at most one Kindred/Tribal
  - Kindred auto-detection in `detect_themes`: counts creature subtypes across non-land cards; if any subtype hits ≥15 cards, injects the matching catalog `X Kindred`/`X Tribal` theme as a high-priority candidate
  - Post-analysis theme correction: **Edit themes** toggle on the Themes panel pre-fills current themes, supports autocomplete, re-runs detection via `POST /decks/import/update-themes`
  - Creature subtype breakdown in the Cards by Type panel: subtypes with ≥5 creatures shown as inline pill list under the Creature row
  - Unified theme list: all themes (user + auto) shown as collapsible `<details>` rows with **Manual** / **Commander** badges, card count, and top-10 cards by EDHRec rank
  - `ThemeCardBreakdown` dataclass: `card_count`, `in_commander`, `is_user_theme`, `top_cards` — computed per theme in `detect_themes` and serialized to temp session
- **Tagging fix — counter type tag names**: `COUNTER_TYPES` in `tag_constants.py` changed from regex raw strings (`r'\+0/\+1'`) to plain strings (`'+0/+1'`); `re.escape()` now applied at search time in `tagger.py` so pattern matching is correct but tag names are human-readable
- **Theme catalog & parquet cleanup**: backslash-escaped counter tags (`\+0/\+1 Counters` etc.) removed from both `config/themes/theme_catalog.csv` (3 lines) and `card_files/processed/all_cards.parquet` (25 rows); both loaders (`theme_catalog_loader.py`, `card_browser.py`) now strip leading `\` as a safety net

### Fixed
- **Theme catalog escape characters**: `\+1/\+0 Counters`, `\+0/\+1 Counters`, `\+2/\+2 Counters` displayed with literal backslashes in autocomplete and theme panels; root cause was regex raw strings used as tag names in `COUNTER_TYPES`

### Removed
_No unreleased changes yet_

