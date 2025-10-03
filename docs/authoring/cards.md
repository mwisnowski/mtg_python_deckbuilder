# Card Authoring Guide

This guide captures the conventions used by the deckbuilder when new cards are added to the CSV inputs. Always validate your edits by running the fast tagging tests or a local build before committing changes.

## Modal double-faced & transform cards

The tagging and reporting pipeline expects one row per face for any multi-faced card (modal double-faced, transform, split, or adventure). Use the checklist below when adding or updating these entries:

1. **Canonical name** — Keep the `name` column identical for every face (e.g., `Valakut Awakening // Valakut Stoneforge`). Individual faces should instead set `face_name` when available; the merger preserves front-face copy for downstream consumers.
2. **Layout & side** — Populate `layout` with the value emitted by Scryfall (`modal_dfc`, `transform`, `split`, `adventure`, etc.) and include a `side` column (`a`, `b`, …). The merger uses `side` ordering when reconstructing per-face metadata.
3. **Mana details** — Supply `mana_cost`, `mana_value`, and `produces_mana` for every face. The per-face land snapshot and deck summary badges rely on these fields to surface the “DFC land” chip and annotated mana production.
4. **Type line accuracy** — Ensure `type_line` includes `Land` for any land faces. The builder counts a card toward land totals when at least one face includes `Land`.
5. **Tags & roles** — Tag every face with the appropriate `themeTags`, `roleTags`, and `card_tags`. The merge stage unions these sets so the finished card retains all relevant metadata.
6. **Commander eligibility** — Only the primary (`side == 'a'`) face is considered for commander legality. If you add a new MDFC commander, double-check that the front face satisfies the Commander rules text; otherwise the record is filtered during catalog refresh.
7. **Cross-check exports** — After the card is added, run a local build and confirm the deck exports include the new `DFCNote` column entry for the card. The annotation summarizes each land face so offline reviewers see the same guidance as the web UI.

### Diagnostics snapshot (optional)

When validating a large batch of MDFCs, enable the snapshot helper to inspect the merged faces:

- Set `DFC_PER_FACE_SNAPSHOT=1` (and optionally `DFC_PER_FACE_SNAPSHOT_PATH`) before running the tagging pipeline.
- Disable parallel tagging (`WEB_TAG_PARALLEL=0`) while the snapshot is active; the helper only writes output during sequential runs.
- Once tagging completes, review `logs/dfc_per_face_snapshot.json` for the card you added to verify mana fields, `produces_mana`, and land detection flags.

Following these guidelines keeps the deck summary badges, exporter annotations, and diagnostics snapshots in sync for every new double-faced card.
