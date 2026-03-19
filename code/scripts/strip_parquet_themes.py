#!/usr/bin/env python3
"""
Strip low-card themes from parquet file themeTags columns.

This script identifies and removes themes below the THEME_MIN_CARDS threshold
from the themeTags column in parquet files. It's part of Milestone 4 (M4) of
the Theme Stripping roadmap (R21).

Usage:
    # Dry run to see what would be stripped
    python code/scripts/strip_parquet_themes.py --dry-run
    
    # Strip from single parquet file
    python code/scripts/strip_parquet_themes.py --file card_files/processed/all_cards.parquet
    
    # Strip from all parquet files in directory
    python code/scripts/strip_parquet_themes.py --all
    
    # Specify custom threshold
    python code/scripts/strip_parquet_themes.py --threshold 10 --all

Environment Variables:
    THEME_MIN_CARDS: Minimum card threshold (default: 5)

Outputs:
    - Modified parquet file(s) with stripped themeTags
    - Timestamped backup (.parquet.bak) if --backup enabled
    - Updated logs/stripped_themes.yml log
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from code import settings as code_settings
from code.tagging.theme_stripper import (
    get_theme_card_counts,
    identify_themes_to_strip,
    strip_parquet_themes,
    create_stripped_themes_log
)


def find_parquet_files(directory: Path) -> list[Path]:
    """Find all parquet files in processed directory."""
    return sorted(directory.glob("*.parquet"))


def update_stripped_themes_log(
    theme_counts: dict,
    themes_to_strip: set[str],
    min_cards: int
) -> None:
    """Update the stripped_themes.yml log with parquet stripping results."""
    log_path = ROOT / "logs" / "stripped_themes.yml"
    
    # Create log with parquet source indicator
    create_stripped_themes_log(
        output_path=log_path,
        theme_counts=theme_counts,
        themes_stripped=themes_to_strip,
        min_threshold=min_cards,
        sources=["parquet files"]
    )
    
    print(f"\nUpdated stripped themes log: {log_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Strip low-card themes from parquet themeTags columns",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--file',
        type=Path,
        help='Specific parquet file to process'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='Process all parquet files in card_files/processed/'
    )
    
    parser.add_argument(
        '--threshold',
        type=int,
        help=f'Minimum card count threshold (default: {code_settings.THEME_MIN_CARDS})'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be stripped without making changes'
    )
    
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip creating backup files before modification'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed stripping information'
    )
    
    args = parser.parse_args()
    
    # Determine threshold
    min_cards = args.threshold if args.threshold else code_settings.THEME_MIN_CARDS
    
    # Determine which files to process
    if args.file:
        if not args.file.exists():
            print(f"Error: File not found: {args.file}")
            return 1
        parquet_files = [args.file]
    elif args.all:
        processed_dir = ROOT / "card_files" / "processed"
        parquet_files = find_parquet_files(processed_dir)
        if not parquet_files:
            print(f"No parquet files found in {processed_dir}")
            return 1
    else:
        # Default: process all_cards.parquet
        default_file = ROOT / "card_files" / "processed" / "all_cards.parquet"
        if not default_file.exists():
            print(f"Error: Default file not found: {default_file}")
            print("Use --file or --all to specify files to process")
            return 1
        parquet_files = [default_file]
    
    print(f"Theme Stripping Configuration:")
    print(f"  Minimum cards: {min_cards}")
    print(f"  Files to process: {len(parquet_files)}")
    print(f"  Backup enabled: {not args.no_backup}")
    print(f"  Dry run: {args.dry_run}")
    print()
    
    # Get theme card counts from parquet files
    print("Analyzing theme card counts...")
    try:
        theme_counts = get_theme_card_counts(parquet_files)
        print(f"Found {len(theme_counts)} unique themes across files")
    except Exception as e:
        print(f"Error analyzing theme counts: {e}")
        return 1
    
    # Identify themes to strip
    print("Identifying themes to strip...")
    try:
        themes_to_strip = identify_themes_to_strip(theme_counts, min_cards)
    except Exception as e:
        print(f"Error identifying themes to strip: {e}")
        return 1
    
    if not themes_to_strip:
        print("No themes found below threshold. Nothing to strip.")
        return 0
    
    print(f"Found {len(themes_to_strip)} themes to strip")
    
    if args.verbose:
        sample = sorted(list(themes_to_strip))[:10]
        print(f"Sample themes: {', '.join(sample)}")
        if len(themes_to_strip) > 10:
            print(f"  ... and {len(themes_to_strip) - 10} more")
    
    print()
    
    # Dry run mode
    if args.dry_run:
        print("DRY RUN MODE - No files will be modified")
        print()
        for parquet_file in parquet_files:
            print(f"Would process: {parquet_file}")
        print(f"\nWould strip {len(themes_to_strip)} themes from themeTags column")
        return 0
    
    # Process each parquet file
    total_results = {
        "files_processed": 0,
        "cards_processed": 0,
        "tags_removed": 0,
        "errors": []
    }
    
    for parquet_file in parquet_files:
        print(f"Processing: {parquet_file.name}")
        
        try:
            results = strip_parquet_themes(
                parquet_path=parquet_file,
                themes_to_strip=themes_to_strip,
                backup=not args.no_backup
            )
            
            total_results["files_processed"] += 1
            total_results["cards_processed"] += results["cards_processed"]
            total_results["tags_removed"] += results["tags_removed"]
            total_results["errors"].extend(results["errors"])
            
            if args.verbose:
                print(f"  Cards: {results['cards_processed']}")
                print(f"  Tags removed: {results['tags_removed']}")
                if results["backup_created"]:
                    print(f"  Backup: {results['backup_created']}")
            
        except Exception as e:
            error_msg = f"Error processing {parquet_file}: {e}"
            print(f"  {error_msg}")
            total_results["errors"].append(error_msg)
            continue
        
        print()
    
    # Update stripped themes log
    try:
        update_stripped_themes_log(theme_counts, themes_to_strip, min_cards)
    except Exception as e:
        print(f"Warning: Failed to update stripped themes log: {e}")
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Files processed: {total_results['files_processed']}")
    print(f"Cards processed: {total_results['cards_processed']}")
    print(f"Tags removed: {total_results['tags_removed']}")
    print(f"Themes stripped: {len(themes_to_strip)}")
    
    if total_results["errors"]:
        print(f"\nErrors encountered: {len(total_results['errors'])}")
        for error in total_results["errors"]:
            print(f"  - {error}")
    else:
        print("\nStripping completed successfully!")
    
    return 0 if not total_results["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
