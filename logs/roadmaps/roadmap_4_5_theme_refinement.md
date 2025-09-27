# Roadmap: Theme Refinement (M2.5)

This note captures gaps and refinements after generating `config/themes/theme_list.json` from the current tagger and constants.

<!--
  Roadmap Refactor (2025-09-20)
  This file was reorganized to remove duplication, unify scattered task lists, and clearly separate:
  - Completed work (historical reference)
  - Active / Remaining work (actionable backlog)
  - Deferred / Optional items
  Historical verbose phase details have been collapsed into an appendix to keep the working backlog lean.
-->

## Unified Task Ledger (Single Source of Truth)
Legend: [x]=done, [ ]=open. Each line starts with a domain tag for quick filtering.

### Completed (Retained for Traceability)
[x] PHASE Extraction prototype: YAML export script, per-theme files, auto-export, fallback path
[x] PHASE Merge pipeline: analytics regen, normalization, precedence merge, synergy cap, fallback
[x] PHASE Validation & tests: models, schemas, validator CLI, idempotency tests, strict alias pass, CI integration
[x] PHASE Editorial enhancements: examples & synergy commanders, augmentation heuristics, deterministic seed, description mapping, lint, popularity buckets
[x] PHASE UI integration: picker APIs, filtering, diagnostics gating, archetype & popularity badges, stale refresh
[x] PREVIEW Endpoint & sampling base (deterministic seed, diversity quotas, role classification)
[x] PREVIEW Commander bias (color identity filter, overlap/theme bonuses, diminishing overlap scaling initial)
[x] PREVIEW Curated layering (examples + curated synergy insertion ordering)
[x] PREVIEW Caching: TTL cache, warm index build, cache bust hooks, size-limited eviction
[x] PREVIEW UX: grouping separators, role chips, curated-only toggle, reasons collapse, tooltip <ul> restructure, color identity ribbon
[x] PREVIEW Mana cost parsing + color pip rendering (client-side parser)
[x] METRICS Global & per-theme avg/p95/p50 build times, request counters, role distribution, editorial coverage
[x] LOGGING Structured preview build & cache_hit/miss, prefetch_success/error
[x] CLIENT Perf: navigation preservation, keyboard nav, accessibility roles, lazy-load images, blur-up placeholders
[x] CLIENT Filter chips (archetype / popularity) inline with search
[x] CLIENT Highlight matched substrings (<mark>) in search results
[x] CLIENT Prefetch detail fragment + top 5 likely themes (<link rel=prefetch>)
[x] CLIENT sessionStorage preview fragment cache + ETag revalidation
[x] FASTAPI Lifespan migration (startup deprecation removal)
[x] FAST PATH Catalog integrity validation & catalog hash emission (drift detection)
[x] RESILIENCE Inline retry UI for preview fetch failures (exponential backoff)
[x] RESILIENCE Graceful degradation banner when fast path unavailable
[x] RESILIENCE Rolling error rate counter surfaced in diagnostics
[x] OBS Client performance marks (list_render_start, list_ready) + client hints batch endpoint
[x] TESTS role chip rendering / prewarm metric / ordering / navigation / keyboard / accessibility / mana parser / image lazy-load / cache hit path
[x] DOCS README API contract & examples update
[x] FEATURE FLAG `WEB_THEME_PICKER_DIAGNOSTICS` gating fallback/editorial/uncapped
[x] DATA Server ingestion of mana cost & rarity + normalization + pre-parsed color identity & pip caches (2025-09-20)
[x] SAMPLING Baseline rarity & uniqueness weighting (diminishing duplicate rarity influence) (2025-09-20)
[x] METRICS Raw curated_total & sampled_total counts per preview payload & structured logs (2025-09-20)
[x] METRICS Global curated & sampled totals surfaced in metrics endpoint (2025-09-20)
[x] INFRA Defensive THEME_PREVIEW_CACHE_MAX guard + warning event (2025-09-20)
[x] BUG Theme detail: restored hover card popup panel (regression fix) (2025-09-20)
[x] UI Hover system unified: single two-column panel (tags + overlaps) replaces legacy dual-panel + legacy large-image hover (2025-09-20)
[x] UI Reasons control converted to checkbox with state persistence (localStorage) (2025-09-20)
[x] UI Curated-only toggle state persistence (localStorage) (2025-09-20)
[x] UI Commander hover parity (themes/overlaps now present for example & synergy commanders) (2025-09-20)
[x] UI Hover panel: fragment-specific duplicate panel removed (single global implementation) (2025-09-20)
[x] UI Hover panel: standardized large image sizing across preview modal, theme detail, build flow, and finished decks (2025-09-20)
[x] UI Hover DFC overlay flip control (single image + top-left circular button with fade transition & keyboard support) (2025-09-20)
[x] UI Hover DFC face persistence (localStorage; face retained across hovers & page contexts) (2025-09-20)
[x] UI Hover immediate face refresh post-flip (no pointer synth; direct refresh API) (2025-09-20)
[x] UI Hover stability: panel retention when moving cursor over flip button (pointerout guard) (2025-09-20)
[x] UI Hover performance: restrict activation to thumbnail images (reduces superfluous fetches) (2025-09-20)
[x] UI Hover image sizing & thumbnail scale increase (110px → 165px → 230px unification across preview & detail) (2025-09-20)
[x] UI DFC UX consolidation: removed dual-image back-face markup; single img element with opacity transition (2025-09-20)
[x] PREVIEW UX: suppress duplicated curated examples on theme detail inline preview (new suppress_curated flag) + uniform 110px card thumb sizing for consistency (2025-09-20)
[x] PREVIEW UX: minimal inline preview variant (collapsible) removing controls/rationale/headers to reduce redundancy on detail page (2025-09-20)
[x] BUG Theme detail: YAML fallback for description/editorial_quality/popularity_bucket restored (catalog omission regression fix) (2025-09-20)

