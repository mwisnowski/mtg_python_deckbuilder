# Locks, Replace & Permalinks

Core Step 5 tools for refining, sharing, and restoring deck builds.

---

## Locks

Lock cards to pin them in place across reruns. Locked cards are always kept in the deck regardless of theme changes, pool reshuffles, or bracket adjustments.

### How to Lock
- In Step 5, click the lock icon on any card row. The card is immediately locked and visually marked.
- Alternatively, click the card name to open its detail panel, then toggle the lock there.

### Behavior
- Locked cards persist when you click **Rebuild** (re-runs the build with the same settings).
- Locks are stored in the session and exported to the summary JSON sidecar (`*.summary.json`).
- When restoring a deck via permalink, locks are restored alongside the rest of the build state.
- Locking has no interaction with Must Include/Exclude lists — a locked card and a must-include card are both always present. Avoid locking a card that is also in Must Exclude.

### Unlocking
Click the lock icon again to unlock. The card re-enters the pool on the next rebuild.

---

## Replace

Swap any card in the current deck for an alternative from the same category pool.

### How to Use
1. In Step 5, enable **Replace mode** (toggle at the top of the card list).
2. Click any card to open the **Alternatives panel**.
3. Browse or filter alternatives. Toggle **Owned only** to restrict candidates to your uploaded library.
4. Click a card in the alternatives panel to swap it in. The replaced card moves out of the deck.
5. The replacement is locked automatically to prevent it from being displaced on the next rebuild.

### Notes
- Replace respects category boundaries: land replacements come from the land pool, creature replacements from the creature pool, etc.
- Combo-paired cards (flagged in the Combos section of Step 5) will surface a warning if you replace one half of a known combo pair.
- Replace history is included in the summary JSON.

---

## Permalinks

Permalinks encode the full build state into a shareable URL so you or anyone else can restore that exact deck later.

### What a Permalink Encodes
- Commander (and partner/background if applicable)
- Primary, secondary, and tertiary themes
- Bracket selection
- Locked cards
- Must Include / Must Exclude lists
- Budget ceiling (if set)
- Build name (if set)

### Creating a Permalink
- In Step 5, click **Copy Permalink**.
- From the Finished Decks page, click the permalink icon on any completed build.

### Restoring from a Permalink
1. Click **Open Permalink…** on the homepage or Build a Deck modal.
2. Paste the permalink URL or token.
3. The builder restores the commander, themes, bracket, locks, and lists, then lands in Step 5 with the saved state ready to rebuild or export.

### Sharing
Permalink URLs are self-contained — no server state is required. Anyone with the URL can restore the build as long as the card data in the application is compatible (same catalog version or later).

---

## Combos (Step 5 Panel)

The Combos section in Step 5 lists known two-card combo pairs detected in the current deck. This is informational — no cards are added or removed automatically. Use locks to preserve combo pairs across rebuilds, or add individual combo cards to Must Include if you want them guaranteed.

---

## FAQ

**Can I share a permalink with someone who has a different card catalog version?**
Permalinks encode names and settings, not card data. As long as the commander and theme names are still valid in the recipient's catalog, the build will restore correctly. Cards that no longer exist in the catalog will be skipped.

**Are locks preserved when I export to CSV or TXT?**
Locks are session metadata and are stored in the summary JSON sidecar (`*.summary.json`) alongside the export. The CSV/TXT card list itself does not include lock state.

**What if I accidentally replace a card I wanted to keep?**
Replaced cards move out of the deck immediately. If you haven't rebuilt, you can replace again to bring a similar card back in. For guaranteed cards, use Must Include so they aren't displaced by Replace or Rebuild.

---

## See Also

- [Build Wizard](build_wizard.md) — locks and replace in the context of the Step 5 review
- [Include / Exclude Lists](include_exclude.md) — guarantee specific cards before the build runs instead of after
- [Owned Cards](owned_cards.md) — restrict Replace alternatives to your owned card library
