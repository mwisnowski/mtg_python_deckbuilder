# MTG Python Deckbuilder ${VERSION}

## Summary
- Completed the Multi-Faced Card Handling roadmap: multi-face records share merged tags, commander eligibility now checks only primary faces, and land diagnostics stay consistent across web, CLI, and exports.
- Deck summary highlights modal double-faced lands with inline badges, and exports append MDFC annotations so offline reviews match the web experience.
- Deck summary now surfaces MDFC land contributions with "Lands: X (Y with DFC)" copy and an expandable breakdown for modal double-faced cards.
- CLI deck output mirrors the web summary so diagnostics stay in sync across interfaces.
- Web builder commander search now flags secondary-face-only commanders, auto-corrects to the legal face, and shows inline guidance sourced from `.commander_exclusions.json`.
- Diagnostics dashboard now surfaces the multi-face merge snapshot and MDFC telemetry, combining the persisted `logs/dfc_merge_summary.json` artifact with live deck summary counters.
- New Deck modal now mirrors Step 4 preferences with inline toggles for owned-only, prefer-owned, and MDFC basic swap so players can lock in their plan before starting a build.
- Restored setup filtering to exclude Acorn and Heart promotional security stamps so Commander card pools stay format-legal.
- Added a dedicated commander catalog refresh helper (`python -m code.scripts.refresh_commander_catalog`) that outputs both merged MDFC-aware data and an unmerged compatibility snapshot, with updated documentation guiding downstream migrations.
- Documented the staging rollout completion: Docker/README guidance now notes the MDFC merge is always on and explains how to emit optional compatibility snapshots (`DFC_COMPAT_SNAPSHOT=1`) for downstream QA.

## Added
- Regression test coverage for MDFC export annotations and documentation outlining how to add new double-faced cards to the CSV authoring workflow.
- Optional MDFC per-face diagnostics snapshot controlled through `DFC_PER_FACE_SNAPSHOT` (with `DFC_PER_FACE_SNAPSHOT_PATH` override) for catalog QA.
- Structured DFC merge logging captured in `logs/dfc_merge_summary.json` for observability.
- Land accounting regression coverage via `test_land_summary_totals.py`, including an HTMX smoke test for the deck summary partial.
- Roadmap updates capturing remaining DFC observability, rollout, and export follow-ups with next-step notes.
- Regression test `test_commander_exclusion_warnings.py` ensuring builder guidance for secondary-face commanders stays in place.
- Regression test covering security-stamp filtering during setup to guard against future case-sensitivity regressions.
- Diagnostics panel for multi-face merges, backed by the new `summary_telemetry.py` land summary hook, plus telemetry snapshot endpoint for MDFC land contributions.
- Commander wizard checkbox to swap matching basics whenever modal double-faced lands are added, with dedicated regression coverage.
- New Deck modal exposes owned-only, prefer-owned, and MDFC swap toggles with session-backed defaults so preferences stick across runs.
- Commander catalog automation script (`python -m code.scripts.refresh_commander_catalog`) regenerates commander data, always applies the MDFC merge, and can optionally write compat-face snapshots; README and commander docs now include post-guard migration guidance.
- Docker and README documentation now outline the always-on MDFC merge and the optional `DFC_COMPAT_SNAPSHOT=1` workflow plus compatibility snapshot checkpoints for downstream consumers.
- QA documentation: added `docs/qa/mdfc_staging_checklist.md` outlining the staging validation pass required before removing the MDFC compatibility guard.

## Fixed
- Setup filtering now applies security-stamp exclusions case-insensitively, preventing Acorn/Heart promo cards from entering Commander pools.
- Commander browser thumbnails restore the double-faced flip control so MDFC commanders expose both faces directly in the catalog.