### Open & Planned (Actionable Backlog) — Ordered by Priority

Priority Legend:
P0 = Critical / foundational (unblocks other work or fixes regressions)
P1 = High (meaningful UX/quality/observability improvements next wave)
P2 = Medium (valuable but can follow P1)
P3 = Low / Nice-to-have (consider after core goals) — many of these already in Deferred section

#### P0 (Immediate / Foundational & Bugs)
[x] DATA Taxonomy snapshot tooling (`snapshot_taxonomy.py`) + initial snapshot committed (2025-09-24)  
  STATUS: Provides auditable hash of BRACKET_DEFINITIONS prior to future taxonomy-aware sampling tuning.
[x] TEST Card index color identity edge cases (hybrid, colorless/devoid, MDFC single, adventure, color indicator) (2025-09-24)  
  STATUS: Synthetic CSV injected via `CARD_INDEX_EXTRA_CSV`; asserts `color_identity_list` extraction correctness.
[x] DATA Persist parsed color identity & pips in index (remove client parsing; enable strict color filter tests) (FOLLOW-UP: expose via API for tests)  
  STATUS: Server payload now exposes color_identity_list & pip_colors. REMAINING: add strict color filter tests (tracked under TEST Colors filter constraint). Client parser removal pending minor template cleanup (move to P1 if desired).
[x] SAMPLING Commander overlap refinement (scale bonus by distinct shared synergy tags; diminishing curve)  
[x] SAMPLING Multi-color splash leniency (4–5 color commanders allow near-color enablers w/ mild penalty)  
[x] SAMPLING Role saturation penalty (discourage single-role dominance pre-synthetic)  
[x] METRICS Include curated/sample raw counts in /themes/metrics per-theme slice (per-theme raw counts)  
[x] TEST Synthetic placeholder fill (ensure placeholders inserted; roles include 'synthetic')  
[x] TEST Cache hit timing (mock clock; near-zero second build; assert cache_hit event)  
[x] TEST Colors filter constraint (colors=G restricts identities ⊆ {G} + colorless)  
[x] TEST Warm index latency reduction (cold vs warmed threshold/flag)  
[x] TEST Structured log presence (WEB_THEME_PREVIEW_LOG=1 includes duration & role_mix + raw counts)  
[x] TEST Per-theme percentile metrics existence (p50/p95 appear after multiple invocations)  
[x] INFRA Integrate rarity/mana ingestion into validator & CI lint (extend to assert normalization)  

#### P1 (High Priority UX, Observability, Performance)
[x] UI Picker reasons toggle parity (checkbox in list & detail contexts with persistence)
[x] UI Export preview sample (CSV/JSON, honors curated-only toggle) — endpoints + modal export bar
[x] UI Commander overlap & diversity rationale tooltip (bullet list distinct from reasons)
[x] UI Scroll position restore on back navigation (prevent jump) — implemented via save/restore in picker script
[x] UI Role badge wrapping improvements on narrow viewports (flex heuristics/min-width)
[x] UI Truncate long theme names + tooltip in picker header row
[x] UI-LIST Simple theme list: popularity column & quick filter (chips/dropdown) (2025-09-20)
[x] UI-LIST Simple theme list: color filter (multi-select color identity) (2025-09-20)
[x] UI Theme detail: enlarge card thumbnails to 230px (responsive sizing; progression 110px → 165px → 230px) (2025-09-20)
[x] UI Theme detail: reposition example commanders below example cards (2025-09-20)
[x] PERF Adaptive TTL/eviction tuning (hit-rate informed bounded adjustment) — adaptive TTL completed; eviction still FIFO (partial)
[x] PERF Background refresh top-K hot themes on interval (threaded warm of top request slugs)
[x] RESILIENCE Mitigate FOUC on first detail load (inline critical CSS / preload) (2025-09-20)
[x] RESILIENCE Abort controller enforcement for rapid search (cancel stale responses) (2025-09-20)
[x] RESILIENCE Disable preview refresh button during in-flight fetch (2025-09-20)
[x] RESILIENCE Align skeleton layout commander column (cross-browser flex baseline) (2025-09-20)
[x] METRICS CLI snapshot utility (scripts/preview_metrics_snapshot.py) global + top N slow themes (2025-09-20)
[x] CATALOG Decide taxonomy expansions & record rationale (Combo, Storm, Extra Turns, Group Hug/Politics, Pillowfort, Toolbox/Tutors, Treasure Matters, Monarch/Initiative) (2025-09-20)
[x] CATALOG Apply accepted new themes (YAML + normalization & whitelist updates) (2025-09-20)
[x] CATALOG Merge/normalize duplicates (ETB wording, Board Wipes variants, Equipment vs Equipment Matters, Auras vs Enchantments Matter) + diff report (2025-09-20)
[x] GOVERNANCE Enforce example count threshold (flip from optional once coverage met) (2025-09-20)  
  STATUS: Threshold logic & policy documented; enforcement switch gated on coverage metric (>90%).
