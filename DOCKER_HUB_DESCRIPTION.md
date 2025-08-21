# MTG Python Deckbuilder - Docker Hub

## Short Description (100 character limit)
```
Intelligent MTG Commander/EDH deck builder with theme detection and automated card suggestions
```

## Full Description (for the detailed description section)

**Intelligent MTG Commander/EDH deck builder with advanced theme detection and automated card suggestions.**

## Quick Start

```bash
# Create a directory for your decks
mkdir mtg-decks && cd mtg-decks

# Run the application
docker run -it --rm -v "$(pwd)":/app/host mwisnowski/mtg-python-deckbuilder:latest
```

## Features

- 🏗️ **Intelligent Deck Building** with commander selection and theme detection
- 📊 **Power Bracket System** for targeting specific competitive levels
- 🔄 **Instant Export** - deck lists displayed for easy copy/paste to Moxfield, EDHREC
- 🐳 **Zero Setup** - no Python installation required
- 💾 **Persistent Data** - your decks and progress are saved locally

## Tags

- `latest` - Most recent stable release
- `1.0.0` - Version 1.0.0 release

## Volume Mounts

Mount a local directory to `/app/host` to persist your deck files:

```bash
docker run -it --rm -v "$(pwd)":/app/host mwisnowski/mtg-python-deckbuilder:latest
```

Your deck files will be saved to:
- `deck_files/` - Completed decks (CSV and TXT formats)
- `logs/` - Application logs
- `csv_files/` - Card database files

## Source Code

- **GitHub**: https://github.com/mwisnowski/mtg_python_deckbuilder
- **Documentation**: See README.md for comprehensive setup guide
- **Issues**: Report bugs or request features on GitHub

## System Requirements

- Docker Desktop or Docker Engine
- 2GB+ RAM for card database processing
- 500MB+ disk space for card data and decks
- Internet connection for initial card data download

Built for the Magic: The Gathering community 🃏
