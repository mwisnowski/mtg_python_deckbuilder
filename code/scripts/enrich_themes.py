"""CLI wrapper for theme enrichment pipeline.

Runs the consolidated theme enrichment pipeline with command-line options.
For backward compatibility, individual scripts can still be run separately,
but this provides a faster single-pass alternative.

Usage:
    python code/scripts/enrich_themes.py --write
    python code/scripts/enrich_themes.py --dry-run --enforce-min
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import after adding to path
from code.tagging.theme_enrichment import run_enrichment_pipeline  # noqa: E402


def main() -> int:
    """Run theme enrichment pipeline from CLI."""
    parser = argparse.ArgumentParser(
        description='Consolidated theme metadata enrichment pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (no changes written):
  python code/scripts/enrich_themes.py --dry-run
  
  # Write changes:
  python code/scripts/enrich_themes.py --write
  
  # Enforce minimum examples (errors if insufficient):
  python code/scripts/enrich_themes.py --write --enforce-min
  
  # Strict validation for cornerstone themes:
  python code/scripts/enrich_themes.py --write --strict

Note: This replaces running 7 separate scripts (autofill, pad, cleanup, purge,
augment, suggestions, lint) with a single 5-10x faster operation.
        """
    )
    
    parser.add_argument(
        '--write',
        action='store_true',
        help='Write changes to disk (default: dry run)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode: show what would be changed without writing'
    )
    parser.add_argument(
        '--min',
        '--min-examples',
        type=int,
        default=None,
        metavar='N',
        help='Minimum number of example commanders (default: $EDITORIAL_MIN_EXAMPLES or 5)'
    )
    parser.add_argument(
        '--enforce-min',
        action='store_true',
        help='Treat minimum examples violations as errors'
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Enable strict validation (cornerstone themes must have examples)'
    )
    
    args = parser.parse_args()
    
    # Determine write mode
    if args.dry_run:
        write = False
    elif args.write:
        write = True
    else:
        # Default to dry run if neither specified
        write = False
        print("Note: Running in dry-run mode (use --write to save changes)\n")
    
    # Get minimum examples threshold
    if args.min is not None:
        min_examples = args.min
    else:
        min_examples = int(os.environ.get('EDITORIAL_MIN_EXAMPLES', '5'))
    
    print("Theme Enrichment Pipeline")
    print("========================")
    print(f"Mode: {'WRITE' if write else 'DRY RUN'}")
    print(f"Min examples: {min_examples}")
    print(f"Enforce min: {args.enforce_min}")
    print(f"Strict: {args.strict}")
    print()
    
    try:
        stats = run_enrichment_pipeline(
            root=ROOT,
            min_examples=min_examples,
            write=write,
            enforce_min=args.enforce_min,
            strict=args.strict,
            progress_callback=None,  # Use default print
        )
        
        # Return non-zero if there are lint errors
        if stats.lint_errors > 0:
            print(f"\n❌ Enrichment completed with {stats.lint_errors} error(s)")
            return 1
        
        print("\n✅ Enrichment completed successfully")
        return 0
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        if '--debug' in sys.argv:
            raise
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
