---
name: Rulebreaker Card Report
about: Report a new or unrecognized "Rulebreaker" commander (a card that grants a
  unique, named deckbuilding rules exception) so its rule can be added to the registry.
title: 'Rulebreaker: '
labels: enhancement, rulebreaker
assignees: ''

---

### Card Name
_Exact printed name of the card._

### Set / Collector Number
_If known (e.g. "MBC #123"). Leave blank if unreleased/unknown._

### Detected By
- [ ] Automated tagging pass (flagged during `run_tagging()` as an unrecognized candidate)
- [ ] Manual report (found while browsing spoilers/previews)

### Oracle Text
_Paste the card's full oracle text verbatim, including the deckbuilding-rule-exception line._

```
(paste oracle text here)
```

### Suggested Rule Type
_Which existing `rule_type` (see `RULEBREAKER_ARCHETYPES` in `code/deck_builder/builder_constants.py`) does this match, if any?_

- [ ] `any_land` — allows any land regardless of color identity
- [ ] `type_any_color` — allows a card type/subtype of any color identity
- [ ] `type_cmc_any_color` — allows a card type/subtype + mana value threshold of any color identity
- [ ] `instant_sorcery_extra_color` — allows Instant/Sorcery of one user-chosen extra color
- [ ] `no_max_deck_size` — removes the maximum deck size cap
- [ ] Other / new pattern not covered by the above (describe below)

### Proposed Registry Entry
_Best-effort draft entry for `RULEBREAKER_ARCHETYPES`, even if incomplete._

```python
'card_name_slug': {
    'id': 'card_name_slug',
    'name': 'Card Name',
    'color_identity': [],
    'rule_type': '',
    'params': {},
    'basic_lands_scope': 'any',  # 'any' | 'identity_plus_extra_color' | 'strict'
    'no_max_deck_size': False,
    'requires_user_input': False,
},
```

### Additional Notes
_Anything else we should know? Links to spoilers/previews are welcome._
