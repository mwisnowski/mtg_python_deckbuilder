# Deck Import & Analysis

Import an existing deck list and get an instant breakdown of its role coverage, theme fit, CMC curve, and duplicate cards — plus fill suggestions if the deck is under 100 cards.

---

## Accessing the Page

From the **Finished Decks** page, click **Import a Deck**. You can also navigate directly to `/decks/import`.

---

## Supported Formats

Paste or upload a plain-text deck list from any of the following sources:

| Source | Notes |
|--------|-------|
| **Moxfield** | Copy from Moxfield's export or deck view |
| **Archidekt** | Copy from Archidekt's text export |
| **TappedOut** | Copy from TappedOut's text export |
| **EDHREC** | Copy from an EDHREC deck list |
| **Native export** | CSV or TXT files exported from this app |

Lines starting with `//` or `#` are treated as comments. Section headers like `Commander`, `Lands`, `Creatures` are recognized and skipped automatically.

---

## Import Form

| Field | Description |
|-------|-------------|
| **Upload .txt file** | Upload a plain-text file (max 512 KB) |
| **Paste deck list** | Paste a deck list directly into the text area |
| **Commander** | Optional — overrides auto-detection if the list does not have a clear commander |
| **Themes** | Optional — hint the analysis with themes you want to emphasize; supports autocomplete |

The theme field shows random placeholder examples (3 themes, at most one Kindred/Tribal) on each page load to illustrate the format.

---

## Analysis Panels

After submitting, the analysis page shows several panels:

### Deck Overview
Card count, commander (if detected), color identity, and a basic legality check.

### Role Coverage
A breakdown of how many cards fill each functional role (Ramp, Card Draw, Removal, Board Wipes, Protection, Creatures, Lands, Other). Roles that appear fewer times than expected are flagged as shortfalls.

### CMC Curve
A bar chart showing the distribution of mana costs across non-land cards.

### Cards by Type
Card counts by type (Creature, Instant, Sorcery, Enchantment, Artifact, Planeswalker, Land). For decks with a significant creature base, creature subtypes with 5 or more creatures are shown as inline pills below the Creature row.

### Themes
All detected themes are shown as collapsible rows with:
- **Manual** badge — themes you specified on the form
- **Commander** badge — themes inferred from the commander's identity
- Card count within the theme
- Top 10 cards by EDHRec rank

#### Editing Themes
Click **Edit themes** on the Themes panel to open the correction form. It pre-fills the current themes, supports autocomplete, and re-runs detection when submitted. Use this to add themes you forgot or remove ones that do not fit the deck's direction.

#### Kindred Auto-Detection
If 15 or more non-land creatures share a creature subtype, the matching `X Kindred` or `X Tribal` theme is automatically injected as a high-priority candidate — even if you did not enter it on the form.

---

## Duplicate Cards

If the imported list contains duplicate card names (beyond intentional multi-copy cards), each duplicate is shown with its own lazy-loaded replacement panel. Each panel offers a tiered pool of alternatives (matched by type and functional role) as radio buttons. Select a replacement and click **Replace** to swap the duplicate out.

---

## Fill Suggestions

If the deck has fewer than 100 cards after duplicate resolution, a **Fill Suggestions** section appears. Suggestions are organized into three independent groups:

| Group | What it finds |
|-------|---------------|
| **Role Shortfalls** | Cards that address one or more roles your deck is light on |
| **Theme Fit** | Cards with strong overlap against your detected themes |
| **General Synergy** | Broadly useful cards in your color identity that improve the deck |

Each suggestion shows:
- Card name, CMC, price, and EDHRec rank
- **Teal role pills** — roles this card covers that address a shortfall in your deck
- **Muted role pills** — other roles the card covers

### Scoring
Cards within each group are scored and sorted highest-first:

| Factor | Weight |
|--------|--------|
| Theme tag match | +3 pts per matching theme |
| Shortfall role coverage | +2.5 pts per shortfall role covered |
| Other staple role coverage | +1 pt per other role covered |
| EDHRec popularity | `+1 ÷ log₁₀(rank + 10)` |

Click **Add** next to any suggestion to add it to the deck.

---

## Saving the Deck

Once you are happy with the deck, click **Save**. The deck is written to `deck_files/` in CSV, TXT, and JSON summary format, the same as any deck built with the wizard. It will appear in your **Finished Decks** list and is available for Potential Upgrades analysis.

---

## See Also

- [Build Wizard](build_wizard.md) — building a new deck from scratch
- [Potential Upgrades](suggested_upgrades.md) — find new cards and swap targets for a saved deck
- [Theme Browser](theme_browser.md) — explore available themes and their synergy cards
- [Locks, Replace & Permalinks](locks_replace_permalinks.md) — lock cards before or after import
