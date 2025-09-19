# MTG Python Deckbuilder ${VERSION}

## Unreleased (Draft)

### Added
- Editorial duplication suppression for example cards: `--common-card-threshold` (default 0.18) and `--print-dup-metrics` flags in `synergy_promote_fill.py` to reduce over-represented staples and surface diverse thematic examples.
- Optional `description_fallback_summary` block (enabled via `EDITORIAL_INCLUDE_FALLBACK_SUMMARY=1`) capturing specialization KPIs: generic vs specialized description counts and top generic holdouts.

### Changed
- Terminology migration: `provenance` renamed to `metadata_info` across catalog JSON, per-theme YAML, models, and tests. Builder writes `metadata_info`; legacy `provenance` key still accepted temporarily.

### Deprecated
- Legacy `provenance` key retained as read-only alias; warning emitted if both keys present (suppress via `SUPPRESS_PROVENANCE_DEPRECATION=1`). Planned removal: v2.4.0.

### Fixed
- Schema evolution adjustments to accept per-theme `metadata_info` and optional fallback summary without triggering validation failures.

---

### Added
- Theme whitelist governance (`config/themes/theme_whitelist.yml`) with normalization, enforced synergies, and synergy cap (5).
- Expanded curated synergy matrix plus PMI-based inferred synergies (data-driven) blended with curated anchors.
- Test: `test_theme_whitelist_and_synergy_cap.py` validates enforced synergy presence and cap compliance.
- PyYAML dependency for governance parsing.

### Changed
- Theme normalization (ETB -> Enter the Battlefield, Self Mill -> Mill, Pillow Fort -> Pillowfort, Reanimator -> Reanimate) applied prior to synergy derivation.
- Synergy output capped to 5 entries per theme (curated > enforced > inferred ordering).

### Fixed
- Removed ultra-rare themes (frequency <=1) except those protected/always included via whitelist.
- Corrected commander eligibility: restricts non-creature legendary permanents. Now only Legendary Creatures (incl. Artifact/Enchantment Creatures), qualifying Legendary Artifact Vehicles/Spacecraft with printed P/T, or any card explicitly stating "can be your commander" are considered. Plain Legendary Enchantments (non-creature), Planeswalkers without the text, and other Legendary Artifacts are excluded.

---