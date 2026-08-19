# Rulebreaker Commanders

Build with commanders that bend one specific deckbuilding rule, each in its own unique way.

---

## Overview

Some commanders carry the **Rulebreaker** ability word: a printed exception that relaxes one normal Commander deckbuilding rule (usually color identity or deck size) in a narrow, specific way, everything else about deckbuilding still applies as usual. The builder detects these commanders automatically (by name) and applies their exception during card pool filtering, land selection, and (for one commander) deck-size scaling, on the web app, the mobile app, and the Manual Deck Builder alike.

There's no setting to turn this on or off. If you pick one of the commanders below, its exception is applied automatically.

---

## The 8 Rulebreaker Commanders

| Commander | Color Identity | What it relaxes |
|---|---|---|
| **Grizzlegom, Hurloon Hero** | R, G | Any land cards, of any color, are legal. |
| **Maular, the Next Evolution** | G | Creature cards with mana value 7+, of any color identity, plus any basic lands, are legal. |
| **Seluma, Light of Aysen** | W | Angel cards of any color identity, plus any basic lands, are legal. |
| **The Everforger** | (colorless) | Artifact Creature and Equipment cards of any color identity, plus any basic lands, are legal. |
| **The Unluckiest Planeswalker** | R | Aura cards of any color identity, plus any basic lands, are legal. |
| **Tolabow, Loch Rascal** | U | Instant and Sorcery cards can use one extra color of your choice (optional), plus any basic lands, are legal. |
| **Valko Indorian** | B | Cards with the Phyrexian creature subtype, of any color identity, plus any basic lands, are legal. |
| **Whtz, the Bibliophile** | U, W | No maximum deck size (the 100-card minimum still applies). |

Each exception is scoped to exactly what's printed on the card, nothing more. For example, Maular only relaxes color identity for creatures with mana value 7 or greater; a 3-mana off-color creature is still illegal, and Grizzlegom's land relaxation doesn't extend to spells.

---

## Selecting a Rulebreaker Commander

### Web
Selecting one of the 8 commanders (as a primary commander, or as one half of a Partner/Background pair) shows an informational banner describing its exception in plain language on the commander step.

- **Tolabow**: an optional color picker appears (excluding Tolabow's own color, blue). Leave it unset to build a mono-blue Instant/Sorcery suite as normal, or pick a second color to widen it.
- **Whtz**: a target deck size field appears, defaulting to 100. Enter any value of 100 or greater; there's no upper limit.

### Mobile
The same Tolabow color dropdown and Whtz deck-size field appear inline on the commander step of the build wizard once a Rulebreaker commander is selected. Neither field is required to start a build.

### Manual Deck Builder
Picking a Rulebreaker commander in the Manual Deck Builder applies the same card-pool and land relaxation as a guided/auto build, the Mana Pips/Sources charts reflect the actual off-identity colors present in your deck rather than zeroing them out.

---

## Deck-Size Scaling (Whtz only)

Since Whtz removes the maximum deck size, the ideal counts for lands, ramp, removal, and other categories are scaled up so a 200-card deck isn't stuck running a 100-card deck's worth of lands. The scaling curve grows land percentage smoothly with deck size (not a flat multiplier), so bigger decks get modestly higher land density without becoming land-flooded. This happens automatically. On the web, the Ideal Counts sliders update live as you change the target deck size, and you can still fine-tune any category afterward.

---

## Random / Surprise-Me Builds

Tolabow is excluded from full-random and surprise-me commander pools, since its optional extra-color choice has no one to answer it during a fully automated pick. The other 7 Rulebreaker commanders can still be selected at random.

---

## See Also

- [Build Wizard](build_wizard.md) — Rulebreaker selection in the context of the full build flow
- [Manual Deck Builder](manual_builder.md) — building a Rulebreaker commander's deck card-by-card
- [Smart Land Bases](land_bases.md) — how land count/ratio targets are calculated, including Whtz's deck-size scaling
- [Partner Mechanics](partner_mechanics.md) — pairing a Rulebreaker commander with a Partner or Background
