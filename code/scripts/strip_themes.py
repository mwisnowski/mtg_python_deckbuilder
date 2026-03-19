#!/usr/bin/env python3
"""
Standalone theme stripping orchestration script.

This script coordinates the complete theme stripping pipeline:
1. Analyze parquet files to identify low-card themes
2. Strip from catalog YAML files (optional)
3. Strip from parquet themeTags columns (optional)
4. Rebuild theme_list.json from stripped parquet data
5. Generate stripped_themes.yml log

Part of Milestone 5 (M5) - Integration & Testing for Theme Stripping (R21).

Usage:
    # Dry run to preview changes
    python code/scripts/strip_themes.py --dry-run
    
    # Strip everything with default threshold (5 cards)
    python code/scripts/strip_themes.py
    
    # Strip only catalog YAML files
    python code/scripts/strip_themes.py --sources catalog
    
    # Strip only parquet files
    python code/scripts/strip_themes.py --sources parquet
    
    # Custom threshold
    python code/scripts/strip_themes.py --min-cards 10
    
    # Skip backups (not recommended)
    python code/scripts/strip_themes.py --no-backup

Environment Variables:
    THEME_MIN_CARDS: Minimum card threshold (default: 5)

Outputs:
    - Modified catalog/*.yml files (if --sources includes catalog)
    - Modified parquet files (if --sources includes parquet)
    - Regenerated config/themes/theme_list.json
    - Updated logs/stripped_themes.yml log
    - Timestamped backups (if --backup enabled)
"""

import argparse
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Set, Dict

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from code import settings as code_settings
from code.tagging.theme_stripper import (
    get_theme_card_counts,
    identify_themes_to_strip,
    strip_catalog_themes,
    strip_parquet_themes,
    create_stripped_themes_log
)


