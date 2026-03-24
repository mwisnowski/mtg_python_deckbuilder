# Owned Cards

Upload your card collection and build decks using only — or preferring — cards you already own.

---

## Overview

The Owned Cards feature lets you upload lists of cards you own. Once uploaded, these lists integrate into the build pipeline so the builder can filter or bias card selection toward your collection.

---

## Uploading Your Library

Go to `/owned` in the web UI to manage your owned card library.

### Supported Formats

| Format | Notes |
|--------|-------|
| `.txt` | One card name per line. Optionally prefix with a count: `4x Sol Ring` or `4 Sol Ring`. |
| `.csv` | Must include at minimum a `name` column. A `count` column is optional. |

Cards are enriched and deduplicated automatically on upload. Near-duplicate names (e.g., different printings) are resolved against the card catalog.

### Multiple Files
You can upload multiple files. All are merged into a single owned library for the session. To replace the library, delete existing files and re-upload.

---

## Build Modes

Select the owned card mode in the **New Deck modal**:

| Mode | Behavior |
|------|----------|
| **No filter** (default) | Owned cards have no special weight; all on-theme cards are eligible. |
| **Prefer owned** | Cards you own are weighted higher in the selection pool. Non-owned cards are still eligible if the pool would otherwise be too thin. |
| **Owned only** | Only cards in your owned library are eligible for selection. Builds may be thinner if your library doesn't cover a theme well. |

---

## Alternatives Panel (Replace)

When using **Replace** in Step 5, toggle **Owned only** in the Alternatives panel to restrict replacement candidates to cards in your library.

---

## Performance

For large libraries (1,000+ cards), enable list virtualization to improve scroll performance in the Owned Library page:

```
WEB_VIRTUALIZE=1
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OWNED_CARDS_DIR` / `CARD_LIBRARY_DIR` | `/app/owned_cards` | Override the directory where owned card files are stored. Mount this volume to persist across container restarts. |
| `WEB_VIRTUALIZE` | `1` | Enable virtualized lists for large owned libraries and Step 5 card grids. |

---

## Headless / CLI

In headless mode, set the owned card mode via JSON config:

```json
{
  "owned_only": true,
  "prefer_owned": false
}
```

Use `"prefer_owned": true` for soft weighting, `"owned_only": true` for hard filtering. The two are mutually exclusive; `owned_only` takes precedence if both are set.
