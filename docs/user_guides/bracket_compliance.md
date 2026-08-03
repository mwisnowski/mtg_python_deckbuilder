# Bracket Compliance

Select a power level for your deck and get a detailed compliance report against the official Commander bracket rules.

---

## Overview

Commander brackets define five power tiers from Exhibition (casual) to cEDH (competitive). The builder checks your finished deck against the rules for your selected bracket and surfaces a PASS / WARN / FAIL report per category.

Bracket selection lives in the **New Deck modal**. The compliance report appears in Step 5 and is exported to the compliance JSON sidecar (`deck_files/*_compliance.json`).

---

## Bracket Tiers

| Bracket | Name | Key restrictions |
|---------|------|-----------------|
| 1 | Exhibition | No Game Changers; no two-card infinite combos; no mass land denial; extra turns discouraged; tutors sparse |
| 2 | Core | No Game Changers; no two-card infinite combos; no mass land denial; extra turns not chained; tutors sparse |
| 3 | Upgraded | Up to 3 Game Changers; no mass land denial; no early/cheap two-card combos; extra turns not chained |
| 4 | Optimized | No bracket restrictions (banned list still applies) |
| 5 | cEDH | No bracket restrictions (banned list still applies; competitive mindset) |

Bracket rules follow the official Wizards of the Coast Commander bracket definitions. The card lists used for compliance checks are stored in `config/card_lists/` and can be updated as WotC revises the lists.

---

## Compliance Categories

For each build, the compliance report checks:

| Category | What is checked |
|----------|----------------|
| **Game Changers** | Cards on the official Game Changers list (`config/card_lists/game_changers.json`) |
| **Extra turns** | Cards that grant extra turns (`extra_turns.json`) |
| **Mass land denial** | Cards that destroy, exile, or bounce many lands (`mass_land_denial.json`) |
| **Non-land tutors** | Cards that search the library for non-land cards |
| **Two-card combos** | Known two-card infinite combos (`combos.json`), with a flag for early/cheap combos |

Each category returns a PASS / WARN / FAIL verdict and lists the flagged cards with links.

If the **commander itself** is on the Game Changers list, it is surfaced separately at the top of the report.

---

## Enforcement

Compliance checking is always report-only: violations are flagged as WARN/FAIL, but no card is blocked from being added during selection.

To actually remove or swap out flagged cards after a build, use one of:

| Trigger | Behavior |
|---------|----------|
| **Apply Bracket Enforcement** button (Step 5 compliance panel) | Swaps FAIL-category cards for on-theme alternatives, respecting any locked cards, then re-exports the deck. |
| `WEB_AUTO_ENFORCE=1` | Runs the same enforcement/swap pass automatically right after each web build completes. |

| Scenario | Report-only (default) | After Apply/`WEB_AUTO_ENFORCE` |
|----------|------------------------|--------------------------------|
| 1–3 Game Changers in pool (Bracket 3) | Each flagged in report | Kept (within the 3-card cap) |
| 4+ Game Changers in pool (Bracket 3) | All flagged FAIL in report | Extras swapped for alternatives; capped at 3 |
| Mass land denial card | Flagged WARN/FAIL in report | Swapped for an alternative if one exists in the pool |
| Must Include card violates bracket | Flagged in report; card stays | Card stays (Must Include always wins; never swapped) |

---

## Web UI

- The bracket dropdown in the New Deck modal defaults to **Core (Bracket 2)** when no bracket is set.
- The compliance banner in Step 5 shows a color-coded overall verdict (green=PASS, yellow=WARN, red=FAIL) and expandable per-category details.
- `WEB_AUTO_ENFORCE=1` re-runs compliance export automatically after each completed build.

---

## Maintaining the Card Lists

The Game Changers list and companion lists are static JSON files in `config/card_lists/`. Each file includes `source_url` and `generated_at` metadata. Update them manually when WotC publishes revisions. Unknown cards in lookups are skipped with a note in the compliance report — they do not cause a hard failure.

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `WEB_AUTO_ENFORCE` | `0` | Auto-run compliance export after every build. |

---

## FAQ

**My deck passed Bracket 2 but the table says it feels more like Bracket 3 — why?**
The compliance check runs against the official card lists (Game Changers, extra turns, tutors, combos). Cards not on those lists are not flagged even if they're powerful in context. Use the compliance report as a starting point, then discuss with your table.

**I applied bracket enforcement but my Must Include card still violates the bracket.**
Must Include cards always bypass enforcement swaps — they are inserted directly and never removed. The compliance report will still flag the violation. Adjust the Must Include list or the bracket to resolve it.

**Why does the compliance check flag a two-card combo I didn't intend?**
Combo detection runs against a known list of two-card infinite combinations. If your synergies happen to match a known combo pattern, they'll be flagged. The report is informational — no cards are removed automatically.

**Can I update the Game Changers list when WotC publishes new cards?**
Yes. Edit the JSON files in `config/card_lists/` (e.g., `game_changers.json`). Each file has a `source_url` field pointing to the canonical source. Restart the server after editing.

---

## See Also

- [Build Wizard](build_wizard.md) — step-by-step guide covering bracket selection in context
- [Include / Exclude Lists](include_exclude.md) — how Must Include cards interact with bracket enforcement
- [Partner Mechanics](partner_mechanics.md) — bracket implications when the commander is on the Game Changers list
