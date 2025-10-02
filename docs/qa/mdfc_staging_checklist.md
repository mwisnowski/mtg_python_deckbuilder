# MDFC Staging QA Checklist

Use this checklist when validating the MDFC merge in staging. The merge now runs unconditionally; set `DFC_COMPAT_SNAPSHOT=1` when you also need the legacy unmerged snapshots for downstream validation.

_Last updated: 2025-10-02_

## Prerequisites
- Staging environment (Docker Compose or infrastructure equivalent) can override environment variables for the web service.
- Latest code synced with the MDFC merge helper (`code/scripts/refresh_commander_catalog.py`).
- Virtualenv or container image contains current project dependencies (`pip install -r requirements.txt`).

## Configuration Steps
1. Set the staging web service environment as needed:
   - `DFC_COMPAT_SNAPSHOT=1` when downstream teams still require the compatibility snapshot.
   - Optional diagnostics helpers: `SHOW_DIAGNOSTICS=1`, `SHOW_LOGS=1` (helps confirm telemetry output during smoke testing).
2. Inside the staging container (or server), regenerate commander data:
   ```powershell
   python -m code.scripts.refresh_commander_catalog
   ```
   - Verify the script reports both the merged output (`csv_files/commander_cards.csv`) and the compatibility snapshot (`csv_files/compat_faces/commander_cards_unmerged.csv`).
3. Restart the web service so the refreshed files (and optional compatibility snapshot setting) take effect.

## Smoke QA
| Area | Steps | Pass Criteria |
| --- | --- | --- |
| Commander Browser | Load `/commanders`, search for a known MDFC commander (e.g., "Elmar, Ulvenwald Informant"), flip faces, paginate results. | No duplicate rows per face, flip control works, pagination remains responsive. |
| Deck Builder | Run a New Deck build with a commander that adds MDFC lands (e.g., "Atraxa, Grand Unifier" with MDFC swap option). | Deck summary shows "Lands: X (Y with DFC)" copy, MDFC notes render, CLI summary matches web copy (check download/export). |
| Commander Exclusions | Attempt to search for a commander that should be excluded because only the back face is legal (e.g., "Withengar Unbound"). | UI surfaces exclusion guidance; the commander is not selectable. |
| Diagnostics | Open `/diagnostics` with `SHOW_DIAGNOSTICS=1`. Confirm MDFC telemetry panel shows merged counts. | `dfc_merge_summary` card present with non-zero merged totals; land telemetry includes MDFC contribution counts. |
| Logs | Tail application logs via `/logs` or container logs during a build. | No errors related to tag merging or commander loading. |

## Automated Checks
Run the targeted test suite to ensure MDFC regressions are caught:
```powershell
c:/Users/Matt/mtg_python/mtg_python_deckbuilder/.venv/Scripts/python.exe -m pytest -q ^
  code/tests/test_land_summary_totals.py ^
  code/tests/test_commander_primary_face_filter.py ^
  code/tests/test_commander_exclusion_warnings.py
```
- All tests should pass. Investigate any failures before promoting the flag.

## Downstream Sign-off
1. Provide consumers with:
   - Merged file: `csv_files/commander_cards.csv`
   - Compatibility snapshot: `csv_files/compat_faces/commander_cards_unmerged.csv`
2. Share expected merge metrics (`logs/dfc_merge_summary.json`) to help validate MDFC counts.
3. Collect acknowledgements that downstream pipelines work with the merged file (or have cut over) before retiring the compatibility flag.

## Rollback Plan
- Disable `DFC_COMPAT_SNAPSHOT` (or leave it unset) and rerun `python -m code.scripts.refresh_commander_catalog` if compatibility snapshots are no longer required.
- Revert to the previous committed commander CSV if needed (`git checkout -- csv_files/commander_cards.csv`).
- Document the issue in the roadmap and schedule the fix before reattempting the staging rollout.

## Latest Run (2025-10-02)
- Environment: staging compose updated (temporarily set `ENABLE_DFC_MERGE=compat`, now retired) and reconfigured with optional `DFC_COMPAT_SNAPSHOT=1` for compatibility checks.
- Scripts executed:
   - `python -m code.scripts.refresh_commander_catalog --compat-snapshot`
   - `python -m code.scripts.preview_dfc_catalog_diff --compat-snapshot --output logs/dfc_catalog_diff.json`
- Automated tests passed:
   - `code/tests/test_land_summary_totals.py`
   - `code/tests/test_commander_primary_face_filter.py`
   - `code/tests/test_commander_exclusion_warnings.py`
- Downstream sign-off: `logs/dfc_catalog_diff.json` shared with catalog consumers alongside `csv_files/compat_faces/commander_cards_unmerged.csv`; acknowledgements recorded in `docs/releases/dfc_merge_rollout.md`.
