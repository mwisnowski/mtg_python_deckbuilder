"""
Theme Distribution Analysis Script

Analyzes theme distribution across the card catalog and generates reports
showing which themes would be stripped based on minimum card thresholds.

Usage:
    python -m code.scripts.analyze_theme_distribution [--min-cards N] [--output FILE]

Arguments:
    --min-cards N    Minimum card threshold (default: from THEME_MIN_CARDS setting)
    --output FILE    Output file path (default: logs/theme_stripping_analysis.txt)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Set

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from code.settings import THEME_MIN_CARDS, CARD_FILES_PROCESSED_DIR
from code.tagging.theme_stripper import (
    get_theme_card_counts,
    identify_themes_to_strip,
    get_theme_distribution,
    get_themes_by_count
)


def analyze_theme_distribution(min_cards: int = None, output_path: str = None) -> None:
    """
    Analyze theme distribution and generate report.
    
    Args:
        min_cards: Minimum card threshold (defaults to THEME_MIN_CARDS setting)
        output_path: Path to output file (defaults to logs/theme_stripping_analysis.txt)
    """
    if min_cards is None:
        min_cards = THEME_MIN_CARDS
    
    if output_path is None:
        output_path = "logs/theme_stripping_analysis.txt"
    
    print(f"Analyzing theme distribution (min_cards={min_cards})...")
    
    # Find all parquet files
    processed_dir = Path(CARD_FILES_PROCESSED_DIR)
    if not processed_dir.exists():
        print(f"Error: Processed cards directory not found: {processed_dir}")
        print("Please run initial setup first to generate parquet files.")
        sys.exit(1)
    
    parquet_files = list(processed_dir.glob("*.parquet"))
    if not parquet_files:
        print(f"Error: No parquet files found in {processed_dir}")
        print("Please run initial setup first to generate parquet files.")
        sys.exit(1)
    
    print(f"Found {len(parquet_files)} parquet files to analyze")
    
    # Build theme counts
    print("Building theme -> card count mapping...")
    theme_counts = get_theme_card_counts(parquet_files)
    
    if not theme_counts:
        print("Error: No themes found in parquet files")
        sys.exit(1)
    
    print(f"Found {len(theme_counts)} unique themes")
    
    # Identify themes to strip
    themes_to_strip = identify_themes_to_strip(theme_counts, min_cards)
    
    # Get distribution
    distribution = get_theme_distribution(theme_counts)
    
    # Get themes below threshold
    below_threshold = get_themes_by_count(theme_counts, min_cards)
    
    # Generate report
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        # Header
        f.write("=" * 80 + "\n")
        f.write("THEME DISTRIBUTION ANALYSIS REPORT\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Minimum Card Threshold: {min_cards}\n")
        f.write(f"Source: {processed_dir}\n")
        f.write(f"Parquet Files Analyzed: {len(parquet_files)}\n")
        f.write("=" * 80 + "\n\n")
        
        # Summary statistics
        f.write("SUMMARY STATISTICS\n")
        f.write("-" * 80 + "\n")
        f.write(f"Total Themes: {distribution['total']}\n")
        f.write(f"Themes to Strip (< {min_cards} cards): {len(themes_to_strip)}\n")
        f.write(f"Themes to Keep (>= {min_cards} cards): {distribution['total'] - len(themes_to_strip)}\n")
        f.write(f"Percentage to Strip: {len(themes_to_strip) / distribution['total'] * 100:.1f}%\n")
        f.write("\n")
        
        # Distribution by card count
        f.write("DISTRIBUTION BY CARD COUNT\n")
        f.write("-" * 80 + "\n")
        f.write(f"  1 card:  {distribution['1_card']:4d} themes\n")
        f.write(f"  2 cards: {distribution['2_cards']:4d} themes\n")
        f.write(f"  3-4 cards: {distribution['3_4_cards']:4d} themes\n")
        f.write(f"  5-9 cards: {distribution['5_9_cards']:4d} themes\n")
        f.write(f"  10+ cards: {distribution['10_plus']:4d} themes\n")
        f.write(f"  Total:   {distribution['total']:4d} themes\n")
        f.write("\n")
        
        # Themes below threshold
        if below_threshold:
            f.write(f"THEMES BELOW THRESHOLD (< {min_cards} cards)\n")
            f.write("=" * 80 + "\n")
            f.write(f"Total: {len(below_threshold)} themes\n\n")
            
            for theme_id, count, card_list in below_threshold:
                f.write(f"Theme: {theme_id}\n")
                f.write(f"Card Count: {count}\n")
                f.write(f"Cards:\n")
                for card in card_list:
                    f.write(f"  - {card}\n")
                f.write("\n")
        else:
            f.write(f"NO THEMES BELOW THRESHOLD (< {min_cards} cards)\n")
            f.write("=" * 80 + "\n")
            f.write("All themes meet the minimum card requirement.\n\n")
        
        # Recommendations
        f.write("RECOMMENDATIONS\n")
        f.write("=" * 80 + "\n")
        if len(themes_to_strip) > 0:
            f.write(f"• {len(themes_to_strip)} themes should be stripped\n")
            f.write(f"• This represents {len(themes_to_strip) / distribution['total'] * 100:.1f}% of the catalog\n")
            f.write(f"• Run theme stripping to remove these low-viability themes\n")
            f.write(f"• Consider adjusting THEME_MIN_CARDS if this seems too aggressive\n")
        else:
            f.write(f"• No themes below threshold (all themes have >= {min_cards} cards)\n")
            f.write(f"• Consider lowering THEME_MIN_CARDS if you want to strip more themes\n")
        f.write("\n")
        
        # Footer
        f.write("=" * 80 + "\n")
        f.write("END OF REPORT\n")
        f.write("=" * 80 + "\n")
    
    print(f"\nReport generated: {output_file}")
    print(f"\nSummary:")
    print(f"  Total themes: {distribution['total']}")
    print(f"  Themes to strip: {len(themes_to_strip)} ({len(themes_to_strip) / distribution['total'] * 100:.1f}%)")
    print(f"  Themes to keep: {distribution['total'] - len(themes_to_strip)}")
    
    # Print distribution
    print(f"\nDistribution:")
    print(f"  1 card:    {distribution['1_card']:4d} themes")
    print(f"  2 cards:   {distribution['2_cards']:4d} themes")
    print(f"  3-4 cards: {distribution['3_4_cards']:4d} themes")
    print(f"  5-9 cards: {distribution['5_9_cards']:4d} themes")
    print(f"  10+ cards: {distribution['10_plus']:4d} themes")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze theme distribution and identify themes below minimum card threshold"
    )
    parser.add_argument(
        '--min-cards',
        type=int,
        default=None,
        help=f'Minimum card threshold (default: {THEME_MIN_CARDS} from THEME_MIN_CARDS setting)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output file path (default: logs/theme_stripping_analysis.txt)'
    )
    
    args = parser.parse_args()
    
    try:
        analyze_theme_distribution(
            min_cards=args.min_cards,
            output_path=args.output
        )
    except KeyboardInterrupt:
        print("\nAnalysis cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError during analysis: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