def strip_all_sources(
    min_cards: int,
    sources: Set[str],
    backup: bool,
    dry_run: bool,
    verbose: bool
) -> Dict:
    """
    Execute complete theme stripping pipeline.
    
    Args:
        min_cards: Minimum card count threshold
        sources: Set of sources to strip ('catalog', 'parquet', or both)
        backup: Whether to create backups before modification
        dry_run: Preview changes without modifying files
        verbose: Show detailed output
        
    Returns:
        Dictionary with stripping results and statistics
    """
    start_time = time.time()
    results = {
        "themes_analyzed": 0,
        "themes_to_strip": 0,
        "catalog_stripped": 0,
        "parquet_tags_removed": 0,
        "json_regenerated": False,
        "errors": []
    }
    
    print("="*70)
    print("THEME STRIPPING PIPELINE")
    print("="*70)
    print(f"Configuration:")
    print(f"  Minimum cards: {min_cards}")
    print(f"  Sources: {', '.join(sorted(sources))}")
    print(f"  Backup enabled: {backup}")
    print(f"  Dry run: {dry_run}")
    print()
    
    # Step 1: Analyze parquet files
    print("Step 1: Analyzing theme card counts...")
    try:
        parquet_dir = ROOT / "card_files" / "processed"
        parquet_files = sorted(parquet_dir.glob("*.parquet"))
        
        if not parquet_files:
            results["errors"].append("No parquet files found in card_files/processed/")
            return results
        
        theme_counts = get_theme_card_counts(parquet_files)
        results["themes_analyzed"] = len(theme_counts)
        print(f"  Found {len(theme_counts)} unique themes")
        
        themes_to_strip = identify_themes_to_strip(theme_counts, min_cards)
        results["themes_to_strip"] = len(themes_to_strip)
        print(f"  Identified {len(themes_to_strip)} themes below threshold")
        
        if verbose and themes_to_strip:
            sample = sorted(list(themes_to_strip))[:5]
            print(f"  Sample themes: {', '.join(sample)}")
            if len(themes_to_strip) > 5:
                print(f"    ... and {len(themes_to_strip) - 5} more")
        
        if not themes_to_strip:
            print("\n✅ No themes below threshold. Nothing to strip.")
            return results
            
    except Exception as e:
        error_msg = f"Analysis failed: {e}"
        print(f"  ❌ {error_msg}")
        results["errors"].append(error_msg)
        return results
    
    print()
    
    # Dry run mode
    if dry_run:
        print("DRY RUN MODE - No files will be modified")
        print()
        if 'catalog' in sources:
            print("Would strip from catalog YAML files:")
            catalog_dir = ROOT / "config" / "themes" / "catalog"
            yaml_files = sorted(catalog_dir.glob("*.yml"))
            for yaml_file in yaml_files[:5]:
                print(f"  - {yaml_file.name}")
            if len(yaml_files) > 5:
                print(f"  ... and {len(yaml_files) - 5} more")
        
        if 'parquet' in sources:
            print("\nWould strip from parquet files:")
            for pf in parquet_files[:3]:
                print(f"  - {pf.name}")
            if len(parquet_files) > 3:
                print(f"  ... and {len(parquet_files) - 3} more")
        
        print(f"\nWould strip {len(themes_to_strip)} themes total")
        print("Would regenerate theme_list.json")
        print("Would update stripped_themes.yml log")
        return results
    
    # Step 2: Strip from catalog (if requested)
    # NOTE: Catalog YAML must be stripped BEFORE building theme_list.json,
    # otherwise build_theme_catalog.py will read un-stripped themes from YAML
    if 'catalog' in sources:
        print("Step 2: Stripping from catalog YAML files...")
        try:
            catalog_dir = ROOT / "config" / "themes" / "catalog"
            catalog_results = strip_catalog_themes(
                catalog_dir=catalog_dir,
                themes_to_strip=themes_to_strip,
                backup=backup
            )
            
            results["catalog_stripped"] = catalog_results["files_modified"]
            
            if verbose:
                print(f"  Files modified: {catalog_results['files_modified']}")
                print(f"  Themes removed: {catalog_results['themes_removed']}")
                if catalog_results["backups_created"]:
                    print(f"  Backups created: {len(catalog_results['backups_created'])}")
            else:
                print(f"  ✓ Stripped {catalog_results['themes_removed']} themes from {catalog_results['files_modified']} files")
            
            results["errors"].extend(catalog_results["errors"])
            
        except Exception as e:
            error_msg = f"Catalog stripping failed: {e}"
            print(f"  ❌ {error_msg}")
            results["errors"].append(error_msg)
        
        print()
    
    # Step 3: Strip from parquet (if requested)
    if 'parquet' in sources:
        step_num = 3 if 'catalog' in sources else 2
        print(f"Step {step_num}: Stripping from parquet files...")
        try:
            for parquet_file in parquet_files:
                if verbose:
                    print(f"  Processing: {parquet_file.name}")
                
                parquet_results = strip_parquet_themes(
                    parquet_path=parquet_file,
                    themes_to_strip=themes_to_strip,
                    backup=backup
                )
                
                results["parquet_tags_removed"] += parquet_results["tags_removed"]
                results["errors"].extend(parquet_results["errors"])
                
                if verbose and parquet_results["tags_removed"] > 0:
                    print(f"    Removed {parquet_results['tags_removed']} tag occurrences")
            
            if not verbose:
                print(f"  ✓ Removed {results['parquet_tags_removed']} tag occurrences from {len(parquet_files)} file(s)")
            
        except Exception as e:
            error_msg = f"Parquet stripping failed: {e}"
            print(f"  ❌ {error_msg}")
            results["errors"].append(error_msg)
        
        print()
    
    # Step 4: Rebuild theme_list.json (if parquet was stripped)
    # NOTE: This reads from both parquet AND catalog YAML, so both must be stripped first
    if 'parquet' in sources:
        step_num = 4 if 'catalog' in sources else 3
        print(f"Step {step_num}: Rebuilding theme_list.json...")
        try:
            # Import build script
            from code.scripts.build_theme_catalog import main as build_main
            
            # Suppress verbose build output unless --verbose flag
            import io
            import contextlib
            
            if not verbose:
                with contextlib.redirect_stdout(io.StringIO()):
                    build_main()
            else:
                build_main()
            
            results["json_regenerated"] = True
            print("  ✓ theme_list.json regenerated")
            
        except Exception as e:
            error_msg = f"JSON regeneration failed: {e}"
            print(f"  ❌ {error_msg}")
            results["errors"].append(error_msg)
        
        print()
    
    # Step 5: Update stripped themes log
    final_step = 5 if ('catalog' in sources and 'parquet' in sources) else (3 if 'catalog' in sources else 4)
    print(f"Step {final_step}: Updating stripped_themes.yml log...")
    try:
        log_path = ROOT / "logs" / "stripped_themes.yml"
        source_labels = []
        if 'catalog' in sources:
            source_labels.append("catalog YAML")
        if 'parquet' in sources:
            source_labels.append("parquet files")
        
        create_stripped_themes_log(
            output_path=log_path,
            theme_counts=theme_counts,
            themes_stripped=themes_to_strip,
            min_threshold=min_cards,
            sources=source_labels if source_labels else None
        )
        print(f"  ✓ Log updated: {log_path}")
        
    except Exception as e:
        error_msg = f"Log update failed: {e}"
        print(f"  ❌ {error_msg}")
        results["errors"].append(error_msg)
    
    # Final summary
    elapsed = time.time() - start_time
    print()
    print("="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Themes analyzed: {results['themes_analyzed']}")
    print(f"Themes stripped: {results['themes_to_strip']}")
    if 'catalog' in sources:
        print(f"Catalog files modified: {results['catalog_stripped']}")
    if 'parquet' in sources:
        print(f"Parquet tags removed: {results['parquet_tags_removed']}")
        print(f"JSON regenerated: {'Yes' if results['json_regenerated'] else 'No'}")
    print(f"Time elapsed: {elapsed:.2f}s")
    
    if results["errors"]:
        print(f"\n⚠️  Errors encountered: {len(results['errors'])}")
        for error in results["errors"]:
            print(f"  - {error}")
    else:
        print("\n✅ Theme stripping completed successfully!")
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Orchestrate complete theme stripping pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--min-cards',
        type=int,
        help=f'Minimum card count threshold (default: {code_settings.THEME_MIN_CARDS})'
    )
    
    parser.add_argument(
        '--sources',
        type=str,
        help='Comma-separated list of sources to strip: catalog, parquet, all (default: all)'
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
    min_cards = args.min_cards if args.min_cards else code_settings.THEME_MIN_CARDS
    
    # Determine sources
    if args.sources:
        source_input = args.sources.lower()
        if source_input == 'all':
            sources = {'catalog', 'parquet'}
        else:
            sources = set(s.strip() for s in source_input.split(','))
            valid_sources = {'catalog', 'parquet'}
            invalid = sources - valid_sources
            if invalid:
                print(f"Error: Invalid sources: {', '.join(invalid)}")
                print(f"Valid sources: {', '.join(valid_sources)}, all")
                return 1
    else:
        sources = {'catalog', 'parquet'}  # Default: all sources
    
    # Execute pipeline
    results = strip_all_sources(
        min_cards=min_cards,
        sources=sources,
        backup=not args.no_backup,
        dry_run=args.dry_run,
        verbose=args.verbose
    )
    
    # Return exit code
    return 0 if not results["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
