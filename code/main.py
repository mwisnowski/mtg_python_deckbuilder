"""Command-line entrypoint for the MTG Python Deckbuilder.

Launches directly into the interactive deck builder. On first run (or if the
card database is missing), it automatically performs initial setup and tagging.
"""
from __future__ import annotations

# Standard library imports
import sys
from pathlib import Path
from typing import NoReturn

# Ensure local package resolution in frozen builds
import os
if getattr(sys, 'frozen', False):  # PyInstaller frozen
    base = os.path.dirname(sys.executable)
    code_dir = os.path.join(base, 'code')
    if os.path.isdir(code_dir) and code_dir not in sys.path:
        sys.path.insert(0, code_dir)

# Local imports
from deck_builder import DeckBuilder
from file_setup.setup import initial_setup, run_full_pipeline
from tagging import tagger
import logging_util
from settings import CSV_DIRECTORY
from path_util import get_processed_cards_path

# Create logger for this module
logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
logger.addHandler(logging_util.file_handler)
logger.addHandler(logging_util.stream_handler)

builder = DeckBuilder()

def _ensure_data_ready() -> None:
    logger.info("Starting MTG Python Deckbuilder")
    Path('csv_files').mkdir(parents=True, exist_ok=True)
    Path('deck_files').mkdir(parents=True, exist_ok=True)
    Path('logs').mkdir(parents=True, exist_ok=True)

    # Ensure required Parquet file exists and is tagged before proceeding
    try:
        import time
        import json as _json
        from datetime import datetime as _dt
        parquet_path = get_processed_cards_path()
        flag_path = os.path.join(CSV_DIRECTORY, '.tagging_complete.json')
        refresh_needed = False
        # Missing Parquet file forces refresh
        if not os.path.exists(parquet_path):
            logger.info("all_cards.parquet not found. Running initial setup and tagging...")
            refresh_needed = True
        else:
            # Stale Parquet file (>7 days) forces refresh
            try:
                age_seconds = time.time() - os.path.getmtime(parquet_path)
                if age_seconds > 7 * 24 * 60 * 60:
                    logger.info("all_cards.parquet is older than 7 days. Refreshing data (setup + tagging)...")
                    refresh_needed = True
            except Exception:
                pass
        # Missing tagging flag forces refresh
        if not os.path.exists(flag_path):
            logger.info("Tagging completion flag not found. Performing full tagging...")
            refresh_needed = True
        if refresh_needed:
            run_full_pipeline(output_func=lambda msg: logger.info(msg), parallel=True)
            # Write tagging completion flag
            try:
                os.makedirs(CSV_DIRECTORY, exist_ok=True)
                with open(flag_path, 'w', encoding='utf-8') as _fh:
                    _json.dump({
                        'tagged_at': _dt.now().isoformat(timespec='seconds')
                    }, _fh)
            except Exception:
                logger.warning("Failed to write tagging completion flag (non-fatal).")
            logger.info("Initial setup and tagging completed.")
    except Exception as e:
        logger.error(f"Failed ensuring CSVs are ready: {e}")


def _interactive_loop() -> None:
    while True:
        try:
            # Fresh builder instance for each deck to avoid state carryover
            DeckBuilder().build_deck_full()
        except Exception as e:
            logger.error(f"Unexpected error in deck builder: {e}")

        # Prompt to build another deck or return to main menu
        try:
            resp = input("\nBuild another deck? (y/n): ").strip().lower()
        except KeyboardInterrupt:
            resp = 'n'
            print("")
        if resp not in ('y', 'yes'):
            break


def run_menu() -> NoReturn:
    """Launch directly into the deck builder after ensuring data files exist.

    Creates required directories, ensures card CSVs are present (running setup
    and tagging if needed), then starts the full deck build flow. Exits when done.
    """
    _ensure_data_ready()

    # Auto headless mode for container runs (no menu prompt)
    auto_mode = os.getenv('DECK_MODE', '').strip().lower()
    if auto_mode in ("headless", "noninteractive", "auto"):
        try:
            from headless_runner import _main as headless_main
            headless_main()
        except Exception as e:
            logger.error(f"Headless run failed: {e}")
        logger.info("Exiting application")
        sys.exit(0)

    # Menu-driven selection
    def _run_headless() -> None:
        """Run headless runner with current CLI/env-configured defaults."""
        try:
            from headless_runner import _main as headless_main
            headless_main()
        except Exception as e:
            logger.error(f"Headless run failed: {e}")

    while True:
        print("\n==== MTG Deckbuilder ====")
        print("1) Interactive deck build")
        print("2) Headless (env/CLI-configured) run")
        print("q) Quit")
        try:
            choice = input("Select an option [1]: ").strip().lower() or '1'
        except KeyboardInterrupt:
            print("")
            choice = 'q'

        if choice in ('1', 'i', 'interactive'):
            _interactive_loop()
            # loop returns to main menu
        elif choice in ('2', 'h', 'headless', 'noninteractive'):
            _run_headless()
            # after one headless run, return to menu
        elif choice in ('q', 'quit', 'exit'):
            logger.info("Exiting application")
            sys.exit(0)
        else:
            print("Invalid selection. Please try again.")

if __name__ == "__main__":
    run_menu()