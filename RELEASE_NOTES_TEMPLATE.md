# MTG Python Deckbuilder ${VERSION}

## Summary
- Restored setup filtering to exclude Acorn and Heart promotional security stamps so Commander card pools stay format-legal.
- Added a regression test that locks the security stamp filtering behavior in place.

## Added
- Regression test covering security-stamp filtering during setup to guard against future case-sensitivity regressions.

## Fixed
- Setup filtering now applies security-stamp exclusions case-insensitively, preventing Acorn/Heart promo cards from entering Commander pools.