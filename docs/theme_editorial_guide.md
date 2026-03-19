# Theme Editorial Workflow Guide

**Version**: 1.0.0  
**Last Updated**: March 18, 2026  
**Audience**: Contributors, maintainers, theme curators

## Overview

This guide documents the theme editorial quality system introduced in Roadmap 12 (M1-M4). It explains how theme quality is measured, how to curate high-quality themes, and how to use the linter to maintain catalog standards.

## Quality Scoring System

### Scoring Components

Theme editorial quality is measured using an **Enhanced Quality Score** (0.0-1.0 scale) with four weighted components:

| Component | Weight | Description |
|-----------|--------|-------------|
| **Card Count** | 30 points | Number of example cards (target: 8+) |
| **Uniqueness** | 40 points | Ratio of cards appearing in <25% of themes |
| **Description** | 20 points | Manual (20) > Rule-based (10) > Generic (0) |
| **Curation** | 10 points | Presence of curated synergies |

**Total**: 100 points → normalized to 0.0-1.0 scale

### Quality Tiers

Themes are classified into four quality tiers based on their score:

| Tier | Score Range | Description | Priority |
|------|-------------|-------------|----------|
| **Excellent** | ≥0.75 | 8+ unique cards, manual description, well-curated | ✅ Maintain |
| **Good** | 0.60-0.74 | Strong card selection, rule-based description | ✅ Monitor |
| **Fair** | 0.40-0.59 | Adequate cards, may have some generic cards or description | ⚠️ Improve |
| **Poor** | <0.40 | Few cards, generic description, high duplication | 🔴 Urgent |

### Uniqueness vs Duplication

- **Uniqueness Ratio**: Fraction of example cards appearing in <25% of themes (higher is better)
- **Duplication Ratio**: Fraction of example cards appearing in >40% of themes (lower is better)

**Example**:
- A theme with `["Sol Ring", "Command Tower", "Unique Card A", "Unique Card B"]` might have:
  - Uniqueness: 0.50 (2/4 cards are unique)
  - Duplication: 0.50 (2/4 cards are generic staples)

## Curating High-Quality Themes

### Best Practices for Example Cards

#### DO ✅
- **Use 8+ example cards** - Maximizes card count score (30 points)
- **Select unique, theme-specific cards** - Boosts uniqueness score (40 points)
- **Avoid generic staples** - Focus on cards that actually exemplify the theme
- **Include archetype-specific cards** - Not just "good cards in these colors"
- **Prioritize cards that demonstrate the strategy** - Help players understand the theme

#### DON'T ❌
- **Include generic ramp** - `Sol Ring`, `Arcane Signet`, `Commander's Sphere`
- **Include generic card draw** - `Rhystic Study`, `Esper Sentinel` (unless theme-relevant)
- **Include generic removal** - `Swords to Plowshares`, `Cyclonic Rift` (unless theme-relevant)
- **Use <5 example cards** - Severely impacts card count score
- **Copy example cards from similar themes** - Reduces uniqueness, increases duplication

#### Example Comparison

**Poor Quality** (Score: 0.35, Tier: Poor):
```yaml
display_name: Voltron Auras
example_cards:
  - Sol Ring
  - Lightning Greaves
  - Swiftfoot Boots
  - Sword of Feast and Famine
description_source: generic
```
*Issues*: Generic cards, only 4 cards, generic description

**Excellent Quality** (Score: 0.82, Tier: Excellent):
```yaml
display_name: Voltron Auras
example_cards:
  - All That Glitters
  - Ethereal Armor
  - Ancestral Mask
  - Bess, Soul Nourisher
  - Sigil of the Empty Throne
  - Mesa Enchantress
  - Three Dreams
  - Spirit Mantle
description_source: manual
description: "Enchants a single creature with multiple Auras to create a powerful, evasive threat while drawing cards and generating value from enchantress effects."
popularity_pinned: false
```
*Strengths*: 8 unique aura-specific cards, manual description, clear strategy

### Description Quality

#### Description Sources

- **`manual`**: Hand-written by a curator (20 points)
  - Clear, concise, strategic explanation
  - Explains *how* the theme wins, not just what it does
  - Example: "Reanimates high-cost creatures from the graveyard early via discard/mill effects, bypassing mana costs to establish board dominance."

- **`rule`**: Generated from external heuristics (10 points)
  - Template-based with theme-specific keywords
  - Example: "Leverages the graveyard for recursion and value."

