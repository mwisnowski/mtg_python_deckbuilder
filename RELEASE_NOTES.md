# MTG Python Deckbuilder v1.1.0 Release Notes

## Highlights
- Headless mode via submenu in the main menu (auto-runs single config; lists multiple as "Commander - Theme1, Theme2, Theme3"; `deck.json` shows as "Default")
- Config precedence: CLI > env > JSON > defaults; honors `ideal_counts` in JSON
- Exports: CSV/TXT always; JSON run-config only for interactive runs (headless skips it)
- Docs simplified: concise README and Docker guide; PowerShell examples included

## Docker
- Single service with persistent volumes:
  - /app/deck_files
  - /app/logs
  - /app/csv_files
  - Optional: /app/config for JSON configs

### Quick Start (PowerShell)
```powershell
# From Docker Hub
docker run -it --rm `
  -v "${PWD}/deck_files:/app/deck_files" `
  -v "${PWD}/logs:/app/logs" `
  -v "${PWD}/csv_files:/app/csv_files" `
  mwisnowski/mtg-python-deckbuilder:latest

# From source with Compose
docker compose build
docker compose run --rm mtg-deckbuilder

# Headless (optional)
docker compose run --rm -e DECK_MODE=headless mtg-deckbuilder
# With JSON config
docker compose run --rm -e DECK_MODE=headless -e DECK_CONFIG=/app/config/deck.json mtg-deckbuilder
```

## Changes
- Added headless runner and headless submenu
- Suppressed JSON run-config export for headless runs
- `ideal_counts` in JSON now honored by prompts; only `fetch_count` tracked for lands
- Documentation trimmed and updated; added sample config with ideal_counts

### Tagging updates
- New: Discard Matters theme – detects your discard effects and triggers; includes Madness and Blood creators; Loot/Connive/Cycling/Blood also add Discard Matters.
- New taggers:
  - Freerunning → adds Freerunning and Cost Reduction.
  - Craft → adds Transform; conditionally Artifacts Matter, Exile Matters, Graveyard Matters.
  - Spree → adds Modal and Cost Scaling.
  - Explore/Map → adds Card Selection; Explore may add +1/+1 Counters; Map adds Tokens Matter.
  - Rad counters → adds Rad Counters.
- Exile Matters expanded to cover Warp and Time Counters/Time Travel/Vanishing.
- Energy enriched to also tag Resource Engine.
- Eldrazi Spawn/Scion creators now tag Aristocrats and Ramp (replacing prior Sacrifice Fodder mapping).

## Known Issues
- First run downloads card data (takes a few minutes)
- Use `docker compose run --rm` (not `up`) for interactive sessions
- Ensure volumes are mounted to persist files outside the container

---

# MTG Python Deckbuilder v1.0.0 Release Notes

## 🎉 Initial Release

This is the first stable release of the MTG Python Deckbuilder - a comprehensive command-line tool for building and analyzing Magic: The Gathering Commander/EDH decks.

## 🚀 Features

### Core Functionality
- **Deck Building**: Create and manage Commander/EDH decks with intelligent card suggestions
- **Theme Detection**: Automatically identify and suggest cards based on deck themes and strategies
- **Color Identity Support**: Filter cards based on Commander color identity rules
- **CSV File Management**: Efficient storage and retrieval of card data
- **Card Database**: Comprehensive MTG card database with regular updates
- **Instant Export**: Completed deck lists are automatically displayed for easy copy/paste to online deck builders like Moxfield

### Setup & Management
- **Initial Setup**: Automated download and processing of MTG card data
- **CSV File Tagging**: Automatically tag cards with themes and strategies
- **Commander Validation**: Verify commander legality and format compliance

### Planned Features
- **Price Checking**: From the initial unpolished build I have plans to leverage Scrython for price information (using cheapest print)
- **Deck Value**: From the price checking, there's plans to track the deck value, assign a max deck value, and a max per card value
- **Non-Singleton Cards**: Also from an unpolished build there's remnants for adding and tracking cards you can have multiple copies of (i.e. Nazgul or Hare Apparent) and use these as a "Hidden" theme
- **Further Tag Refinment**: I'm sure there's some missing themes or mis tags, there's honestly far too many cards for me to want to read through and make sure everything is correct, but this will be an evolving project

## 🐳 Docker Support

### Easy Deployment
- **Cross-platform**: Works on Windows, macOS, and Linux
- **No Python Required**: Run without installing Python locally
- **File Persistence**: Your decks and data persist between container runs
- **Interactive Terminal**: Full menu and keyboard interaction support

### Quick Start
```bash
# Linux/macOS
./quick-start.sh

# Windows PowerShell
.\run-docker.ps1 compose
```

## 📦 Installation Options

### Option 1: Docker Hub (Easiest)
```bash
# Create a directory for your decks
mkdir mtg-decks && cd mtg-decks

# Run directly from Docker Hub
docker run -it --rm \
  -v "$(pwd)/deck_files":/app/deck_files \
  -v "$(pwd)/logs":/app/logs \
  -v "$(pwd)/csv_files":/app/csv_files \
  mwisnowski/mtg-python-deckbuilder:latest
```

**Windows Docker Desktop Users**: See `WINDOWS_DOCKER_GUIDE.md` for detailed Windows-specific instructions including GUI setup.

### Option 2: Docker from Source (Recommended for Development)
1. Clone the repository
2. Ensure Docker is installed
3. Run `./quick-start.sh` (Linux/macOS) or `.\run-docker.ps1 compose` (Windows)

### Option 3: From Source
```bash
git clone https://github.com/mwisnowski/mtg_python_deckbuilder.git
cd mtg_python_deckbuilder
pip install -r requirements.txt
python code/main.py
```

## 🗂️ File Structure

After running, you'll have:
```
mtg_python_deckbuilder/
├── deck_files/          # Your saved decks (CSV and TXT files)
├── logs/               # Application logs
├── csv_files/          # Card database files
└── ...
```

## 🔧 System Requirements

- **Docker**: Latest version recommended
- **Python**: 3.11+ (if running from source)
- **Memory**: 2GB+ RAM for card database processing
- **Storage**: 500MB+ for card data and decks

## 📋 Dependencies

### Core Dependencies
- pandas >= 1.5.0
- inquirer >= 3.1.3
- scrython >= 1.10.0
- numpy >= 1.24.0
- requests >= 2.31.0

### Development Dependencies
- mypy >= 1.3.0
- pandas-stubs >= 2.0.0
- pytest >= 8.0.0

## 🐛 Known Issues

- Initial setup requires internet connection for card data download
- Large card database may take time to process on first run
- File permissions may show as 'root' when using Docker (normal behavior)

## 🔄 Breaking Changes

N/A - Initial release

## 🙏 Acknowledgments

- MTG JSON for comprehensive card data
- The Python community for excellent libraries
- Magic: The Gathering players and deck builders

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/mwisnowski/mtg_python_deckbuilder/issues)
- **Documentation**: See README.md and DOCKER.md
- **Docker Help**: `./run-docker.sh help`

---

**Full Changelog**: This is the initial release
