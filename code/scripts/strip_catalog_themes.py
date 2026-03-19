#!/usr/bin/env python3
"""
Strip Theme Catalog Script

Removes themes with insufficient card counts from the theme catalog YAML files.
Creates backups and logs all stripped themes for reference.

Usage:
    python -m code.scripts.strip_catalog_themes [--min-cards N] [--no-backup] [--dry-run]

Options:
    --min-cards N       Override THEME_MIN_CARDS setting (default: from environment/settings)
    --no-backup         Skip creating backup files
    --dry-run           Show what would be stripped without making changes

Example:
    python -m code.scripts.strip_catalog_themes
    python -m code.scripts.strip_catalog_themes --min-cards 3 --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from code import settings
from code.tagging.theme_stripper import (
    get_theme_card_counts,
    identify_themes_to_strip,
    strip_catalog_themes,
    create_stripped_themes_log,
    get_theme_distribution
)


def main():
    parser = argparse.ArgumentParser(
        description="Strip themes with insufficient card counts from catalog YAML files"
    )
    parser.add_argument(
        "--min-cards",
        type=int,
        default=settings.THEME_MIN_CARDS,
        help=f"Minimum cards required to keep a theme (default: {settings.THEME_MIN_CARDS})"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating backup files before modification"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be stripped without making changes"
    )
    
    args = parser.parse_args()
    
    # Paths
    processed_dir = Path(settings.CARD_FILES_PROCESSED_DIR)
    catalog_dir = PROJECT_ROOT / 'config' / 'themes' / 'catalog'
    log_dir = PROJECT_ROOT / 'logs'
    stripped_log_path = log_dir / 'stripped_themes.yml'
    
    print(f"Stripping themes from catalog (min_cards={args.min_cards})")
    print(f"Catalog directory: {catalog_dir}")
    print(f"Dry run: {args.dry_run}")
    print()
    
    # Step 1: Get theme card counts from parquet files
    print("Step 1: Analyzing theme card counts from parquet files...")
    parquet_files = sorted(processed_dir.glob("*.parquet"))
    if not parquet_files:
        print(f"Error: No parquet files found in {processed_dir}")
        return 1
    
    print(f"Found {len(parquet_files)} parquet files")
    theme_counts = get_theme_card_counts(parquet_files)
    print(f"Found {len(theme_counts)} unique themes")
    print()
    
    # Step 2: Get distribution
    distribution = get_theme_distribution(theme_counts)
    print("Theme distribution:")
    print(f"  1 card:     {distribution['1_card']:4d} themes")
    print(f"  2 cards:    {distribution['2_cards']:4d} themes")
    print(f"  3-4 cards:  {distribution['3_4_cards']:4d} themes")
    print(f"  5-9 cards:  {distribution['5_9_cards']:4d} themes")
    print(f"  10+ cards:  {distribution['10_plus']:4d} themes")
    print(f"  Total:      {distribution['total']:4d} themes")
    print()
    
    # Step 3: Identify themes to strip
    themes_to_strip = identify_themes_to_strip(theme_counts, args.min_cards)
    themes_to_keep = set(theme_counts.keys()) - themes_to_strip
    
    print(f"Themes to strip: {len(themes_to_strip)} ({len(themes_to_strip)/len(theme_counts)*100:.1f}%)")
    print(f"Themes to keep:  {len(themes_to_keep)} ({len(themes_to_keep)/len(theme_counts)*100:.1f}%)")
    print()
    
    # Show sample of themes to strip
    if themes_to_strip:
        print("Sample themes to strip (first 10):")
        sample = sorted(themes_to_strip)[:10]
        for theme_id in sample:
            count = len(theme_counts[theme_id])
            cards_sample = sorted(theme_counts[theme_id])[:3]
            cards_str = ", ".join(cards_sample)
            if count > 3:
                cards_str += f", ... ({count} total)"
            print(f"  - {theme_id} ({count} cards): {cards_str}")
        print()
    
    if args.dry_run:
        print("DRY RUN: No changes made")
        return 0
    
    # Step 4: Strip themes from catalog
    print("Step 4: Stripping themes from catalog YAML files...")
    results = strip_catalog_themes(
        catalog_dir=catalog_dir,
        themes_to_strip=themes_to_strip,
        backup=not args.no_backup
    )
    
    print(f"  Stripped: {results['stripped_count']} themes")
    print(f"  Files deleted: {len(results['files_deleted'])}")
    print(f"  Backups created: {len(results['backups_created'])}")
    
    if results['errors']:
        print(f"  Errors: {len(results['errors'])}")
        for error in results['errors'][:5]:  # Show first 5 errors
            print(f"    - {error}")
    print()
    
    # Step 5: Create stripped themes log
    print("Step 5: Creating stripped themes log...")
    create_stripped_themes_log(
        output_path=stripped_log_path,
        theme_counts=theme_counts,
        themes_stripped=themes_to_strip,
        min_threshold=args.min_cards,
        sources=["catalog YAML"]
    )
    print(f"  Log written to {stripped_log_path}")
    print()
    
    print("✅ Catalog stripping complete!")
    print()
    print(f"Summary:")
    print(f"  Total themes analyzed: {len(theme_counts)}")
    print(f"  Themes stripped: {len(themes_to_strip)}")
    print(f"  Themes remaining: {len(themes_to_keep)}")
    print(f"  Catalog files deleted: {len(results['files_deleted'])}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
