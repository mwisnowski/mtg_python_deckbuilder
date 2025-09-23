# Theme Taxonomy Rationale & Governance

This document captures decision criteria and rationale for expanding, merging, or refining the theme taxonomy.

## Goals
- Maintain meaningful, player-recognizable buckets.
- Avoid overspecialization (micro-themes) that dilute search & filtering.
- Preserve sampling diversity and editorial sustainability.

## Expansion Checklist
A proposed new theme SHOULD satisfy ALL of:
1. Distinct Strategic Identity: The game plan (win condition / resource axis) is not already adequately described by an existing theme or combination of two existing themes.
2. Representative Card Depth: At least 8 broadly played, format-relevant cards (EDHREC / common play knowledge) naturally cluster under this identity.
3. Commander Support: At least 3 reasonable commander candidates (not including fringe silver-bullets) benefit from or enable the theme.
4. Non-Subset Test: The candidate is not a strict subset of an existing theme's synergy list (check overlap ≥70% == probable subset).
5. Editorial Coverage Plan: Concrete initial examples & synergy tags identified; no reliance on placeholders at introduction.

If any criterion fails -> treat as a synergy tag inside an existing theme rather than a standalone theme.

## Candidate Themes & Notes
| Candidate | Rationale | Risks / Watchouts | Initial Verdict |
|-----------|-----------|-------------------|-----------------|
| Combo | High-synergy deterministic or infinite loops. Already partly surfaced via combo detection features. | Over-broad; could absorb unrelated value engines. | Defer; emphasize combo detection tooling instead. |
| Storm | Spell-chain count scaling (Grapeshot, Tendrils). Distinct engine requiring density/rituals. | Low breadth in casual metas; may overlap with Spellslinger. | Accept (pending 8-card list + commander examples). |
| Extra Turns | Time Walk recursion cluster. | Potential negative play perception; governance needed to avoid glorifying NPE lines. | Tentative accept (tag only until list curated). |
| Group Hug / Politics | Resource gifting & table manipulation. | Hard to score objectively; card set is broad. | Accept with curated examples to anchor definition. |
| Pillowfort | Defensive taxation / attack deterrence (Ghostly Prison line). | Overlap with Control / Enchantments. | Accept; ensure non-redundant with generic Enchantments. |
| Toolbox / Tutors | Broad search utility enabling silver-bullet packages. | Tutors already subject to bracket policy thresholds; broad risk. | Defer; retain as synergy tag only. |
| Treasure Matters | Explicit treasure scaling (Academy Manufactor, Prosper). | Rapidly evolving; needs periodic review. | Accept. |
| Monarch / Initiative | Alternate advantage engines via emblems/dungeons. | Initiative narrower post-rotation; watch meta shifts. | Accept (merge both into a single theme for now). |

## Merge / Normalization Guidelines
When overlap (Jaccard) between Theme A and Theme B > 0.55 across curated+enforced synergies OR example card intersection ≥60%, evaluate for merge. Preference order:
1. Retain broader, clearer name.
2. Preserve curated examples; move excess to synergy tags.
3. Add legacy name to `aliases` for backward compatibility.

## Example Count Enforcement
Threshold flips to hard enforcement after global coverage >90%:
- Missing required examples -> linter error (`lint_theme_editorial.py --require-examples`).
- Build fails CI unless waived with explicit override label.

## Splash Relax Policy Rationale
- Prevents 4–5 color commanders from feeling artificially constrained when one enabling piece lies just outside colors.
- Controlled by single-card allowance + -0.3 score penalty so off-color never outranks true color-aligned payoffs.

## Popularity Buckets Non-Scoring Principle
Popularity reflects observational frequency and is intentionally orthogonal to sampling to avoid feedback loops. Any future proposal to weight by popularity must include a diversity impact analysis and opt-in feature flag.

## Determinism & Reproducibility
All sampling randomness is derived from `seed = hash(theme|commander)`; taxonomy updates must document any score function changes in `CHANGELOG.md` and provide transition notes if output ordering shifts beyond acceptable tolerance.

## Governance Change Process
1. Open a PR modifying taxonomy YAML or this file.
2. Include: rationale, representative card list, commander list, overlap analysis with nearest themes.
3. Run catalog build + linter; attach metrics snapshot (`preview_metrics_snapshot.py`).
4. Reviewer checks duplication, size, overlap, enforcement thresholds.

## Future Considerations
- Automated overlap dashboard (heatmap) for candidate merges.
- Nightly diff bot summarizing coverage & generic description regression.
- Multi-dimensional rarity quota experimentation (moved to Deferred section for now).

---
Last updated: 2025-09-20
