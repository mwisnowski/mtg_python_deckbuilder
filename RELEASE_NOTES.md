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
docker run -it --rm -v "$(pwd)":/app/host mwisnowski/mtg-python-deckbuilder:latest
```

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
