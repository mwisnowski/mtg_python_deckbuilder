"""Command-line entrypoint for the MTG Python Deckbuilder.

Launches directly into the interactive deck builder. On first run (or if the
card database is missing), it automatically performs initial setup and tagging.
"""
from __future__ import annotations

# Standard library imports
import sys
from pathlib import Path
import json
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
from file_setup.setup import initial_setup
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
            initial_setup()
            tagger.run_tagging(parallel=True)  # Use parallel tagging for performance
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
    def _run_headless_with_config(selected_config: str | None) -> None:
        """Run headless runner, optionally forcing a specific config path for this invocation."""
        try:
            from headless_runner import _main as headless_main
            # Temporarily override DECK_CONFIG for this run if provided
            prev_cfg = os.environ.get('DECK_CONFIG')
            try:
                if selected_config:
                    os.environ['DECK_CONFIG'] = selected_config
                headless_main()
            finally:
                if selected_config is not None:
                    if prev_cfg is not None:
                        os.environ['DECK_CONFIG'] = prev_cfg
                    else:
                        os.environ.pop('DECK_CONFIG', None)
        except Exception as e:
            logger.error(f"Headless run failed: {e}")

    def _headless_submenu() -> None:
        """Submenu to choose a JSON config and run the headless builder.

        Behavior:
        - If DECK_CONFIG points to a file, run it immediately.
        - Else, search for *.json in (DECK_CONFIG as dir) or /app/config or ./config.
          - If one file is found, run it immediately.
          - If multiple files, list them for selection.
          - If none, fall back to running headless using env/CLI/defaults.
        """
        cfg_target = os.getenv('DECK_CONFIG')
        # Case 1: DECK_CONFIG is an explicit file
        if cfg_target and os.path.isfile(cfg_target):
            print(f"\nRunning headless with config: {cfg_target}")
            _run_headless_with_config(cfg_target)
            return

        # Determine directory to scan for JSON configs
        if cfg_target and os.path.isdir(cfg_target):
            cfg_dir = cfg_target
        elif os.path.isdir('/app/config'):
            cfg_dir = '/app/config'
        else:
            cfg_dir = 'config'

        try:
            p = Path(cfg_dir)
            files = sorted([str(fp) for fp in p.glob('*.json')]) if p.exists() else []
        except Exception:
            files = []

        # No configs found: run headless with current env/CLI/defaults
        if not files:
            print("\nNo JSON configs found in '" + cfg_dir + "'. Running headless with env/CLI/defaults...")
            _run_headless_with_config(None)
            return

        # Single config: run automatically
        if len(files) == 1:
            print(f"\nFound one JSON config: {files[0]}\nRunning it now...")
            _run_headless_with_config(files[0])
            return

        # Multiple configs: list and select
        def _config_label(p: str) -> str:
            try:
                with open(p, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                cmd = str(data.get('commander') or '').strip() or 'Unknown Commander'
                themes = [t for t in [data.get('primary_tag'), data.get('secondary_tag'), data.get('tertiary_tag')] if isinstance(t, str) and t.strip()]
                name = os.path.basename(p).lower()
                if name == 'deck.json':
                    return 'Default'
                return f"{cmd} - {', '.join(themes)}" if themes else cmd
            except Exception:
                return p

        print("\nAvailable JSON configs:")
        labels = [_config_label(f) for f in files]
        for idx, label in enumerate(labels, start=1):
            print(f"  {idx}) {label}")
        print("  0) Back to main menu")
        while True:
            try:
                sel = input("Select a config to run [0]: ").strip() or '0'
            except KeyboardInterrupt:
                print("")
                sel = '0'
            if sel == '0':
                return
            try:
                i = int(sel)
                if 1 <= i <= len(files):
                    _run_headless_with_config(files[i - 1])
                    return
            except ValueError:
                pass
            print("Invalid selection. Try again.")

    while True:
        print("\n==== MTG Deckbuilder ====")
        print("1) Interactive deck build")
        print("2) Headless (env/JSON-configured) run")
        print("   - Will auto-run a single config if found, or let you choose from many")
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
            _headless_submenu()
            # after one headless run, return to menu
        elif choice in ('q', 'quit', 'exit'):
            logger.info("Exiting application")
            sys.exit(0)
        else:
            print("Invalid selection. Please try again.")

if __name__ == "__main__":
    run_menu()