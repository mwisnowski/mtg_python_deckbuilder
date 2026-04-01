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

## Enforcement Mode

Set `enforcement_mode` in your JSON config to control how the builder handles bracket violations:

| Mode | Behavior |
|------|----------|
| `validate` | Build freely, then report violations. No cards are blocked. _(default)_ |
| `prefer` | During selection, avoid adding disallowed categories; cap Game Changers for Bracket 3. |
| `strict` | Block additions that would violate the bracket. Build fails with a clear message if unavoidable. |

```json
{
  "bracket": "core",
  "enforcement_mode": "prefer"
}
```

### Enforcement Examples (Bracket 3 — Upgraded)

| Scenario | `validate` | `prefer` | `strict` |
|----------|------------|----------|---------|
| 1–3 Game Changers in pool | Proceeds; each flagged in report | Proceeds; included within 3-card cap | Proceeds; included within 3-card cap |
| 4+ Game Changers in pool | All flagged FAIL in report | Caps selection at 3; extras skipped | Build fails listing the violating cards |
| Mass land denial card | Flagged WARN/FAIL in report | Avoided if alternatives exist in pool | Build fails if card cannot be excluded |
| Must Include card violates bracket | Flagged in report; card stays | Flagged in report; card stays | Flagged in report; card stays (Must Include always wins) |

---

## Rule Zero Notes

The `rule_zero_notes` field in the JSON config lets you document table agreements that override standard bracket rules:

```json
{
  "bracket": "upgraded",
  "rule_zero_notes": "Mass land denial allowed by table agreement. Two-card combos capped at 1."
}
```

Rule zero notes appear in the compliance report header and are exported to the compliance JSON.

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

## JSON Config Keys

| Key | Values | Purpose |
|-----|--------|---------|
| `bracket` | `exhibition` \| `core` \| `upgraded` \| `optimized` \| `cedh` | Bracket selection. Defaults to `core` if unset. |
| `enforcement_mode` | `validate` \| `prefer` \| `strict` | How violations are handled during building. |
| `rule_zero_notes` | string | Optional table agreement notes included in the compliance report. |

---

## FAQ

**My deck passed Bracket 2 but the table says it feels more like Bracket 3 — why?**
The compliance check runs against the official card lists (Game Changers, extra turns, tutors, combos). Cards not on those lists are not flagged even if they're powerful in context. Use the compliance report as a starting point, then discuss with your table.

**I set `enforcement_mode: strict` but my Must Include card still violates the bracket.**
Must Include cards always bypass enforcement filtering — they are inserted directly before pool selection runs. The compliance report will still flag the violation. Adjust the Must Include list or the bracket to resolve it.

**Why does the compliance check flag a two-card combo I didn't intend?**
Combo detection runs against a known list of two-card infinite combinations. If your synergies happen to match a known combo pattern, they'll be flagged. The report is informational — no cards are removed automatically.

**Can I update the Game Changers list when WotC publishes new cards?**
Yes. Edit the JSON files in `config/card_lists/` (e.g., `game_changers.json`). Each file has a `source_url` field pointing to the canonical source. Restart the server after editing.

---

## See Also

- [Build Wizard](build_wizard.md) — step-by-step guide covering bracket selection in context
- [Include / Exclude Lists](include_exclude.md) — how Must Include cards interact with bracket enforcement
- [Partner Mechanics](partner_mechanics.md) — bracket implications when the commander is on the Game Changers list