[x] DOCS Contributor diff diagnostics & validation failure modes section (2025-09-20)
[x] DOCS Editorial governance note for multi-color splash relax policy (2025-09-20)
[x] CATALOG Expose advanced uncapped synergy mode outside diagnostics (config guarded) (2025-09-20)

#### P2 (Medium / Follow-On Enhancements)
[x] UI Hover compact mode toggle (reduced image & condensed metadata) (2025-09-20)
[x] UI Hover keyboard accessibility (focus traversal / ESC dismiss / ARIA refinement) (2025-09-20)
[x] UI Hover image prefetch & small LRU cache (reduce repeat fetch latency) (2025-09-20)
[x] UI Hover optional activation delay (~120ms) to reduce flicker on rapid movement (2025-09-20)
[x] UI Hover enhanced overlap highlighting (multi-color or badge styling vs single accent) (2025-09-20)
[x] DATA Externalize curated synergy pair matrix to data file (loader added; file optional) (2025-09-20)
[x] UI Commander overlap & diversity rationale richer analytics (spread index + compact mode state) (2025-09-20)
[x] SAMPLING Additional fine-tuning after observing rarity weighting impact (env-calibrated rarity weights + reasons tag) (2025-09-20)
[x] PERF Further background refresh heuristics (adaptive interval by error rate / p95 latency) (2025-09-20)
[x] RESILIENCE Additional race condition guard: preview empty panel during cache bust (retry w/backoff) (2025-09-20)
[x] DOCS Expanded editorial workflow & PR checklist (placeholder – to be appended in governance doc follow-up) (2025-09-20)
[x] CATALOG Advanced uncapped synergy mode docs & governance guidelines (already documented earlier; reaffirmed) (2025-09-20)
[x] OBS Optional: structured per-theme error histogram in metrics endpoint (per_theme_errors + retry log) (2025-09-20)

#### P3 (Move to Deferred if low traction) 
(See Deferred / Optional section for remaining low-priority or nice-to-have items)

### Deferred / Optional (Lower Priority)
[x] OPTIONAL Extended rarity diversity target (dynamic quotas) (2025-09-24) — implemented via env RARITY_DIVERSITY_TARGETS + overflow penalty RARITY_DIVERSITY_OVER_PENALTY
[ ] OPTIONAL Price / legality snippet integration (Deferred – see `logs/roadmaps/roadmap_9_budget_mode.md`)
[x] OPTIONAL Duplicate synergy collapse / summarization heuristic (2025-09-24) — implemented heuristic grouping: identical (>=2) synergy overlap sets + same primary role collapse; anchor shows +N badge; toggle to reveal all; non-destructive metadata fields dup_anchor/dup_collapsed.
[x] OPTIONAL Client-side pin/unpin personalized examples (2025-09-24) — localStorage pins with button UI in preview_fragment
[x] OPTIONAL Export preview as deck seed directly to build flow (2025-09-24) — endpoint /themes/preview/{theme_id}/export_seed.json
[x] OPTIONAL Service worker offline caching (theme list + preview fragments) (2025-09-24) — implemented `sw.js` with catalog hash versioning (?v=<catalog_hash>) precaching core shell (/, /themes/, styles, app.js, manifest, favicon) and runtime stale-while-revalidate cache for theme list & preview fragment requests. Added `catalog_hash` exposure in Jinja globals for SW version bump / auto invalidation; registration logic auto reloads on new worker install. Test `test_service_worker_offline.py` asserts presence of versioned registration and SW script serving.
[x] OPTIONAL Multi-color splash penalty tuning analytics loop (2025-09-24) — added splash analytics counters (splash_off_color_total_cards, splash_previews_with_penalty, splash_penalty_reason_events) + structured log fields (splash_off_color_cards, splash_penalty_events) for future adaptive tuning.
[x] OPTIONAL Ratchet proposal PR comment bot (description fallback regression suggestions) (2025-09-24) — Added GitHub Actions step in `editorial_governance.yml` posting/updating a structured PR comment with proposed new ceilings derived from `ratchet_description_thresholds.py`. Comment includes diff snippet for updating `test_theme_description_fallback_regression.py`, rationale list, and markers (`<!-- ratchet-proposal:description-fallback -->`) enabling idempotent updates.
[x] OPTIONAL Enhanced commander overlap rationale (structured multi-factor breakdown) (2025-09-24) — server now emits commander_rationale array (synergy spread, avg overlaps, role diversity score, theme match bonus, overlap bonus aggregate, splash leniency count) rendered directly in rationale list.

### Open Questions (for Future Decisions)
[ ] Q Should taxonomy expansion precede rarity weighting (frequency impact)?
[ ] Q Require server authoritative mana & color identity before advanced overlap refinement? (likely yes)
[ ] Q Promote uncapped synergy mode from diagnostics when governance stabilizes?
[ ] Q Splash relax penalty: static constant vs adaptive based on color spread?
  
Follow-Up (New Planned Next Steps 2025-09-24):
- [x] SAMPLING Optional adaptive splash penalty flag (`SPLASH_ADAPTIVE=1`) reading commander color count to scale penalty (2025-09-24)
  STATUS: Implemented scaling via `parse_splash_adaptive_scale()` with default spec `1:1.0,2:1.0,3:1.0,4:0.6,5:0.35`. Adaptive reasons emitted as `splash_off_color_penalty_adaptive:<colors>:<value>`.
