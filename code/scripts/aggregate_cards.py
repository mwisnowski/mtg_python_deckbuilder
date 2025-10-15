#!/usr/bin/env python3
"""
Aggregate Cards CLI Script

Command-line interface for consolidating individual card CSV files into a single
Parquet file. Useful for manual aggregation runs, testing, and recovery.

Usage:
    python code/scripts/aggregate_cards.py
    python code/scripts/aggregate_cards.py --source csv_files --output card_files/all_cards.parquet
    python code/scripts/aggregate_cards.py --validate-only
    python code/scripts/aggregate_cards.py --incremental
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from code.file_setup.card_aggregator import CardAggregator
from code.logging_util import get_logger
from code.settings import CSV_DIRECTORY, CARD_FILES_DIRECTORY

# Initialize logger
logger = get_logger(__name__)


def main() -> int:
    """Main entry point for aggregate_cards CLI."""
    parser = argparse.ArgumentParser(
        description="Aggregate individual card CSV files into consolidated Parquet file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--source",
        "-s",
        default=CSV_DIRECTORY,
        help=f"Source directory containing card CSV files (default: {CSV_DIRECTORY})",
    )

    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output Parquet file path (default: card_files/all_cards.parquet)",
    )

    parser.add_argument(
        "--output-dir",
        default=CARD_FILES_DIRECTORY,
        help=f"Output directory for Parquet files (default: {CARD_FILES_DIRECTORY})",
    )

    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate existing output file, don't aggregate",
    )

    parser.add_argument(
        "--incremental",
        "-i",
        action="store_true",
        help="Perform incremental update (only changed files)",
    )

    parser.add_argument(
        "--keep-versions",
        type=int,
        default=3,
        help="Number of historical versions to keep (default: 3)",
    )

    args = parser.parse_args()

    # Initialize aggregator
    aggregator = CardAggregator(output_dir=args.output_dir)

    # Determine output path
    output_path = args.output or f"{args.output_dir}/all_cards.parquet"

    try:
        if args.validate_only:
            # Validation only mode
            logger.info(f"Validating {output_path}...")
            is_valid, errors = aggregator.validate_output(output_path, args.source)

            if is_valid:
                logger.info("✓ Validation passed")
                return 0
            else:
                logger.error("✗ Validation failed:")
                for error in errors:
                    logger.error(f"  - {error}")
                return 1

        elif args.incremental:
            # Incremental update mode
            logger.info("Starting incremental aggregation...")
            metadata_path = f"{args.output_dir}/.aggregate_metadata.json"
            changed_files = aggregator.detect_changes(args.source, metadata_path)

            if not changed_files:
                logger.info("No changes detected, skipping aggregation")
                return 0

            stats = aggregator.incremental_update(changed_files, output_path)

        else:
            # Full aggregation mode
            logger.info("Starting full aggregation...")
            stats = aggregator.aggregate_all(args.source, output_path)

        # Print summary
        print("\n" + "=" * 60)
        print("AGGREGATION SUMMARY")
        print("=" * 60)
        print(f"Files processed:     {stats['files_processed']}")
        print(f"Total cards:         {stats['total_cards']:,}")
        print(f"Duplicates removed:  {stats['duplicates_removed']:,}")
        print(f"File size:           {stats['file_size_mb']:.2f} MB")
        print(f"Time elapsed:        {stats['elapsed_seconds']:.2f} seconds")
        print(f"Output:              {output_path}")
        print("=" * 60)

        # Run validation
        logger.info("\nValidating output...")
        is_valid, errors = aggregator.validate_output(output_path, args.source)

        if is_valid:
            logger.info("✓ Validation passed")
            return 0
        else:
            logger.error("✗ Validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
            return 1

    except FileNotFoundError as e:
        logger.error(f"Error: {e}")
        return 1
    except ValueError as e:
        logger.error(f"Error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
