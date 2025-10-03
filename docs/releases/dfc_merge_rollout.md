# MDFC Merge Rollout (2025-10-02)

## Summary
- Staging environment refreshed with the MDFC merge permanently enabled; compatibility snapshot retained via `DFC_COMPAT_SNAPSHOT=1` during validation.
- Commander catalog rebuilt with `python -m code.scripts.refresh_commander_catalog --compat-snapshot`, generating both the merged output and `csv_files/compat_faces/commander_cards_unmerged.csv` for downstream comparison.
- Diff artifact `logs/dfc_catalog_diff.json` captured via `python -m code.scripts.preview_dfc_catalog_diff --compat-snapshot --output logs/dfc_catalog_diff.json` and shared with downstream consumers.
- `ENABLE_DFC_MERGE` guard removed across the codebase; documentation updated to reflect the always-on merge and optional compatibility snapshot workflow.

## QA Artifacts
| Artifact | Description |
| --- | --- |
| `docs/qa/mdfc_staging_checklist.md` | Latest run log documents the staging enablement procedure and verification steps. |
| `logs/dfc_catalog_diff.json` | JSON diff summarising merged vs. unmerged commander/catalog rows for parity review. |
| `csv_files/commander_cards.csv` | Merged commander catalog generated after guard removal. |
| `csv_files/compat_faces/commander_cards_unmerged.csv` | Legacy snapshot retained for downstream validation during the final review window. |

## Automated Verification
| Check | Command | Result |
| --- | --- | --- |
| MDFC land accounting | `python -m pytest -q code/tests/test_land_summary_totals.py` | ✅ Passed |
| Commander primary-face filter | `python -m pytest -q code/tests/test_commander_primary_face_filter.py` | ✅ Passed |
| Commander exclusion warnings | `python -m pytest -q code/tests/test_commander_exclusion_warnings.py` | ✅ Passed |

## Downstream Sign-off
| Consumer / Surface | Validation | Status |
| --- | --- | --- |
| Web UI (builder + diagnostics) | MDFC staging checklist smoke QA | ✅ Complete |
| CLI / Headless workflows | Targeted pytest suite confirmations (see above) | ✅ Complete |
| Data exports & analytics | `logs/dfc_catalog_diff.json` review against `commander_cards_unmerged.csv` | ✅ Complete |

All downstream teams confirmed parity with the merged catalog and agreed to proceed without the `ENABLE_DFC_MERGE` guard. Compatibility snapshots remain available via `DFC_COMPAT_SNAPSHOT=1` for any follow-up spot checks.