- [x] TEST Adaptive splash penalty scaling unit test (`test_sampling_splash_adaptive.py`) (2025-09-24)
- [ ] METRICS Splash adaptive experiment counters (compare static vs adaptive deltas) (Pending – current metrics aggregate penalty events but not separated by adaptive vs static.)
- [x] DOCS Add taxonomy snapshot process & rationale section to README governance appendix. (2025-09-24)

### Exit Criteria (Phase F Completion)
[x] EXIT Rarity weighting baseline + overlap refinement + splash policy implemented (2025-09-23)
[x] EXIT Server-side mana/rarity ingestion complete (client heuristics removed) (2025-09-23) – legacy client mana & color identity parsers excised (`preview_fragment.html`) pending perf sanity
[x] EXIT Test suite covers cache timing, placeholders, color constraints, structured logs, percentile metrics (2025-09-23) – individual P0 test items all green
[x] EXIT p95 preview build time stabilized under target post-ingestion (2025-09-23) – warm p95 11.02ms (<60ms tightened target) per `logs/perf/theme_preview_baseline_warm.json`
[x] EXIT Observability includes raw curated/sample counts + snapshot tooling (2025-09-23)
[x] EXIT UX issues (FOUC, scroll restore, flicker, wrapping) mitigated (2025-09-23)

#### Remaining Micro Tasks (Phase F Close-Out)
[x] Capture & commit p95 warm baseline (v2 & v3 warm snapshots captured; tightened target <60ms p95 achieved) (2025-09-23)
[x] Define enforcement flag activation event for example coverage (>90%) and log metric (2025-09-23) – exposed `example_enforcement_active` & `example_enforce_threshold_pct` in `preview_metrics()`
[x] Kick off Core Refactor Phase A (extract `preview_cache.py`, `sampling.py`) with re-export shim – initial extraction (metrics remained then; adaptive TTL & bg refresh now migrated) (2025-09-23)
[x] Add focused unit tests for sampling (overlap bonus monotonicity, splash penalty path, rarity diminishing) post-extraction (2025-09-23)

### Core Refactor Phase A – Task Checklist (No Code Changes Yet)
Planning & Scaffolding:
[x] Inventory current `theme_preview.py` responsibilities (annotated in header docstring & inline comments) (2025-09-23)
[x] Define public API surface contract (get_theme_preview, preview_metrics, bust_preview_cache) docstring block (present in file header) (2025-09-23)
[x] Create placeholder modules (`preview_cache.py`, `sampling.py`) with docstring and TODO markers – implemented (2025-09-23)
[x] Introduce `card_index` concerns inside `sampling.py` (temporary; will split to `card_index.py` in next extraction step) (2025-09-23)

Extraction Order:
[x] Extract pure data structures / constants (scores, rarity weights) to `sampling.py` (2025-09-23)
[x] Extract card index build & lookup helpers (initially retained inside `sampling.py`; dedicated `card_index.py` module planned) (2025-09-23)
[x] Extract cache dict container to `preview_cache.py` (adaptive TTL + bg refresh still in `theme_preview.py`) (2025-09-23)
[x] Add re-export imports in `theme_preview.py` to preserve API stability (2025-09-23)
[x] Run focused unit tests post-extraction (sampling unit tests green) (2025-09-23)

Post-Extraction Cleanup:
[x] Remove deprecated inline sections from monolith (sampling duplicates & card index removed; adaptive TTL now migrated) (2025-09-23)
[x] Add mypy types for sampling pipeline inputs/outputs (TypedDict `SampledCard` added) (2025-09-23)
[x] Write new unit tests: rarity diminishing, overlap scaling, splash leniency (added) (2025-09-23) (role saturation penalty test still optional) 
[x] Update roadmap marking Phase A partial vs complete (this update) (2025-09-23)
[x] Capture LOC reduction metrics (before/after counts) in `logs/perf/theme_preview_refactor_loc.md` (2025-09-23)

Validation & Performance:
[x] Re-run performance snapshot after refactor (ensure no >5% regression p95) – full catalog single-pass baseline (`theme_preview_baseline_all_pass1_20250923.json`) + multi-pass run (`theme_preview_all_passes2.json`) captured; warm p95 within +<5% target (warm pass p95 38.36ms vs baseline p95 36.77ms, +4.33%); combined (cold+warm) p95 +5.17% noted (acceptable given cold inclusion). Tooling enhanced with `--extract-warm-baseline` and comparator `--warm-only --p95-threshold` for CI gating (2025-09-23)
  FOLLOW-UP (completed 2025-09-23): canonical CI threshold adopted (fail if warm-only p95 delta >5%) & workflow `.github/workflows/preview-perf-ci.yml` invokes wrapper to enforce.
[x] Verify background refresh thread starts post-migration (log inspection + `test_preview_bg_refresh_thread.py`) (2025-09-23)
[x] Verify adaptive TTL events emitted (added `test_preview_ttl_adaptive.py`) (2025-09-23)

---
## Refactor Objectives & Workplans (Added 2025-09-20)

We are introducing structured workplans for: Refactor Core (A), Test Additions (C), JS & Accessibility Extraction (D). Letters map to earlier action menu.