- **`generic`**: Fallback template (0 points)
  - Minimal information, no strategic insight
  - Example: "A theme focused on [theme name] strategies."
  - ⚠️ **Should be upgraded to rule or manual**

#### Writing Manual Descriptions

Good manual descriptions answer:
1. **What** does the theme do? (mechanics)
2. **How** does it win? (strategy)
3. **Why** is it effective? (synergies/payoffs)

**Template**: `[Action] [Key Cards/Mechanics] to [Strategic Goal] via [Synergies/Payoffs].`

**Example**:
- Theme: Aristocrats
- Description: "Sacrifices creatures for value via death triggers, then recurs them to repeat the process while generating tokens, card advantage, and direct damage."

### Popularity Pinning

Use `popularity_pinned: true` to prevent automatic popularity_bucket updates when you've manually curated the bucket:

```yaml
popularity_bucket: Common
popularity_pinned: true  # Prevents overwriting during rebuilds
```

**When to pin**:
- Manual research shows different bucket than analytics
- Theme popularity has shifted but analytics lag
- Theme is intentionally promoted/demoted for editorial reasons

**When NOT to pin**:
- Default/initial backfill state
- No strong reason to override analytics

## Using the Linter

### Running the Linter

The linter is integrated into `validate_theme_catalog.py`:

```bash
# Basic quality checks (M1)
python code/scripts/validate_theme_catalog.py --check-quality

# Full linter with M4 rules
python code/scripts/validate_theme_catalog.py --check-quality --lint

# Customize thresholds
python code/scripts/validate_theme_catalog.py --lint \
  --lint-duplication-threshold 0.4 \
  --lint-quality-threshold 0.5
```

### Linter Rules

| Rule | Severity | Threshold | Description |
|------|----------|-----------|-------------|
| **Missing description_source** | ERROR | N/A | Theme has description but no source metadata |
| **Generic description** | WARNING | N/A | Description_source is "generic" |
| **Missing popularity_pinned** | ERROR | N/A | popularity_pinned=True but no bucket set |
| **High duplication** | WARNING | >0.5 | >50% of example cards are generic staples |
| **Low quality score** | WARNING | <0.5 | Quality score below threshold |

### Interpreting Linter Output

#### Example Output

```
VALIDATION FAILED:
 - [QUALITY] voltron-auras.yml has generic description_source - consider upgrading to rule-based or manual
 - [LINT-WARNING] voltron-auras.yml has high duplication ratio (0.62 > 0.5). Generic cards: Sol Ring, Lightning Greaves, Swiftfoot Boots
 - [LINT-WARNING] voltron-auras.yml has low quality score (0.38 < 0.5, tier=Poor). Suggestions: Add more example cards (target: 8+); Upgrade to manual or rule-based description; Replace generic staples with unique cards
```

#### Recommended Actions

1. **High Duplication**:
   - Review listed generic cards
   - Replace with theme-specific alternatives
   - Example: Replace `Sol Ring` with `All That Glitters` for Voltron Auras

2. **Low Quality Score**:
   - Follow suggestions in order: cards first, then description, then deduplicate
   - **Add more cards** (fastest improvement)
   - **Upgrade description** (if you understand the theme)
   - **Replace generic cards** (if cards are already adequate)

3. **Generic Description**:
   - Write a manual description following the template
   - Or wait for rule-based generation improvements

## Workflow Examples

### Example 1: Improving a Fair-Quality Theme

**Starting Point**:
```yaml
display_name: Graveyard Value
example_cards:
  - Command Tower
  - Sol Ring
  - Eternal Witness
  - Greenwarden of Murasa
  - Reanimate
description_source: generic
description: "A theme focused on graveyard strategies."
```
**Score**: 0.45 (Fair)

**Step 1: Add Example Cards** (target: 8+)
```yaml
example_cards:
  - Command Tower           # Keep for now
  - Sol Ring                # Keep for now
  - Eternal Witness
  - Greenwarden of Murasa
  - Reanimate
  - Living Death            # Added
  - Victimize               # Added
  - Animate Dead            # Added
  - Muldrotha, the Gravetide # Added
```
**Score**: 0.53 (Fair → Good threshold)

**Step 2: Upgrade Description**
```yaml
description_source: manual
description: "Fills the graveyard via self-mill and discard, then recurs high-value creatures and spells for repeated use, generating card advantage and overwhelming opponents with recursive threats."
```
**Score**: 0.63 (Good)

