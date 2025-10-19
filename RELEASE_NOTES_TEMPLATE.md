# MTG Python Deckbuilder ${VERSION}

### Summary
Major infrastructure upgrade: migrated to Parquet data format with comprehensive performance improvements, combo tag support, simplified data management, and instant setup via GitHub downloads.

### What's New
- **Instant Setup** - Download pre-tagged card database from GitHub instead of 15-20 minute initial build
- **Parquet Migration** - Unified `all_cards.parquet` replaces multiple CSV files for faster, more efficient card storage
- **Combo Tags** - 226 cards now tagged with combo-enabling abilities for better synergy detection
- **Parallel Tagging** - Optional 4.2x speedup for card tagging (22s → 5.2s)
- **Automatic Deduplication** - No more duplicate card printings cluttering your deck options
- **Built-in Commander Filtering** - Instant identification of 2,751 commanders and 31 backgrounds

### Improvements
- **First-Run Experience** - Auto-downloads pre-tagged data on first run (seconds vs. 15-20 minutes)
- **Faster Startup** - Binary columnar format loads significantly faster than text parsing
- **Smaller File Sizes** - Single Parquet file is more compact than multiple CSVs
- **Better Data Quality** - Automatic validation, deduplication, and type checking
- **Cleaner Organization** - Single source of truth for all 29,857 cards
- **Web Performance** - Card browser, commander catalog, and owned cards all benefit from faster data access
- **Weekly Updates** - Pre-tagged data refreshed weekly via GitHub Actions

### For Users
Everything works the same or better! Main visible differences:
- **First-time users**: Setup completes in seconds (auto-downloads pre-tagged data)
- Faster load times and data operations
- Better card recommendations with combo tag support
- More reliable data handling
- Web UI includes manual "Download from GitHub" button for instant refresh

### Technical Details
- Data stored in `card_files/processed/all_cards.parquet`
- Boolean flags (`isCommander`, `isBackground`) replace separate CSV files
- CLI execution: `python -m code.main`
- Headless execution: `python -m code.headless_runner --config <path>`
- GitHub Actions and Docker builds updated for Parquet workflow
