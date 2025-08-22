"""Command-line entrypoint for the MTG Python Deckbuilder.

Launches directly into the interactive deck builder. On first run (or if the
card database is missing), it automatically performs initial setup and tagging.
"""
from __future__ import annotations

# Standard library imports
import sys
from pathlib import Path
from typing import NoReturn

# Local imports
from deck_builder import DeckBuilder
from file_setup.setup import initial_setup
from tagging import tagger
import logging_util
import os
from settings import CSV_DIRECTORY

# Create logger for this module
logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
logger.addHandler(logging_util.file_handler)
logger.addHandler(logging_util.stream_handler)

builder = DeckBuilder()

def run_menu() -> NoReturn:
    """Launch directly into the deck builder after ensuring data files exist.

    Creates required directories, ensures card CSVs are present (running setup
    and tagging if needed), then starts the full deck build flow. Exits when done.
    """
    logger.info("Starting MTG Python Deckbuilder")
    Path('csv_files').mkdir(parents=True, exist_ok=True)
    Path('deck_files').mkdir(parents=True, exist_ok=True)
    Path('logs').mkdir(parents=True, exist_ok=True)

    # Ensure required CSVs exist and are tagged before proceeding
    try:
        cards_path = os.path.join(CSV_DIRECTORY, 'cards.csv')
        if not os.path.exists(cards_path):
            logger.info("cards.csv not found. Running initial setup and tagging...")
            initial_setup()
            tagger.run_tagging()
            logger.info("Initial setup and tagging completed.")
    except Exception as e:
        logger.error(f"Failed ensuring CSVs are ready: {e}")
    while True:
        try:
            # Fresh builder instance for each deck to avoid state carryover
            DeckBuilder().build_deck_full()
        except Exception as e:
            logger.error(f"Unexpected error in deck builder: {e}")

        # Prompt to build another deck or quit
        try:
            resp = input("\nBuild another deck? (y/n): ").strip().lower()
        except KeyboardInterrupt:
            resp = 'n'
            print("")
        if resp not in ('y', 'yes'):
            logger.info("Exiting application")
            sys.exit(0)

if __name__ == "__main__":
    run_menu()