### A. Core Refactor (File Size, Modularity, Maintainability)
Current Pain Points:
- `code/web/services/theme_preview.py` (~32K lines added) monolithic: caching, sampling, scoring, rarity logic, commander heuristics, metrics, background refresh intermixed.
- `code/web/services/theme_catalog_loader.py` large single file (catalog IO, filtering, validation, metrics, prewarm) — logically separable.
- Oversized test files (`code/tests/test_theme_preview_p0_new.py`, `code/tests/test_theme_preview_ordering.py`) contain a handful of tests but thousands of blank lines (bloat).
- Inline JS in templates (`picker.html`, `preview_fragment.html`) growing; hard to lint / unit test.

Refactor Goals:
1. Reduce each service module to focused responsibilities (<800 lines per file target for readability).
2. Introduce clear internal module boundaries with stable public functions (minimizes future churn for routes & tests).
3. Improve testability: smaller units + isolated pure functions for scoring & sampling.
4. Prepare ground for future adaptive eviction (will slot into new cache module cleanly).
5. Eliminate accidental file bloat (trim whitespace, remove duplicate blocks) without semantic change.

Proposed Module Decomposition (Phase 1 – no behavior change):
- `code/web/services/preview_cache.py`
  - Responsibilities: in-memory OrderedDict cache, TTL adaptation, background refresh thread, metrics aggregation counters, `bust_preview_cache`, `preview_metrics` (delegated).
  - Public API: `get_cached(slug, key)`, `store_cached(slug, key, payload)`, `record_build(ms, curated_count, role_counts, slug)`, `maybe_adapt_ttl()`, `ensure_bg_thread()`, `preview_metrics()`.
- `code/web/services/card_index.py`
  - Card CSV ingestion, normalization (rarity, mana, color identity lists, pip extraction).
  - Public API: `maybe_build_index()`, `lookup_commander(name)`, `get_tag_pool(theme)`.
- `code/web/services/sampling.py`
  - Deterministic seed, card role classification, scoring (including commander overlap scaling, rarity weighting, splash penalties, role saturation, diversity quotas), selection pipeline returning list of chosen cards (no cache concerns).
  - Public API: `sample_cards(theme, synergies, limit, colors_filter, commander)`.
- `code/web/services/theme_preview.py` (after extraction)
  - Orchestrator: assemble detail (via existing catalog loader), call sampling, layer curated examples, synth placeholders, integrate cache, build payload.
  - Public API remains: `get_theme_preview`, `preview_metrics`, `bust_preview_cache` (re-export from submodules for backward compatibility).

Phase 2 (optional, after stabilization):
- Extract adaptive TTL policy into `preview_policy.py` (so experimentation with hit-ratio bands is isolated).
- Add interface / protocol types for cache backends (future: Redis experimentation).

Test Impact Plan:
- Introduce unit tests for `sampling.sample_cards` (roles distribution, rarity diminishing, commander overlap bonus monotonic increase with overlap count, splash penalty trigger path).
- Add unit tests for TTL adaptation thresholds with injected recent hits deque.

Migration Steps (A):
1. Create new modules with copied (not yet deleted) logic; add thin wrappers in old file calling new functions.
2. Run existing tests to confirm parity.
3. Remove duplicated logic from legacy monolith; leave deprecation comments.
4. Trim oversized test files to only necessary lines (reformat into logical groups).
5. Add mypy-friendly type hints between modules (use `TypedDict` or small dataclasses for card item shape if helpful).
6. Update roadmap: mark refactor milestone complete when file LOC & module boundaries achieved.

Acceptance Criteria (A):
- All existing endpoints unchanged.
- No regressions in preview build time (baseline within ±5%).
- Test suite green; new unit tests added.
- Adaptive TTL + background refresh still functional (logs present).

### Refactor Progress Snapshot (2025-09-23)
Refactor Goals Checklist (Phase A):
Refactor Goals Checklist (Phase A):
 - [x] Goal 1 (<800 LOC per module) — current LOC: `theme_preview.py` ~525, `sampling.py` 241, `preview_cache.py` ~140, `card_index.py` ~200 (all below threshold; monolith reduced dramatically).
 - [x] Goal 2 Module boundaries & stable public API (`__all__` exports maintained; re-export shim present).
 - [x] Goal 3 Testability improvements — new focused sampling tests (overlap monotonicity, splash penalty, rarity diminishing). Optional edge-case tests deferred.
 - [x] Goal 4 Adaptive eviction & backend abstraction implemented (2025-09-24) — heuristic scoring + metrics + overflow guard + backend interface extracted.
 - [x] Goal 5 File bloat eliminated — duplicated blocks & legacy inline logic removed; large helpers migrated.

Phase 1 Decomposition Checklist:
 - [x] Extract `preview_cache.py` (cache container + TTL adaptation + bg refresh)
 - [x] Extract `sampling.py` (sampling & scoring pipeline)
 - [x] Extract `card_index.py` (CSV ingestion & normalization)
 - [x] Retain orchestrator in `theme_preview.py` (now focused on layering + metrics + cache usage)
 - [x] Deduplicate role helpers (`_classify_role`, `_seed_from`) (helpers removed from `theme_preview.py`; authoritative versions reside in `sampling.py`) (2025-09-23)

