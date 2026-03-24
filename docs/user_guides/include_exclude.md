# Include / Exclude Lists

Pin specific cards into every build or permanently block them from selection.

---

## Overview

The Include / Exclude feature (also called "Must-Haves") lets you control card selection at the individual card level, outside the normal theme and pool logic.

- **Must Include**: cards are always added to the deck, before pool selection runs.
- **Must Exclude**: cards are never added, regardless of theme, bracket, or pool filtering.

Requires `ALLOW_MUST_HAVES=1` (default: on).

---

## Enabling the UI Controls

The include/exclude buttons are hidden by default to keep the Step 5 interface clean. To show them:

```
SHOW_MUST_HAVE_BUTTONS=1
```

When enabled, each card row in Step 5 gains a Must Include (+) and Must Exclude (−) button. You can also manage lists via the quick-add input at the top of the section.

---

## Adding Cards

### Via Step 5 UI
1. Enable `SHOW_MUST_HAVE_BUTTONS=1`.
2. In Step 5, click **+** on a card to add it to Must Include, or **−** to add it to Must Exclude.
3. Use the quick-add input at the top to add cards by name without scrolling.

### Via JSON Config
Supply lists in your deck config file:

```json
{
  "must_include": ["Sol Ring", "Arcane Signet"],
  "must_exclude": ["Thassa's Oracle"]
}
```

Both keys accept an array of card names. Names are matched case-insensitively.

---

## Priority Order

When include/exclude interacts with other filters, this order applies:

1. **Must Exclude** — always wins; card is never selected.
2. **Must Include** — card is always added, before pool selection.
3. **Budget filter** — applied to the remaining pool after Must Include cards are inserted.
4. **Bracket filter** — applied after budget.

Must Include cards are inserted directly and are not subject to budget pool filtering. They may appear as over-budget in the summary if they exceed the ceiling, and they may trigger bracket warnings if they violate bracket rules.

---

## Multi-Copy Archetypes

If a card is in Must Include and the builder detects it supports multi-copy (e.g., Relentless Rats), a count picker dialog appears. Set the desired copy count before confirming.

---

## Conflict Resolution

| Scenario | Behavior |
|----------|----------|
| Card is in both Must Include and Must Exclude | A conflict dialog prompts you to resolve before building. Exclude wins if unresolved. |
| Must Include card not in color identity | Build silently skips the card (does not hard-fail). Verify color identity before including. |
| Must Include card violates bracket rule | Card is added; bracket compliance report flags it. Resolve in Step 5 or adjust bracket. |

---

## Headless / CLI

Set include and exclude lists in the JSON config. Environment variable overrides are not supported for per-card lists; use the config file.

```json
{
  "must_include": ["Swiftfoot Boots"],
  "must_exclude": ["Demonic Tutor"]
}
```
