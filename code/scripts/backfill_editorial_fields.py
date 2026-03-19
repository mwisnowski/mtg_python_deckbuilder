"""Backfill M1 editorial tracking fields (description_source, popularity_pinned) to theme YAML files.

This script adds tracking metadata to existing theme YAMLs to support editorial workflows:
- description_source: Classifies descriptions as 'rule', 'generic', or 'manual'
- popularity_pinned: Boolean flag to prevent auto-population_bucket updates

Usage:
    python code/scripts/backfill_editorial_fields.py [--dry-run] [--verbose]
    
Options:
    --dry-run: Show changes without writing files
    --verbose: Print detailed progress
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / 'code'))

from type_definitions_theme_catalog import ThemeYAMLFile
from web.services.theme_editorial_service import ThemeEditorialService


def load_yaml_raw(file_path: Path) -> Dict:
    """Load YAML file preserving order and comments."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def write_yaml_preserving_order(file_path: Path, data: Dict) -> None:
    """Write YAML file with consistent formatting."""
    with open(file_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,  # Preserve insertion order
            indent=2,
        )


def backfill_theme_yaml(
    file_path: Path,
    service: ThemeEditorialService,
    dry_run: bool = False,
    verbose: bool = False
) -> Tuple[bool, List[str]]:
    """Backfill M1 editorial fields to a single theme YAML.
    
    Args:
        file_path: Path to theme YAML file
        service: ThemeEditorialService instance for inference
        dry_run: If True, don't write changes
        verbose: If True, print detailed messages
        
    Returns:
        Tuple of (modified, changes) where:
        - modified: True if file was changed
        - changes: List of change descriptions
    """
    try:
        # Load raw YAML
        raw_data = load_yaml_raw(file_path)
        
        # Validate against ThemeYAMLFile model
        theme = ThemeYAMLFile(**raw_data)
        
        changes = []
        modified = False
        
        # Check description_source
        if not raw_data.get('description_source'):
            if theme.description:
                inferred = service.infer_description_source(theme.description)
                raw_data['description_source'] = inferred
                changes.append(f"Added description_source='{inferred}'")
                modified = True
            else:
                changes.append("Skipped description_source (no description)")
        
        # Check popularity_pinned
        if 'popularity_pinned' not in raw_data:
            raw_data['popularity_pinned'] = False
            changes.append("Added popularity_pinned=False")
            modified = True
        
        # Write back if modified and not dry-run
        if modified and not dry_run:
            write_yaml_preserving_order(file_path, raw_data)
        
        if verbose and modified:
            print(f"{'[DRY-RUN] ' if dry_run else ''}Modified: {file_path.name}")
            for change in changes:
                print(f"  - {change}")
        
        return modified, changes
        
    except Exception as e:
        if verbose:
            print(f"ERROR processing {file_path.name}: {e}", file=sys.stderr)
        return False, [f"Error: {e}"]


def backfill_catalog(
    catalog_dir: Path,
    dry_run: bool = False,
    verbose: bool = False
) -> Dict[str, int]:
    """Backfill all theme YAML files in catalog directory.
    
    Args:
        catalog_dir: Path to themes/catalog/ directory
        dry_run: If True, don't write changes
        verbose: If True, print detailed progress
        
    Returns:
        Statistics dict with counts
    """
    service = ThemeEditorialService()
    
    yaml_files = sorted(catalog_dir.glob('*.yml'))
    
    stats = {
        'total': len(yaml_files),
        'modified': 0,
        'unchanged': 0,
        'errors': 0,
    }
    
    print(f"Processing {stats['total']} theme YAML files...")
    if dry_run:
        print("[DRY-RUN MODE] No files will be modified\n")
    
    for yaml_path in yaml_files:
        modified, changes = backfill_theme_yaml(yaml_path, service, dry_run, verbose)
        
        if changes and changes[0].startswith('Error:'):
            stats['errors'] += 1
        elif modified:
            stats['modified'] += 1
        else:
            stats['unchanged'] += 1
    
    return stats


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backfill M1 editorial tracking fields to theme YAML files"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Show changes without writing files"
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help="Print detailed progress"
    )
    parser.add_argument(
        '--catalog-dir',
        type=Path,
        default=ROOT / 'config' / 'themes' / 'catalog',
        help="Path to theme catalog directory (default: config/themes/catalog)"
    )
    
    args = parser.parse_args()
    
    if not args.catalog_dir.exists():
        print(f"ERROR: Catalog directory not found: {args.catalog_dir}", file=sys.stderr)
        return 1
    
    # Run backfill
    stats = backfill_catalog(args.catalog_dir, args.dry_run, args.verbose)
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"Backfill {'Summary (DRY-RUN)' if args.dry_run else 'Complete'}:")
    print(f"  Total files: {stats['total']}")
    print(f"  Modified: {stats['modified']}")
    print(f"  Unchanged: {stats['unchanged']}")
    print(f"  Errors: {stats['errors']}")
    print(f"{'='*60}")
    
    if args.dry_run:
        print("\nRe-run without --dry-run to apply changes.")
    
    return 0 if stats['errors'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
