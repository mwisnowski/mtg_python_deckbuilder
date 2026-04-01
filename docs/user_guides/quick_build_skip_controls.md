# Quick Build & Skip Controls

Speed up the build workflow with one-click automation or granular per-stage skipping.

---

## Overview

The Step-by-Step builder presents each stage for your approval before moving on. Two tools let you bypass this:

- **Quick Build** — one click from the New Deck modal runs all stages automatically and lands in Step 5 with a complete deck ready to review.
- **Skip Controls** — per-stage toggles in Step 5 let you auto-accept any combination of the 21 granular build stages while still stepping through the others manually.

---

## Quick Build

Click **Quick Build** in the New Deck modal (next to the standard **Build** button) to run the full workflow without any approval prompts. Progress is shown in real time as each stage completes.

Use Quick Build when:
- You want to iterate quickly and refine in Step 5 rather than stepping through each stage.
- You are running Batch Build and want all variants generated without interruption.
- You already know what you want and just need a starting point to lock and tweak.

Quick Build respects all normal build settings (bracket, budget, include/exclude, owned filters) and honors any locks from a previous build.

---

## Stage Order

The default build order (`WEB_STAGE_ORDER=new`) runs creatures and spells before lands. This allows the builder to see what pip costs are needed before finalizing the mana base.

| Mode | Order |
|------|-------|
| `new` (default) | Multi-Copy → Creatures → Spells → Lands → Theme Fill → Adjustments |
| `legacy` | Multi-Copy → Lands → Creatures → Spells → Theme Fill → Adjustments |

Set `WEB_STAGE_ORDER=legacy` to restore the original lands-first order.

---

## Skip Controls

In Step 5, the **Skip Controls** section shows 21 per-stage toggles. Enabling a toggle for a stage causes that stage to be auto-accepted on the next build (or rebuild), skipping the approval prompt.

### Land Stages
| Stage | What it auto-accepts |
|-------|---------------------|
| Basic land fill | Automatically approve the basic land distribution |
| Nonbasic fill | Automatically approve nonbasic land selection |
| Land count adjustment | Automatically approve the final land count tuning |

### Creature Stages
| Stage | What it auto-accepts |
|-------|---------------------|
| Early-game creatures | Auto-approve 1–2 CMC creatures |
| Mid-game creatures | Auto-approve 3–4 CMC creatures |
| Late-game creatures | Auto-approve 5+ CMC creatures |
| Synergy creatures | Auto-approve creatures selected for synergy with themes |
| Creature theme fill | Auto-approve remaining creature theme fill |

### Spell Stages
| Stage | What it auto-accepts |
|-------|---------------------|
| Ramp | Auto-approve ramp spells |
| Removal | Auto-approve single-target removal |
| Board wipes | Auto-approve mass removal |
| Card draw | Auto-approve draw spells |
| Protection | Auto-approve protection/counterspell package |
| Spell theme fill | Auto-approve remaining spell theme fill |

Additional adjustment and fill stages are also individually toggleable in the UI.

---

## Combining Quick Build and Skip Controls

You can use skip controls as a "remembered preference" that persists for the session:

- Enable skip controls for stages you never want to review (e.g., basic land fill, ramp).
- Use **Build** (not Quick Build) to still step through the remaining stages manually.

Quick Build always auto-accepts all stages regardless of skip control settings — it is the equivalent of all 21 toggles enabled at once.

---

## Session Persistence

Skip control settings are stored in the browser session. They persist across multiple builds in the same browser tab but reset when the session ends (tab close, browser restart, or session timeout).

---

## Ideal Counts UI

The stage tuning interface (where you set target counts for each category before a stage runs) uses range sliders by default. Switch to numeric text inputs with:

```
WEB_IDEALS_UI=input
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `WEB_STAGE_ORDER` | `new` | Build stage execution order: `new` (creatures→spells→lands) or `legacy` (lands→creatures→spells). |
| `WEB_IDEALS_UI` | `slider` | Stage tuning interface: `slider` (range inputs) or `input` (text boxes). |

---

## See Also

- [Build Wizard](build_wizard.md) — full walkthrough covering Quick Build and Skip Controls in context
- [Batch Build & Compare](batch_build_compare.md) — run multiple full builds in one session using Quick Build
