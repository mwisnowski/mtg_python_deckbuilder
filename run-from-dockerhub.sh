#!/bin/bash

echo "MTG Python Deckbuilder - Docker Hub Runner"
echo "==========================================="

# Create directories if they don't exist
mkdir -p deck_files logs csv_files
mkdir -p config

echo "Starting MTG Python Deckbuilder from Docker Hub..."
echo "Your files will be saved in the current directory:"
echo "  - deck_files/: Your completed decks"
echo "  - logs/: Application logs"  
echo "  - csv_files/: Card database files"
echo "  - config/: JSON configs for headless runs (e.g., deck.json)"
echo

# Run the Docker container with proper volume mounts
docker run -it --rm \
  -v "$(pwd)/deck_files":/app/deck_files \
  -v "$(pwd)/logs":/app/logs \
  -v "$(pwd)/csv_files":/app/csv_files \
  -v "$(pwd)/config":/app/config \
  mwisnowski/mtg-python-deckbuilder:latest

echo
echo "MTG Python Deckbuilder session ended."
echo "Your files are saved in: $(pwd)"
