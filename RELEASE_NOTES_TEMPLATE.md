# MTG Python Deckbuilder ${VERSION}

## Highlights
- Direct-to-builder launch with automatic initial setup and tagging
- Improved Type Summary (accurate Commander/Creature/etc. counts)
- Smarter export filenames: full commander name + ordered themes + date, with auto-increment
- TXT export duplication fixed
- Post-build prompt to build another deck or quit

## Docker
- Multi-arch image (amd64, arm64) on Docker Hub
- Persistent volumes:
  - /app/deck_files
  - /app/logs
  - /app/csv_files

### Quick Start
```bash
mkdir mtg-decks && cd mtg-decks

docker run -it --rm \
  -v "$(pwd)/deck_files":/app/deck_files \
  -v "$(pwd)/logs":/app/logs \
  -v "$(pwd)/csv_files":/app/csv_files \
  mwisnowski/mtg-python-deckbuilder:latest
```

Windows PowerShell users: see WINDOWS_DOCKER_GUIDE.md or run:
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/mwisnowski/mtg_python_deckbuilder/main/run-from-dockerhub.bat" -OutFile "run-from-dockerhub.bat" run-from-dockerhub.bat

## Changes
- Auto-setup/tagging when `csv_files/cards.csv` is missing (both main and builder)
- Main entrypoint now skips menu and launches the deck builder
- Type summary classification matches export categories; uses snapshot fallback
- Export filenames:
  - Full commander name (punctuation removed)
  - All themes in order
  - Date suffix (YYYYMMDD)
  - Auto-increment when file exists
- Removed duplicate TXT sidecar creation in CSV export

## Known Issues
- First run downloads card data; may take several minutes
- Ensure volume mounts are present to persist files outside the container

## Links
- Repo: https://github.com/mwisnowski/mtg_python_deckbuilder
- Issues: https://github.com/mwisnowski/mtg_python_deckbuilder/issues
