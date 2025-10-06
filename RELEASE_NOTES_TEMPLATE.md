# MTG Python Deckbuilder ${VERSION}

## Summary
- Partner suggestion service and UI chips recommend secondary commanders (partner/background/Doctor) when `ENABLE_PARTNER_SUGGESTIONS` is enabled.
- Headless runner now honors partner/background inputs behind the `ENABLE_PARTNER_MECHANICS` feature flag and exposes the resolved configuration in dry-run output.
- Web builder Step 2 displays partner/background pairing controls (toggle, selectors, preview, warnings) when the feature flag is active.
- Quick-start modal now embeds the shared partner/background controls so the rapid flow can choose secondary commanders or backgrounds without leaving the overlay.
- Partner mechanics UI auto-enables for eligible commanders, renames the selector to “Partner commander,” layers in Partner With defaults with an opt-out chip, and adds Doctor/Doctor’s Companion pairing coverage while keeping theme tags consistent across modal and Step 2.
- Background catalog parsing is now centralized in `load_background_cards()` with typed entries, memoized caching, and a generator utility so background-only card lists stay fresh.
- Commander setup now regenerates `background_cards.csv` whenever commander catalogs refresh, keeping background pickers aligned after setup or data updates.

## Added
- Partner suggestion dataset loader, FastAPI endpoint, UI wiring, dataset override env (`PARTNER_SUGGESTIONS_DATASET`), automatic regeneration when the dataset is missing, and regression coverage for ranked results when suggestions are enabled.
- CLI regression coverage (`code/tests/test_cli_partner_config.py`) validating partner/background dry-run payloads and environment flag precedence.
- Partner mechanics UI in the web builder (Step 2) with live preview, warnings, and automatic Partner With hints behind `ENABLE_PARTNER_MECHANICS`.
- Quick-start modal renders the `_partner_controls.html` partial, surfacing partner/background selections during commander inspection.
- Commander metadata now flags Doctors and Doctor’s Companions, enabling legal doctor/companion pairings in partner selectors with role-aware labels.
- New background catalog loader and `python -m code.scripts.generate_background_cards` utility, plus regression coverage ensuring only legal backgrounds populate the catalog.
- Shared `build_combined_commander()` aggregation and partner selection helper reused by headless, web, and orchestration flows with expanded unit coverage.

## Changed
- Partner controls now fetch suggestion chips in Step 2 and the quick-start modal (respecting partner mode and locks) when `ENABLE_PARTNER_SUGGESTIONS=1`.
- Partner suggestion scoring filters out broad "Legends Matter", "Historics Matter", and Kindred themes during overlap/synergy calculations so suggested pairings highlight distinctive commander synergies.
- Headless runner parsing resolves `--secondary-commander` and `--background` inputs (mutually exclusive), applies the partner selection helper before deck assembly, and surfaces partner metadata when the feature flag is enabled.
- Step 2 submission now validates partner selections, stores combined commander previews in session state, and clears partner context when the toggle is disabled.
- `/build/new` submission mirrors the partner validation/resolution flow, persisting combined commander payloads and returning inline partner errors when inputs conflict.
- Partner controls no longer rely on a manual checkbox; they render automatically for eligible commanders, rename the secondary selector to “Partner commander,” and expose a Partner With default chip that can be toggled off.
- Deck assembly, exports, and preview endpoints now consume the shared combined-commander payload so color identity, theme tags, and warnings stay aligned across flows.
- Partner detection differentiates between standalone “Partner” cards and restricted mechanics (Partner With, Doctor’s Companion, hyphenated variants), keeping plain-partner pools clean while retaining direct Partner With pairings.
- Structured partner selection logs now emit `partner_mode_selected` and include before/after color identity snapshots to support diagnostics and telemetry dashboards.
- Commander setup now regenerates the background catalog in the same pass as commander CSVs, so downstream pickers stay synchronized without manual scripts.

## Fixed
- Regenerated `background_cards.csv` and refined detection so only true Background enchantments appear in the dropdown, preventing "Choose a Background" commanders from showing up as illegal selections.
- Quick-start modal now mirrors Step 2’s merged theme tags so chips stay consistent after commander inspection.
- Step 5 summary and quick-start commander preview now surface merged partner color identity and theme tags so partnered commanders show the full color pair.
- Background picker falls back to the commander catalog when `background_cards.csv` is missing so “Choose a Background” commanders keep their pairing options in the web UI.
- Partner suggestions refresh actions now retry dataset generation and load the builder script with the correct project path, allowing missing `partner_synergy.json` files to be rebuilt without restarting the web service.
