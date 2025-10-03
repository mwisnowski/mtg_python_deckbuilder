# Web UI Deep Dive

A closer look at the rich interactions available in the MTG Python Deckbuilder Web UI. Use this guide after you are comfortable with the basic homepage flows described in the README.

## Table of contents
- [Unified New Deck modal](#unified-new-deck-modal)
- [Stage 5 tools: lock, replace, compare, permalinks](#stage-5-tools-lock-replace-compare-permalinks)
- [Multi-copy archetype packages](#multi-copy-archetype-packages)
- [Bracket compliance and skipped stages](#bracket-compliance-and-skipped-stages)
- [Build options: owned-only and prefer-owned](#build-options-owned-only-and-prefer-owned)
- [Visual summaries](#visual-summaries)
- [Combos & synergies](#combos--synergies)
- [Owned library page](#owned-library-page)
- [Finished decks workspace](#finished-decks-workspace)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Virtualization, tagging, and performance](#virtualization-tagging-and-performance)
- [Diagnostics and logs](#diagnostics-and-logs)

---

## Unified New Deck modal
The first three steps of deckbuilding live inside a single modal:

1. **Search for a commander** – autocomplete prioritizes color identity matches; press Enter to grab the top result.
2. **Pick primary/secondary/tertiary themes** – the modal displays your selections in order so you can revisit them quickly.
3. **Choose a bracket** – labels such as “Bracket 3: Upgraded” clarify power bands. Bracket 3 is the default tier for new builds.

Optional inputs:
- **Deck name** becomes the export filename stem and is reused in Finished Decks banners.
- **Combo auto-complete** and other preferences persist between runs.

Once you submit, the modal closes and the build starts immediately—no extra confirmation screen.

## Stage 5 tools: lock, replace, compare, permalinks
Stage 5 is the iterative workspace for tuning the deck:

- **Lock** a card by clicking the padlock or the card artwork. Locked cards persist across rerolls and show a “Last action” chip for quick confirmation.
- **Replace** opens the Alternatives drawer. Filters include Owned-only, role alignment, and bracket compliance. The system skips commanders, locked cards, just-added cards, and anything already in the list.
- **Permalink** buttons appear in Stage 5 and Finished Decks. Share a build (commander, themes, bracket, ideals, flags) or restore one by pasting a permalink back into the app.
- **Compare** mode lives in Finished Decks. Pick two builds (quick actions select the latest pair) and triage changes via Changed-only, Copy summary, or download the diff as TXT.

## Multi-copy archetype packages
When a commander + theme combination suggests a multi-copy strategy (e.g., Persistent Petitioners, Shadowborn Apostles), the UI offers an optional package:

- Choose the desired quantity (bounded by printed limits) and optionally add **Thrumming Stone** when it synergizes.
- Packages are inserted before other stages so target counts adjust appropriately.
- A safety clamp trims overflow to keep the deck at 100 cards; the stage displays a “Clamped N” indicator if it triggers.
- You can dismiss the modal, and we won’t re-prompt unless your selections change.

## Bracket compliance and skipped stages
- Bracket policy enforcement prunes disallowed categories before stage execution. Violations block reruns until you resolve them.
- Enforcement options: keep the panel collapsed when compliant, auto-open with a colored status chip (green/amber/red) when action is needed.
- Enable auto-enforcement by setting `WEB_AUTO_ENFORCE=1`.
- Toggle **Show skipped stages** to surface steps that added zero cards, making it easier to review the full pipeline.

## Build options: owned-only and prefer-owned
The modal includes toggles for **Use only owned cards** and **Prefer owned cards**:

- Owned-only builds pull strictly from the inventory in `owned_cards/` (commander exempt).
- Prefer-owned bumps owned cards slightly in the scoring pipeline but still allows unowned all-stars when necessary.
- Both modes respect the Owned Library filters and show Owned badges in the exported CSV (including the `Owned` column when you disable the mode).

## Visual summaries
Stage 5 displays multiple data visualizations that cross-link to the card list:

- **Mana curve** – hover a bar to highlight matching cards in list and thumbnail views.
- **Color requirements vs. sources** – pips show requirements; sources include non-land producers and an optional `C` (colorless) toggle.
- **Tooltips** – each tooltip lists contributing cards and offers a copy-to-clipboard action.
- Visual polish includes lazy-loaded thumbnails, blur-up transitions, and accessibility tweaks that respect `prefers-reduced-motion`.

## Combos & synergies
The builder detects curated two-card combos and synergy pairs in the final deck:

- Chips display badges such as “cheap” or “setup” with hover previews for each card and a split preview when hovering the entire row.
- Enable **Auto-complete combos** to add missing partners before theme filling. Configure target count, balance (early/late/mix), and preference weighting.
- Color identity restrictions keep the algorithm from suggesting off-color partners.

## Owned library page
Open the Owned tile to manage uploaded inventories:

- Upload `.txt` or `.csv` files with one card per line. The app enriches and deduplicates entries on ingestion.
- The page includes sortable columns, exact color-identity filters (including four-color combos), and an export button.
- Large collections benefit from virtualization when `WEB_VIRTUALIZE=1`.

## Finished decks workspace
- Browse historical builds with filterable theme chips.
- Each deck offers Download TXT, Copy summary, Open permalink, and Compare actions.
- Locks, replace history, and compliance metadata are stored per deck and surface alongside the exports.

## Keyboard shortcuts
- **Enter** selects the first commander suggestion while searching.
- Inside Stage 5 lists: **L** locks/unlocks the focused card, **R** opens the Replace drawer, and **C** copies the permalink.
- Browser autofill is disabled in the modal to keep searches clean.

## Virtualization, tagging, and performance
- `WEB_TAG_PARALLEL=1` with `WEB_TAG_WORKERS=4` (compose default) speeds up initial data preparation. The UI falls back to sequential tagging if workers fail to start.
- `WEB_VIRTUALIZE=1` enables virtualized grids in Stage 5 and the Owned library, smoothing large decks or libraries.
- Diagnostics overlays: enable `SHOW_DIAGNOSTICS=1`, then press **v** inside a virtualized grid to inspect render ranges, row counts, and paint timings.

## Diagnostics and logs
- `SHOW_DIAGNOSTICS=1` unlocks the `/diagnostics` page with system summaries (`/status/sys`), feature flags, and per-request `X-Request-ID` headers.
- Supplemental theme telemetry lives at `/status/theme_metrics` (enabled with `ENABLE_CUSTOM_THEMES=1`); the diagnostics page renders commander themes, user-supplied themes, merged totals, and unresolved counts using the `userThemes`/`themeCatalogVersion` metadata exported from builds.
- `SHOW_LOGS=1` turns on the `/logs` viewer with level & keyword filters, auto-refresh, and copy-to-clipboard.
- Health probes live at `/healthz` and return `{status, version, uptime_seconds}` for integration with uptime monitors.
