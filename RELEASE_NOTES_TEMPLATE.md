# MTG Python Deckbuilder ${VERSION}

### Added
- Theme whitelist governance (`config/themes/theme_whitelist.yml`) with normalization, enforced synergies, and synergy cap (5).
- Expanded curated synergy matrix plus PMI-based inferred synergies (data-driven) blended with curated anchors.
- Test: `test_theme_whitelist_and_synergy_cap.py` validates enforced synergy presence and cap compliance.
- PyYAML dependency for governance parsing.

### Changed
- Theme normalization (ETB -> Enter the Battlefield, Self Mill -> Mill, Pillow Fort -> Pillowfort, Reanimator -> Reanimate) applied prior to synergy derivation.
- Synergy output capped to 5 entries per theme (curated > enforced > inferred ordering).

### Fixed
- Removed ultra-rare themes (frequency <=1) except those protected/always included via whitelist.
- Corrected commander eligibility: restricts non-creature legendary permanents. Now only Legendary Creatures (incl. Artifact/Enchantment Creatures), qualifying Legendary Artifact Vehicles/Spacecraft with printed P/T, or any card explicitly stating "can be your commander" are considered. Plain Legendary Enchantments (non-creature), Planeswalkers without the text, and other Legendary Artifacts are excluded.

---