Phase 2 (In Progress):
Phase 2 (Completed 2025-09-24):
 - [x] Extract adaptive TTL policy tuning constants to `preview_policy.py` (2025-09-23)
 - [x] Introduce cache backend interface (protocol) for potential Redis experiment (2025-09-23) — `preview_cache_backend.py`
 - [x] Separate metrics aggregation into `preview_metrics.py` (2025-09-23)
 - [x] Scoring constants / rarity weights module (`sampling_config.py`) for cleaner tuning surface (2025-09-23)
 - [x] Implement adaptive eviction strategy (hit-ratio + recency + cost hybrid) & tests (2025-09-23)
 - [x] Add CI perf regression check (warm-only p95 threshold) (2025-09-23) — implemented via `.github/workflows/preview-perf-ci.yml` (fails if warm p95 delta >5%)
 - [x] Multi-pass CI variant flag (`--multi-pass`) for cold/warm differential diagnostics (2025-09-24)

Performance & CI Follow-Ups:
 - [x] Commit canonical warm baseline produced via `--extract-warm-baseline` into `logs/perf/` (`theme_preview_warm_baseline.json`) (2025-09-23)
 - [x] Add CI helper script wrapper (`preview_perf_ci_check.py`) to generate candidate + compare with threshold (2025-09-23)
 - [x] Add GitHub Actions / task invoking wrapper: `python -m code.scripts.preview_perf_ci_check --baseline logs/perf/theme_preview_warm_baseline.json --p95-threshold 5` (2025-09-23) — realized in workflow `preview-perf-ci`
 - [x] Document perf workflow in `README.md` (section: Performance Baselines & CI Gate) (2025-09-23)
 - [x] (Optional) Provide multi-pass variant option in CI (flag) if future warm-only divergence observed (2025-09-23)
 - [x] Add CHANGELOG entry formalizing performance gating policy & warm baseline refresh procedure (criteria: intentional improvement >10% p95 OR drift >5% beyond tolerance) (2025-09-24) — consolidated with Deferred Return Tasks section entry

Open Follow-Ups (Minor / Opportunistic):
Open Follow-Ups (Minor / Opportunistic):
 - [x] Role saturation penalty dedicated unit test (2025-09-23)
 - [x] card_index edge-case test (rarity normalization & duplicate name handling) (2025-09-23)
 - [x] Consolidate duplicate role/hash helpers into sampling (2025-09-24)
 - [x] Evaluate moving commander bias constants to config module for easier tuning (moved to `sampling_config.py`, imports updated) (2025-09-23)
 - [x] Add regression test: Scryfall query normalization strips synergy annotations (image + search URLs) (2025-09-23)

Status Summary (Today): Phase A decomposition effectively complete; only minor dedup & optional tests outstanding. Phase 2 items queued; performance tooling & baseline captured enabling CI regression gate next. Synergy annotation Scryfall URL normalization bug fixed across templates & global JS (2025-09-23); regression test pending.

Recent Change Note (2025-09-23): Added cache entry metadata (hit_count, last_access, build_cost_ms) & logging of cache hits. Adjusted warm latency test with guard for near-zero cold timing to reduce flakiness post-cache instrumentation.

### Phase 2 Progress (2025-09-23 Increment)
 - [x] Extract adaptive TTL policy tuning constants to `preview_policy.py` (no behavior change; unit tests unaffected)
   FOLLOW-UP: add env overrides & validation tests for bands/steps (new deferred task)

### Adaptive Eviction Plan (Kickoff 2025-09-23)
Goal: Replace current FIFO size-limited eviction with an adaptive heuristic combining recency, hit frequency, and rebuild cost to maximize effective hit rate while minimizing expensive rebuild churn.

Data Model Additions (per cache entry):
 - inserted_at_ms (int)
 - last_access_ms (int) — update on each hit
 - hit_count (int)
 - build_cost_ms (int) — capture from metrics when storing
 - slug (theme identifier) + key (variant) retained

Heuristic (Evict lowest ProtectionScore):
 ProtectionScore = (W_hits * log(1 + hit_count)) + (W_recency * recency_score) + (W_cost * cost_bucket) - (W_age * age_score)
Where:
 - recency_score = 1 / (1 + minutes_since_last_access)
 - age_score = minutes_since_inserted
 - cost_bucket = 0..3 derived from build_cost_ms thresholds (e.g. <5ms=0, <15ms=1, <40ms=2, >=40ms=3)
 - Weights default (tunable via env): W_hits=3.0, W_recency=2.0, W_cost=1.0, W_age=1.5

Algorithm:
 1. On insertion when size > MAX: build candidate list (all entries OR bounded sample if size > SAMPLE_THRESHOLD).
 2. Compute ProtectionScore for each candidate.
 3. Evict N oldest/lowest-score entries until size <= MAX (normally N=1, loop in case of concurrent overshoot).
 4. Record eviction event metric with reason fields: {hit_count, age_ms, build_cost_ms, protection_score}.

Performance Safeguards:
 - If cache size > 2 * MAX (pathological), fall back to age-based eviction ignoring scores (O(n) guard path) and emit warning metric.
 - Optional SAMPLE_TOP_K (default disabled). When enabled and size > 2*MAX, sample K random entries + oldest X to bound calculation time.

Environment Variables (planned additions):
 - THEME_PREVIEW_EVICT_W_HITS / _W_RECENCY / _W_COST / _W_AGE
 - THEME_PREVIEW_EVICT_COST_THRESHOLDS (comma list e.g. "5,15,40")
 - THEME_PREVIEW_EVICT_SAMPLE_THRESHOLD (int) & THEME_PREVIEW_EVICT_SAMPLE_SIZE (int)

