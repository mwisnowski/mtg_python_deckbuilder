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

Some cards have a printed exception allowing any number of copies in a Commander deck. When you add one of these cards to Must Include, a count picker dialog appears to set the desired copy count.

For the full list of supported archetypes, count caps, and detailed guidance see the [Multi-Copy Package](multi_copy.md) guide.

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

---

## FAQ

**Can I include a card that isn't in my commander's color identity?**
The builder will attempt to add it but will silently skip it if the card is outside the commander's color identity. Check the build summary for skipped cards.

**What happens if my Must Include list makes the deck exceed 100 cards?**
Must Include cards are inserted before pool selection fills the remaining slots. The total is always capped at 100 cards, with Must Includes taking priority over pool-selected cards.

**Do Must Include cards count against bracket compliance?**
Yes. A Must Include card that violates your bracket (e.g., a Game Changer at Bracket 2) will be flagged in the compliance report. The card stays in the deck regardless of enforcement mode.

---

## See Also

- [Build Wizard](build_wizard.md) — where Include/Exclude fits in the overall build flow
- [Multi-Copy Package](multi_copy.md) — dedicated guide for multi-copy archetype builds
- [Bracket Compliance](bracket_compliance.md) — how Must Include cards interact with bracket enforcement
- [Locks, Replace & Permalinks](locks_replace_permalinks.md) — lock cards in place and swap alternatives after building