**Step 3: Replace Generic Cards**
```yaml
example_cards:
  - World Shaper            # Replace Command Tower
  - Crucible of Worlds      # Replace Sol Ring
  - Eternal Witness
  - Greenwarden of Murasa
  - Reanimate
  - Living Death
  - Victimize
  - Animate Dead
  - Muldrotha, the Gravetide
```
**Score**: 0.78 (Excellent!)

### Example 2: Maintaining Excellent Quality

**Theme**: Aristocrats  
**Score**: 0.82 (Excellent)

**Maintenance Checklist**:
- ✅ 10 unique example cards
- ✅ Manual description matches current strategy
- ✅ Popularity bucket accurate (review quarterly)
- ✅ No generic staples in example list
- ✅ Synergies reflect current meta cards

**Action**: Pin popularity if manually verified:
```yaml
popularity_bucket: Very Common
popularity_pinned: true
```

## Common Pitfalls

### ❌ Pitfall 1: "Good Cards" Aren't Always Theme Cards

**Bad**:
```yaml
display_name: Enchantress
example_cards:
  - Rhystic Study  # Good card, but not enchantress-specific
  - Sol Ring       # Generic ramp
  - Swords to Plowshares  # Generic removal
```

**Good**:
```yaml
display_name: Enchantress
example_cards:
  - Enchantress's Presence
  - Setessan Champion
  - Mesa Enchantress
  - Argothian Enchantress
```

### ❌ Pitfall 2: Copying Example Cards

Themes with high overlap hurt the catalog's uniqueness metrics:

**Bad** (Voltron + Equipment themes share 6/8 cards):
```yaml
# voltron-equipment.yml
example_cards: [Sword of Fire and Ice, Batterskull, Colossus Hammer, Lightning Greaves, ...]

# voltron-auras.yml  
example_cards: [Sword of Fire and Ice, Batterskull, Colossus Hammer, Lightning Greaves, ...]
```

**Good** (Distinct card pools):
```yaml
# voltron-equipment.yml
example_cards: [Sword of Fire and Ice, Batterskull, Colossus Hammer, Sigarda's Aid, ...]

# voltron-auras.yml
example_cards: [All That Glitters, Ethereal Armor, Ancestral Mask, Estrid, the Masked, ...]
```

### ❌ Pitfall 3: Ignoring Linter Warnings

Linter warnings accumulate over time. Address them during regular maintenance:

**Quarterly Workflow**:
1. Run `--lint --lint-quality-threshold 0.4`
2. Identify Poor/Fair themes (<0.5 score)
3. Improve 5-10 themes per session
4. Commit improvements incrementally

## Quality Metrics Dashboard

Track catalog health with these statistics:

```bash
# Generate quality report (future tool)
python code/scripts/generate_quality_report.py

# Expected Output:
# Total Themes: 740
# Excellent: 220 (30%)
# Good:      300 (40%)
# Fair:      180 (24%)
# Poor:       40 ( 6%)
# Average Uniqueness: 0.62
# Average Duplication: 0.28
```

**Health Benchmarks**:
- **Excellent + Good**: >60%
- **Poor**: <10%
- **Average Uniqueness**: >0.50
- **Average Duplication**: <0.35

## Resources

- **Heuristics Config**: `config/themes/editorial_heuristics.yml`
- **Validation Script**: `code/scripts/validate_theme_catalog.py`
- **Backfill Script**: `code/scripts/backfill_editorial_fields.py`
- **Service Implementation**: `code/web/services/theme_editorial_service.py`
- **Tests**: `code/tests/test_theme_editorial_service.py`, `code/tests/test_theme_linter.py`

## FAQ

### Q: What's the minimum acceptable quality score?
**A**: Fair (0.40) is acceptable for niche themes. Aim for Good (0.60+) for common themes.

### Q: Should I remove all generic staples?
**A**: Not necessarily. If a card like `Sol Ring` is *genuinely* theme-relevant (e.g., "Colorless Matters"), include it. But avoid generic ramp/removal that appears in 50%+ of decks.

### Q: How do I handle themes with few unique cards?
**A**: Focus on description quality (manual) and curate the best available examples. Some themes (e.g., "Mulligan Matters") inherently have limited card pools.

### Q: Can I batch-fix themes?
**A**: Yes, but commit incrementally and test after each batch to avoid introducing errors. Use `--lint` to validate before committing.

### Q: What if the linter disagrees with my curation?
**A**: Linter warnings are suggestions, not hard requirements. Use judgment for niche/experimental themes, but document reasoning in the theme's `notes` field.

---

**Maintained by**: MTG Python Deckbuilder Contributors  
**Feedback**: Open an issue on GitHub with `[editorial]` prefix
