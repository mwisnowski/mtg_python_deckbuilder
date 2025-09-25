# MTG Python Deckbuilder ${VERSION}

## Unreleased (Draft)

### Added
- Random Mode multi-theme groundwork: backend accepts `primary_theme`, `secondary_theme`, `tertiary_theme` and computes a resolved combination with ordered fallback (triple → P+S → P+T → P → synergy token overlap → full pool). Exposes diagnostics (`resolved_themes`, `combo_fallback`, `synergy_fallback`, `fallback_reason`) for upcoming UI integration.
- Locked commander reroll now outputs the full export artifact set (CSV, TXT, compliance, summary) with duplicate prevention.
- Taxonomy snapshot utility (`python -m code.scripts.snapshot_taxonomy`): captures an auditable JSON of BRACKET_DEFINITIONS under `logs/taxonomy_snapshots/` with a content hash. Safe to run any time; subsequent identical snapshots are skipped.
- Random Full Build export parity: random full builds now emit the full artifact set (`.csv`, `.txt`, `_compliance.json`, `.summary.json`) matching standard builds; API includes `csv_path`, `txt_path`, and `compliance` path fields.
- Opt-out env var `RANDOM_BUILD_SUPPRESS_INITIAL_EXPORT` (defaults to suppressed) allows re-enabling legacy double-export for debugging when set to `0`.
- Optional adaptive splash penalty (experiment): enable with `SPLASH_ADAPTIVE=1`; scale per commander color count with `SPLASH_ADAPTIVE_SCALE` (default `1:1.0,2:1.0,3:1.0,4:0.6,5:0.35`). Reasons are emitted as `splash_off_color_penalty_adaptive:<colors>:<value>`.
	- Analytics: splash penalty counters recognize both static and adaptive reasons; compare deltas with the flag toggled.
- Theme picker performance: precomputed summary projections + lowercase haystacks and memoized filtered slug cache (keyed by (etag, q, archetype, bucket, colors)) for sub‑50ms typical list queries on warm path.
- Skeleton loading UI for theme picker list, preview modal, and initial shell.
- Theme preview endpoint (`/themes/api/theme/{id}/preview` + HTML fragment) returning representative sample with roles (payoff/enabler/support/wildcard/example/curated_synergy/synthetic).
- Commander bias heuristics in preview sampling (color identity filtering + overlap/theme bonuses) for context-aware suggestions.
- In‑memory TTL (600s) preview cache with metrics (requests, cache hits, average build ms) exposed at diagnostics endpoint.
- Web UI: Double-faced card (DFC) hover support with single-image overlay flip control (top-left button, keyboard (Enter/Space/F), aria-live), persisted face (localStorage), and immediate refresh post-flip.
- Diagnostics flag `WEB_THEME_PICKER_DIAGNOSTICS=1` gating fallback description flag, editorial quality badges, uncapped synergy lists, raw YAML fetch, and metrics endpoint (`/themes/metrics`).
- Catalog & preview metrics endpoint combining filter + preview counters & cache stats.
- Performance headers on list & API responses: `X-ThemeCatalog-Filter-Duration-ms` and `ETag` for conditional requests.
 - Cache bust hooks tied to catalog refresh & tagging completion clear filter/preview caches (metrics now include last bust timestamps).
 - Governance metrics: `example_enforcement_active`, `example_enforce_threshold_pct` (threshold default 90%) signal when curated coverage enforcement is active.
 - Server authoritative mana & color identity fields (`mana_cost`, `color_identity_list`, `pip_colors`) included in preview/export; legacy client parsers removed.

### Changed
- Random reroll export logic deduplicated by persisting `last_csv_path` / `last_txt_path` from headless runs; avoids creation of `*_1` suffixed artifacts on reroll.
- Splash analytics updated to count both static and adaptive penalty reasons via a shared prefix, keeping historical dashboards intact.
- Random full builds internally auto-set `RANDOM_BUILD_SUPPRESS_INITIAL_EXPORT=1` (unless explicitly provided) to eliminate duplicate suffixed decklists.
- Preview assembly now pins curated `example_cards` then `synergy_example_cards` before heuristic sampling with diversity quotas (~40% payoff, 40% enabler/support, 20% wildcard) and synthetic placeholders only when underfilled.
- List & API filtering route migrated to optimized path avoiding repeated concatenation / casefolding work each request.
- Hover system consolidated to one global panel; removed fragment-specific duplicate & legacy large-image hover. Thumbnails enlarged & unified (110px → 165px → 230px). Hover activation limited to thumbnails; stability improved (no dismissal over flip control); DFC markup simplified to single <img> with opacity transition.

### Deprecated
- Price / legality snippet integration deferred to Budget Mode. Any interim badges will be tracked under `logs/roadmaps/roadmap_9_budget_mode.md`.
 - Legacy client-side mana/color identity parsers are considered deprecated; server-authoritative fields are now included in preview/export payloads.

### Fixed
- Resolved duplicate template environment instantiation causing inconsistent navigation globals in picker fragments.
- Ensured preview cache key includes catalog ETag preventing stale samples after catalog reload.
- Random build duplicate decklist exports removed; suppression of the initial builder auto-export prevents creation of `*_1.csv` / `*_1.txt` artifacts.

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