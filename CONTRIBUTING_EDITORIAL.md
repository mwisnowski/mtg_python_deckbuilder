# Editorial Contribution Guide (Themes & Descriptions)

## Files
- `config/themes/catalog/*.yml` – Per-theme curated metadata (description overrides, popularity_bucket overrides, examples).
- `config/themes/description_mapping.yml` – Ordered auto-description rules (first match wins). `{SYNERGIES}` optional placeholder.
- `config/themes/synergy_pairs.yml` – Fallback curated synergy lists for themes lacking curated_synergies in their YAML.
- `config/themes/theme_clusters.yml` – Higher-level grouping metadata for filtering and analytics.

## Description Mapping Rules
- Keep triggers lowercase; use distinctive substrings to avoid accidental matches.
- Put more specific patterns earlier (e.g., `artifact tokens` before `artifact`).
- Use `{SYNERGIES}` if the description benefits from reinforcing examples; leave out for self-contained archetypes (e.g., Storm).
- Tone: concise, active voice, present tense, single sentence preferred unless clarity needs a second clause.
- Avoid trailing spaces or double periods.

## Adding a New Theme
1. Create a YAML file in `config/themes/catalog/` (copy a similar one as template).
2. Add `curated_synergies` sparingly (3–5 strong signals). Enforced synergies handled by whitelist if needed.
3. Run: `python code/scripts/build_theme_catalog.py --backfill-yaml --force-backfill-yaml`.
4. Run validator: `python code/scripts/validate_description_mapping.py`.
5. Run tests relevant to catalog: `pytest -q code/tests/test_theme_catalog_generation.py`.

## Reducing Generic Fallbacks
- Use fallback summary: set `EDITORIAL_INCLUDE_FALLBACK_SUMMARY=1` when building catalog. Inspect `generic_total` and top ranked themes.
- Prioritize high-frequency themes first (largest leverage). Add mapping entries or curated descriptions.
- After lowering count, tighten regression thresholds in `test_theme_description_fallback_regression.py` (lower allowed generic_total / generic_pct).

## Synergy Pairs
- Only include if a theme’s YAML doesn’t already define curated synergies.
- Keep each list ≤8 (soft) / 12 (hard validator warning).
- Avoid circular weaker links—symmetry is optional and not required.

## Clusters
- Use for UI filtering and analytics; not used in inference.
- Keep cluster theme names aligned with catalog `display_name` strings; validator will warn if absent.

## Metadata Info & Audit
- Backfill process stamps each YAML with a `metadata_info` block (formerly documented as `provenance`) containing timestamp + script version and related generation context. Do not hand‑edit this block; it is regenerated.
- Legacy key `provenance` is still accepted temporarily for backward compatibility. If both keys are present a one-time warning is emitted. The alias is scheduled for removal in version 2.4.0 (set `SUPPRESS_PROVENANCE_DEPRECATION=1` to silence the warning in transitional automation).

## Editorial Quality Status (draft | reviewed | final)
Each theme can declare an `editorial_quality` flag indicating its curation maturity. Promotion criteria:

| Status    | Minimum Example Commanders | Description Quality                          | Popularity Bucket | Other Requirements |
|-----------|----------------------------|----------------------------------------------|-------------------|--------------------|
| draft     | 0+ (may be empty)          | Auto-generated allowed                       | auto/empty ok     | None               |
| reviewed  | >=5                        | Non-generic (NOT starting with "Builds around") OR curated override | present (auto ok) | No lint structural errors |
| final     | >=6 (at least 1 curated, non-synergy annotated) | Curated override present, 8–60 words, no generic stem | present           | metadata_info block present; no lint warnings in description/examples |

Promotion workflow:
1. Move draft → reviewed once you add enough example_commanders (≥5) and either supply a curated description or mapping generates a non-generic one.
2. Move reviewed → final only after adding at least one manually curated example commander (unannotated) and replacing the auto/mapped description with a handcrafted one meeting style/tone.
3. If a final theme regresses (loses examples or gets generic description) lint will flag inconsistency—fix or downgrade status.

Lint Alignment (planned):
- draft with ≥5 examples & non-generic description will emit an advisory to upgrade to reviewed.
- reviewed with generic description will emit a warning.
- final failing any table requirement will be treated as an error in strict mode.

Tips:
- Keep curated descriptions single-paragraph; avoid long enumerations—lean on synergies list for breadth.
- If you annotate synergy promotions (" - Synergy (Foo)"), still ensure at least one base (unannotated) commander remains in examples for final status.

Automation Roadmap:
- CI will later enforce no `final` themes use generic stems and all have `metadata_info`.
- Ratchet script proposals may suggest lowering generic fallback ceilings; prioritize upgrading high-frequency draft themes first.

## Common Pitfalls
- Duplicate triggers: validator warns; remove the later duplicate or merge logic.
- Overly broad trigger (e.g., `art` catching many unrelated words) – prefer full tokens like `artifact`.
- Forgetting to update tests after tightening fallback thresholds – adjust numbers in regression test.

## Style Reference Snippets
- Archetype pattern: `Stacks auras, equipment, and protection on a single threat ...`
- Resource pattern: `Produces Treasure tokens as flexible ramp & combo fuel ...`
- Counter pattern: `Multiplies diverse counters (e.g., +1/+1, loyalty, poison) ...`

## Review Checklist
- [ ] New theme YAML added
- [ ] Description present or mapping covers it specifically
- [ ] Curated synergies limited & high-signal
- [ ] Validator passes (no errors; warnings reviewed)
- [ ] Fallback summary generic counts unchanged or improved
- [ ] Regression thresholds updated if improved enough
- [ ] Appropriate `editorial_quality` set (upgrade if criteria met)
- [ ] Final themes meet stricter table requirements

Happy editing—keep descriptions sharp and high-value.

## Minimum Example Commanders Enforcement (Phase D Close-Out)
As of Phase D close-out, every non-alias theme must have at least 5 `example_commanders`.

Policy:
* Threshold: 5 (override locally with `EDITORIAL_MIN_EXAMPLES`, but CI pins to 5).
* Enforcement: CI exports `EDITORIAL_MIN_EXAMPLES_ENFORCE=1` and runs the lint script with `--enforce-min-examples`.
* Failure Mode: Lint exits non-zero listing each theme below threshold.
* Remediation: Curate additional examples or run the suggestion script (`generate_theme_editorial_suggestions.py`) with a deterministic seed (`EDITORIAL_SEED`) then manually refine.

Local soft check (warnings only):
```
python code/scripts/lint_theme_editorial.py --min-examples 5
```

Local enforced check (mirrors CI):
```
EDITORIAL_MIN_EXAMPLES_ENFORCE=1 python code/scripts/lint_theme_editorial.py --enforce-min-examples --min-examples 5
```

## Alias YAML Lifecycle
Deprecated alias theme YAMLs receive a single release grace period before deletion.

Phases:
1. Introduced: Placeholder file includes a `notes` line marking deprecation and points to canonical theme.
2. Grace Period (one release): Normalization keeps resolving legacy slug; strict alias validator may be soft.
3. Removal: Alias YAML deleted; strict alias validation becomes hard fail if stale references remain.

When removing an alias:
* Delete alias YAML from `config/themes/catalog/`.
* Search & update tests referencing old slug.
* Rebuild catalog: `python code/scripts/build_theme_catalog.py` (with seed if needed).
* Run governance workflow locally (lint + tests).

If extended grace needed (downstream impacts), document justification in PR.