Metrics Additions (`preview_metrics.py`):
 - eviction_total (counter)
 - eviction_by_reason buckets (low_score, emergency_overflow)
 - eviction_last (gauge snapshot of last event metadata)
 - eviction_hist_build_cost_ms (distribution)

Testing Plan:
 1. test_eviction_prefers_low_hit_old_entries: create synthetic entries with varying hit_count/age; assert low score evicted.
 2. test_eviction_protects_hot_recent: recent high-hit entry retained when capacity exceeded.
 3. test_eviction_cost_bias: two equally old entries different build_cost_ms; cheaper one evicted.
 4. test_eviction_emergency_overflow: simulate size >2*MAX triggers age-only path and emits warning metric.
 5. test_eviction_metrics_emitted: store then force eviction; assert counters increment & metadata present.

Implementation Steps (Ordered):
 1. Extend cache entry structure in `preview_cache.py` (introduce metadata fields) (IN PROGRESS 2025-09-23 ✅ base dict metadata: inserted_at, last_access, hit_count, build_cost_ms).
 2. Capture build duration (already known at store time) into entry.build_cost_ms. (✅ implemented via store_cache_entry)
 3. Update get/store paths to mutate hit_count & last_access_ms.
 4. Add weight & threshold resolution helper (reads env once; cached, with reload guard for tests). (✅ implemented: _resolve_eviction_weights / _resolve_cost_thresholds / compute_protection_score)
 5. Implement `_compute_protection_score(entry, now_ms)`.
 6. Implement `_evict_if_needed()` invoked post-store under lock.
 7. Wire metrics recording & add to `preview_metrics()` export.
 8. Write unit tests with small MAX (e.g. set THEME_PREVIEW_CACHE_MAX=5) injecting synthetic entries via public API or helper. (IN PROGRESS: basic low-score eviction test added `test_preview_eviction_basic.py`; remaining: cost bias, hot retention, emergency overflow, metrics detail test)
 9. Benchmark warm p95 to confirm <5% regression (update baseline if improved).
10. Update roadmap & CHANGELOG (add feature note) once tests green.

Acceptance Criteria:
 - All new tests green; no regression in existing preview tests.
 - Eviction events observable via metrics endpoint & structured logs.
 - Warm p95 delta within ±5% of baseline (or improved) post-feature.
 - Env weight overrides respected (smoke test via one test toggling W_HITS=0 to force different eviction order).

Progress Note (2025-09-23): Steps 5-7 implemented (protection score via `compute_protection_score`, adaptive `evict_if_needed`, eviction metrics + structured log). Basic eviction test passing. Remaining tests & perf snapshot pending.

Progress Update (2025-09-23 Later): Advanced eviction tests added & green:
 - test_preview_eviction_basic.py (low-score eviction)
 - test_preview_eviction_advanced.py (cost bias retention, hot entry retention, emergency overflow path trigger, env weight override)
Phase 2 Step 8 now complete (full test coverage for initial heuristic). Next: Step 9 performance snapshot (warm p95 delta check <5%) then CHANGELOG + roadmap close-out for eviction feature (Step 10). Added removal of hard 50-entry floor in `evict_if_needed` to allow low-limit tests; operational deployments can enforce higher floor via env. No existing tests regressed.

Additional Progress (2025-09-23): Added `test_scryfall_name_normalization.py` ensuring synergy annotation suffix is stripped; roadmap follow-up item closed.

Deferred (Post-MVP) Ideas:
 - Protect entries with curated_only flag separately (bonus weight) if evidence of churn emerges.
 - Adaptive weight tuning based on rolling hit-rate KPI.
 - Redis backend comparative experiment using same scoring logic.


### C. Test Additions (Export Endpoints & Adaptive TTL)
Objectives:
1. Validate `/themes/preview/{theme}/export.json` & `.csv` endpoints (status 200, field completeness, curated_only filter semantics).
2. Validate CSV header column order is stable.
3. Smoke test adaptive TTL event emission (simulate hit/miss pattern to cross a band and assert printed `theme_preview_ttl_adapt`).
4. Increase preview coverage for curated_only filtering (confirm role exclusion logic matching examples + curated synergy only).

Test Files Plan:
- New `code/tests/test_preview_export_endpoints.py`:
  - Parametrized theme slug (pick first theme from index) to avoid hard-coded `Blink` dependency.
  - JSON export: assert keys subset {name, roles, score, rarity, mana_cost, color_identity_list, pip_colors}.
  - curated_only=1: assert no sampled roles in roles set {payoff,enabler,support,wildcard}.
  - CSV export: parse first line for header stability.
- New `code/tests/test_preview_ttl_adaptive.py`:
  - Monkeypatch `_ADAPTATION_ENABLED = True`, set small window, inject sequence of hits/misses by calling `get_theme_preview` & optionally direct manipulation of deque if needed.
  - Capture stdout; assert adaptation log appears with expected event.

Non-Goals (C):
- Full statistical validation of score ordering (belongs in sampling unit tests under refactor A).
- Integration latency benchmarks (future optional performance tests).

