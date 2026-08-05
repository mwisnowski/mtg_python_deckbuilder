# Manual Deck Builder

Build a Commander deck yourself, one card at a time, instead of running the automated pipeline. Browse the full legal card pool, add and remove cards, and watch a live role-health bar track your progress.

---

## Accessing the Page

Click **Build a New Deck** (sidebar, home page, or the **Build a Deck** page) and choose **Build Manually** from the New Deck modal (the same modal used for the auto-builder and Quick Build). Enter a commander (and optional themes/bracket/budget) just like a normal build.

Toggle the feature with the `ENABLE_MANUAL_BUILDER` environment variable (default: enabled).

---

## The Pool

The left panel shows every card legal for your commander's color identity, sorted by EDHREC popularity by default (a "Sorted by" label above the grid always shows the active sort). Use the controls above the grid to:

| Control | Effect |
|---------|--------|
| **Role** | Filter to Ramp, Removal, Card Draw, Threat, Land, or Other |
| **Sort** | EDHREC Popularity, Theme Match (overlap with your selected themes), Mana Value, Name, or Price |
| **Search** | Filter the pool by card name |

Each card tile shows its image, role, and mana value, plus a **Why this card?** note explaining why it's surfaced (theme matches, EDHREC popularity, new-card status, role fit). Cards priced above your budget ceiling (if set) stay visible with a highlighted border rather than being hidden.

Click **+ Add** on any tile to add it to your deck. Once added, a card is hidden from the pool (it reappears if you remove it), except basic lands and the small set of "any number of cards named X" cards (Relentless Rats, Persistent Petitioners, etc.), which always stay visible.

### Can't find a card?

If a card you want isn't showing up near the top of the default sort, use the **search outside the default pool sort** box below the grid. It searches the same color-identity-legal card set by name, so you can jump straight to a specific card.

---

## Other Good Options

Hover over a pool card for a moment (about 300ms) and an **Other Good Options** section expands with a few alternatives that share the same role and a similar mana value, excluding anything already in your deck. Each alternative has its own **+ Add** button.

---

## Building the Deck

The right panel lists your current deck, grouped by role (Ramp, Removal, Card Draw, Threats, Lands, Other), with a count next to each group. Click **Remove** next to any card to take it back out.

- Cards are singleton (Commander format), so adding a card already in your deck shows an **"Already in deck"** warning instead of a duplicate.
- Basic lands are the exception: add as many copies as you like.

### Land Package

Click **+ Add Land Package** in the deck panel to pre-add a starting land base: basic lands split evenly across your commander's colors (up to your basic-land ideal from the build config) plus the standard staple utility lands (Command Tower, Reliquary Tower, Exotic Orchard, War Room, Ash Barrens, Rogue's Passage) wherever they apply to your deck. Staples already in your deck are skipped; running it again adds another set of basics.

### Role Health Bar

Above the pool and deck panels, a row of pills tracks your deck against target counts for each role (Ramp, Removal, Draw, Lands, Threats):

- **Green**: at or above target
- **Yellow**: close to target (within 2)
- **Red**: short of target

Lands use fixed thresholds instead of a single target: red under 33, yellow 33-35, green 36 and up. Any red pill also shows a short suggestion below the bar (e.g. "You're short on Removal").

### Bracket Compliance

A second row of pills tracks Game Changers, Extra Turns, Mass Land Denial, Nonland Tutors, and Two-Card Combos against your bracket's limits:

- Cards fully banned at your bracket (limit of zero) never appear in the pool or search results at all.
- Cards allowed up to a positive cap (e.g. up to 3 Game Changers at Bracket 3) stay in the pool with a small badge on the tile, and the pill turns yellow or red as you approach or exceed the cap.
- Two-card combos can't be filtered out of the pool (a combo only exists once both cards are in the deck), so the Two-Card Combos pill instead warns you the moment a known combo pair is already present.

These pills update live as you add and remove cards, same as the role health bar.

---

## Saving and Exporting

- **Save Deck** writes the deck to your saved decks list (same as an imported or auto-built deck) and takes you to its deck page, where you can view Suggested Upgrades or run Import Analysis. Saved manual decks show a **Manual** badge in the Finished Decks list. If your deck isn't exactly 100 cards, it still saves, just with a warning.
- **Export CSV** / **Export TXT** download the current in-progress deck list without saving it, useful for a quick backup while you're still deciding.

---

## Editing a Saved Deck

On any deck you own, click **Edit Deck** to reopen it in the Manual Deck Builder with its commander, color identity, bracket, and current card list already loaded. Add and remove cards exactly as you would when building from scratch; clicking **Save Changes** overwrites the original deck file in place (its visibility setting is preserved).

---

## Notes

- The role-health targets (Ramp, Removal, Draw, Lands, Threats) come from the same defaults the auto-builder uses.
- Budget ceilings are a visual flag only; over-budget cards are never filtered out of the pool.
