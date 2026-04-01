# Partner Mechanics

Build with dual-commander configurations: Partners, Partner With, Doctor/Doctor's Companion, and Backgrounds.

---

## Overview

Partner mechanics allow you to pair two commanders into a single deck, combining their color identities and theme tags. The builder auto-detects which partner type applies to a selected commander and adjusts Step 2 accordingly.

Enable with `ENABLE_PARTNER_MECHANICS=1` (default: on in Docker Compose; disabled by default in headless/CLI).

---

## Partner Types

| Type | How it works |
|------|-------------|
| **Partner** | Both commanders have the Partner keyword. Any two Partner commanders can be paired. |
| **Partner With** | One commander specifically names their partner (e.g., "Partner with Cazur"). The canonical partner is pre-filled; you can opt out and swap. |
| **Doctor / Doctor's Companion** | Doctors list legal companions and vice versa. Role labels are shown beside each option. |
| **Background** | Choose a Background enchantment instead of a second commander. The Background picker replaces the partner selector when applicable. |

---

## Selecting a Partner in the Web UI

1. In the **New Deck modal** or **Step 2**, select a commander that supports a partner type.
2. The appropriate partner input appears automatically:
   - A filtered partner dropdown (Partner)
   - A pre-filled name with an opt-out chip (Partner With, Doctor)
   - A Background dropdown (Background)
3. For **Partner With** and **Doctor** pairings, an opt-out chip lets you keep the canonical suggestion or clear it and choose a different partner.
4. Previews, color identity warnings, and theme chips update in real time as you make partner selections.

### Partner Suggestions
With `ENABLE_PARTNER_SUGGESTIONS=1`, ranked suggestion chips appear beside the partner selector. These are backed by the partner synergy analytics dataset (`config/analytics/partner_synergy.json`, auto-generated when missing). Selecting a chip populates the partner field.

---

## Color Identity

The combined color identity of both commanders is used for all card pool filtering. Cards outside the combined identity are excluded, just as they would be for a single commander.

---

## Theme Tags

Theme tags from both commanders are merged. This means a partner pair may unlock themes neither commander could access individually.

---

## Headless / CLI

Supply partner settings in the JSON config or as CLI flags:

```json
{
  "commander": "Halana, Kessig Ranger",
  "secondary_commander": "Alena, Kessig Trapper",
  "enable_partner_mechanics": true
}
```

CLI flags:
```
--secondary-commander "Alena, Kessig Trapper" --enable-partner-mechanics true
```

For Background pairings, use `background` instead of `secondary_commander`:
```json
{
  "commander": "Raised by Giants",
  "background": "Acolyte of Bahamut",
  "enable_partner_mechanics": true
}
```

`secondary_commander` and `background` are mutually exclusive. `background` takes precedence if both are set.

### Dry Run
Add `--dry-run` to the CLI command to echo the resolved pairing (names, color identity, partner mode) without running a full build:

```powershell
python code/main.py --dry-run --secondary-commander "Alena, Kessig Trapper" --enable-partner-mechanics true
```

---

## Headless JSON Export

Exported configs (`HEADLESS_EXPORT_JSON=1`) include the resolved partner fields:
- `secondary_commander` or `background`
- `combined_color_identity`
- `partner_mode` (partner | partner_with | doctor | background)

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENABLE_PARTNER_MECHANICS` | `0` | Unlock partner/background inputs in the web builder and headless runner. |
| `ENABLE_PARTNER_SUGGESTIONS` | `0` | Show ranked partner suggestion chips in the web builder. |
| `PARTNER_SUGGESTIONS_DATASET` | _(auto)_ | Override path to `partner_synergy.json` inside the container. |

---

## See Also

- [Build Wizard](build_wizard.md) — partner selection in the context of the full build flow
- [Bracket Compliance](bracket_compliance.md) — bracket implications when a commander is on the Game Changers list
- [Theme Browser](theme_browser.md) — find themes compatible with both commanders' color identity