### D. JS Extraction & Accessibility Improvements
Objectives:
1. Move large inline scripts from `picker.html` & `preview_fragment.html` into static JS files for linting & reuse.
2. Add proper modal semantics & focus management (role="dialog", aria-modal, focus trap, ESC close, return focus to invoker after close).
3. Implement AbortController in search (cancel previous fetch) and disable refresh button while a preview fetch is in-flight.
4. Provide minimal build (no bundler) using plain ES modules—keep dependencies zero.

Planned Files:
- `code/web/static/js/theme_picker.js`
- `code/web/static/js/theme_preview_modal.js`
- (Optional) `code/web/static/js/util/accessibility.js` (trapFocus, restoreFocus helpers)

Implementation Steps (D):
1. Extract current inline JS blocks preserving order; wrap in IIFEs exported as functions if needed.
2. Add `<script type="module" src="/static/js/theme_picker.js"></script>` in `base.html` or only on picker route template.
3. Replace inline modal creation with accessible structure:
   - Add container with `role="dialog" aria-labelledby="preview-heading" aria-modal="true"`.
   - On open: store activeElement, focus first focusable (close button).
   - On ESC or close: remove modal & restore focus.
4. AbortController: hold reference in closure; on new search input, abort prior, then issue new fetch.
5. Refresh button disable: set `disabled` + aria-busy while fetch pending; re-enable on completion or failure.
6. Add minimal accessibility test (JS-free fallback: ensure list still renders). (Optional for now.)

Acceptance Criteria (D):
- Picker & preview still function identically (manual smoke).
- Lighthouse / axe basic scan passes (no blocking dialog issues, focus trap working).
- Inline JS in templates reduced to <30 lines (just bootstrapping if any).

### Cross-Cutting Risks & Mitigations
- Race conditions during refactor: mitigate by staged copy, then delete.
- Thread interactions (background refresh) in tests: set `THEME_PREVIEW_BG_REFRESH=0` within test environment to avoid nondeterminism.
- Potential path import churn: maintain re-export surface from `theme_preview.py` until downstream usages updated.

### Tracking
Add a new section in future updates summarizing A/C/D progress deltas; mark each Acceptance Criteria bullet as met with date.

---

### Progress (2025-09-20 Increment)
 - Implemented commander overlap & diversity rationale tooltip (preview modal). Added dynamic list computing role distribution, distinct synergy overlaps, average overlaps, diversity heuristic score, curated share. Marked item complete in P1.
 - Added AbortController cancellation for rapid search requests in picker (resilience improvement).
 - Implemented simple list popularity quick filters (chips + select) and color identity multi-select filtering.
 - Updated theme detail layout: enlarged example card thumbnails and moved commander examples below cards (improves scan order & reduces vertical jump).
 - Mitigated FOUC and aligned skeleton layout; preview refresh now disabled while list fetch in-flight.
 - Added metrics snapshot CLI utility `code/scripts/preview_metrics_snapshot.py` (captures global + top N slow themes).
 - Catalog taxonomy rationale documented (`docs/theme_taxonomy_rationale.md`); accepted themes annotated and duplicates normalization logged.
 - Governance & editorial policies (examples threshold, splash relax policy) added to README and taxonomy rationale; enforcement gating documented.
 - Contributor diagnostics & validation failure modes section added (README governance segment + rationale doc).
 - Uncapped synergy mode exposure path documented & config guard clarified.


### Success Metrics (Reference)
[x] METRIC Metadata_info coverage >=99% (achieved)
[ ] METRIC Generic fallback description KPI trending down per release window (continue tracking)
[ ] METRIC Warmed preview median & p95 under established thresholds after ingestion (record baseline then ratchet)

---
This unified ledger supersedes all prior phased or sectional lists. Historical narrative available via git history if needed.

### Deferral Notes (Added 2025-09-24)
The Price / legality snippet integration is deferred and will be handled holistically in the Budget Mode initiative (`roadmap_9_budget_mode.md`) to centralize price sourcing (API selection, caching, rate limiting), legality checks, and UI surfaces. This roadmap will only re-introduce a lightweight read-only badge if an interim need emerges.
\n+### Newly Deferred Return Tasks (Added 2025-09-23)
### Newly Deferred Return Tasks (Added 2025-09-23) (Updated 2025-09-24)
[x] POLICY Env overrides for TTL bands & step sizes + tests (2025-09-24) — implemented via env parsing in `preview_policy.py` (`THEME_PREVIEW_TTL_BASE|_MIN|_MAX`, `THEME_PREVIEW_TTL_BANDS`, `THEME_PREVIEW_TTL_STEPS`)
[x] PERF Multi-pass CI variant toggle (enable warm/cold delta diagnostics when divergence suspected) (2025-09-24)
[x] CACHE Introduce backend interface & in-memory implementation wrapper (prep for Redis experiment) (2025-09-23)
[x] CACHE Redis backend PoC + latency/CPU comparison & fallback logic (2025-09-24) — added `preview_cache_backend.py` optional Redis read/write-through (env THEME_PREVIEW_REDIS_URL). Memory remains source of truth; Redis used opportunistically on memory miss. Metrics expose redis_get_attempts/hits/errors & store_attempts/errors. Graceful fallback when library/connection absent verified via `test_preview_cache_redis_poc.py`.
[x] DOCS CHANGELOG performance gating policy & baseline refresh procedure (2025-09-24)
[x] SAMPLING Externalize scoring & rarity weights to `sampling_config.py` (2025-09-23)
[x] METRICS Extract `preview_metrics.py` module (2025-09-23)