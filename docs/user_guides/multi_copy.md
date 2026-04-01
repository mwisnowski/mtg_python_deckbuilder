# Multi-Copy Package

Build decks that run many copies of a single card-type — Relentless Rats, Shadowborn Apostles, and more.

---

## Overview

Some Magic cards have a printed exception allowing any number of copies in a Commander deck. The Multi-Copy Package feature lets you include a chosen archetype card at a configured count and builds the rest of the deck around it.

Enable with `ALLOW_MUST_HAVES=1` (default: on). The **Enable Multi-Copy package** checkbox appears in the New Deck modal preferences section.

---

## How It Works

1. Check **Enable Multi-Copy package** in the New Deck modal.
2. When you add an eligible card to Must Include, a **count picker dialog** appears. Set the number of copies.
3. The builder reserves those slots for the archetype card before filling the rest of the deck from the theme pool.
4. The multi-copy card is locked automatically and appears in Step 5 alongside the rest of the build.

The builder auto-suggests the dialog when your commander's theme tags match the archetype's trigger conditions. You can also manually add any eligible card via the quick-add input and set a count freely.

---

## Supported Archetypes

| Card | Color | Cap | Theme triggers |
|------|-------|-----|----------------|
| Cid, Timeless Artificer | W/U | None (20–30 suggested) | artificer kindred, artifacts matter |
| Dragon's Approach | R | None (20–30 suggested) | burn, spellslinger, storm, copy |
| Hare Apparent | W | None (20–30 suggested) | rabbit kindred, tokens matter |
| Nazgûl | B | **9** (printed cap) | wraith kindred, ring, amass |
| Persistent Petitioners | U | None (20–30 suggested) | mill, advisor kindred, control |
| Rat Colony | B | None (20–30 suggested) | rats, swarm, aristocrats |
| Relentless Rats | B | None (20–30 suggested) | rats, swarm, aristocrats |
| Seven Dwarves | R | **7** (printed cap) | dwarf kindred, treasure, equipment |
| Shadowborn Apostle | B | None (20–30 suggested) | demon kindred, aristocrats, sacrifice |
| Slime Against Humanity | G | None (20–30 suggested) | tokens, mill, graveyard, domain |
| Tempest Hawk | W | None (20–30 suggested) | bird kindred, aggro |
| Templar Knight | W | None (20–30 suggested) | human kindred, knight kindred |

Cards with a **printed cap** (Nazgûl: 9, Seven Dwarves: 7) cannot exceed their cap — the count picker enforces the maximum.

---

## Exclusive Groups

Rat Colony and Relentless Rats are mutually exclusive — they share the `rats` exclusive group. If both are added, a dialog will prompt you to choose one. Only one rat archetype can be active per build.

---

## Count Recommendations

For uncapped archetypes, the suggested range is **20–30 copies**. This leaves room for a commander, support spells, and lands in a 100-card deck. The sweet spot is often 20–25 copies, which allows ~15–20 support cards and ~35 lands.

Archetypes with many synergy triggers (Shadowborn Apostle, Relentless Rats) can push toward 30 when the commander specifically supports the archetype.

---

## Bracket Interaction

High copy counts of powerful archetypes can affect bracket compliance:

- **Thrumming Stone** (which many of these archetypes synergise with) is a Game Changer — using it in Bracket 2 or below will trigger a compliance warning.
- The archetype cards themselves are generally not on the Game Changers list, but check the compliance report in Step 5 after building.

---

## Headless / CLI

Set the multi-copy card and count in your JSON config via the `must_include` list. The count picker is a UI affordance — in headless mode, add the card name the desired number of times:

```json
{
  "must_include": [
    "Relentless Rats", "Relentless Rats", "Relentless Rats",
    "Relentless Rats", "Relentless Rats"
  ]
}
```

---

## FAQ

**Why doesn't the count picker appear when I add a multi-copy card?**
The auto-suggest only triggers when your commander's theme tags match the archetype's trigger conditions. If you don't see the dialog, try adding the card manually via the quick-add input — the dialog will appear for recognized archetype names regardless of commander.

**Can I run a multi-copy package with `owned_only` mode?**
Yes, but you need that many copies of the card in your owned card library. The builder will include the configured count regardless of owned status for Must Include cards — they bypass the owned filter.

**Will the multi-copy card count toward my ideal creature or spell count?**
Yes. Multi-copy creature archetypes (e.g., Relentless Rats) count toward the creature ideal, and non-creature archetypes (e.g., Dragon's Approach) count toward the spell ideal. Adjust your ideal counts in Step 6 accordingly.

---

## See Also

- [Include / Exclude Lists](include_exclude.md) — must-include and must-exclude cards in general
- [Bracket Compliance](bracket_compliance.md) — Thrumming Stone and archetype interaction with brackets
- [Build Wizard](build_wizard.md) — multi-copy package in the context of the full build flow
