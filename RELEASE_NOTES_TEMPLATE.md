# MTG Python Deckbuilder ${VERSION}

## Unreleased (Draft)

### Added
	- Tests: added `test_random_reroll_throttle.py` to guard reroll throttle behavior and `test_random_metrics_and_seed_history.py` to verify opt-in telemetry counters and seed history API output.
	- Analytics: splash penalty counters recognize both static and adaptive reasons; compare deltas with the flag toggled.
- Random Mode curated pool now loads manual exclusions (`config/random_theme_exclusions.yml`), includes reporting helpers (`code/scripts/report_random_theme_pool.py --write-exclusions`), and ships documentation (`docs/random_theme_exclusions.md`). Diagnostics cards show manual categories and tag index telemetry.
- Added `code/scripts/check_random_theme_perf.py` guard that compares the multi-theme profiler (`code/scripts/profile_multi_theme_filter.py`) against `config/random_theme_perf_baseline.json` with optional `--update-baseline`.
- Random Mode UI adds a “Clear themes” control that resets Primary/Secondary/Tertiary inputs plus local persistence in a single click.
	- Diagnostics: Added `/status/random_theme_stats` and a diagnostics dashboard card surfacing commander/theme token coverage and top tokens for multi-theme debugging.
 - Cache bust hooks tied to catalog refresh & tagging completion clear filter/preview caches (metrics now include last bust timestamps).
 - Governance metrics: `example_enforcement_active`, `example_enforce_threshold_pct` (threshold default 90%) signal when curated coverage enforcement is active.
 - Server authoritative mana & color identity fields (`mana_cost`, `color_identity_list`, `pip_colors`) included in preview/export; legacy client parsers removed.

### Changed
### Added
- Tests: added `test_random_multi_theme_webflows.py` validating reroll-same-commander caching and permalink roundtrips for multi-theme runs across HTMX and API layers.
- Multi-theme filtering now reuses a cached lowercase tag column and builds a reusable token index so combination checks and synergy fallback avoid repeated pandas `.apply` passes; new script `code/scripts/profile_multi_theme_filter.py` reports mean ~9.3 ms / p95 ~21 ms cascade timings on the current catalog (seed 42, 300 iterations).
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
- Random UI polish: fallback notices gain accessible icons, focus outlines, and aria copy; diagnostics badges now include icons/labels; the theme help tooltip is an accessible popover with keyboard controls; secondary/tertiary theme inputs persist via localStorage so repeat builds start with previous choices.
- Test: `test_theme_whitelist_and_synergy_cap.py` validates enforced synergy presence and cap compliance.
- PyYAML dependency for governance parsing.

### Changed
- Theme normalization (ETB -> Enter the Battlefield, Self Mill -> Mill, Pillow Fort -> Pillowfort, Reanimator -> Reanimate) applied prior to synergy derivation.
- Synergy output capped to 5 entries per theme (curated > enforced > inferred ordering).

### Fixed
- Removed ultra-rare themes (frequency <=1) except those protected/always included via whitelist.
- Corrected commander eligibility: restricts non-creature legendary permanents. Now only Legendary Creatures (incl. Artifact/Enchantment Creatures), qualifying Legendary Artifact Vehicles/Spacecraft with printed P/T, or any card explicitly stating "can be your commander" are considered. Plain Legendary Enchantments (non-creature), Planeswalkers without the text, and other Legendary Artifacts are excluded.

---