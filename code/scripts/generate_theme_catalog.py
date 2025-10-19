"""Generate a normalized theme catalog CSV from card datasets.

Outputs `theme_catalog.csv` with deterministic ordering, a reproducible version hash,
and per-source occurrence counts so supplemental theme workflows can reuse the catalog.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    pd = None  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
CODE_ROOT = ROOT / "code"
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

try:
    from code.settings import CSV_DIRECTORY as DEFAULT_CSV_DIRECTORY  # type: ignore
except Exception:  # pragma: no cover - fallback for adhoc execution
    DEFAULT_CSV_DIRECTORY = "csv_files"

# Parquet support requires pandas (imported at top of file, uses pyarrow under the hood)
HAS_PARQUET_SUPPORT = HAS_PANDAS

DEFAULT_OUTPUT_PATH = ROOT / "config" / "themes" / "theme_catalog.csv"
HEADER_COMMENT_PREFIX = "# theme_catalog"


@dataclass(slots=True)
class CatalogRow:
    theme: str
    source_count: int
    commander_count: int
    card_count: int
    last_generated_at: str
    version: str


@dataclass(slots=True)
class CatalogBuildResult:
    rows: List[CatalogRow]
    generated_at: str
    version: str
    output_path: Path


def normalize_theme_display(raw: str) -> str:
    trimmed = " ".join(raw.strip().split())
    return trimmed


def canonical_key(raw: str) -> str:
    return normalize_theme_display(raw).casefold()


def parse_theme_tags(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, str) and v.strip()]
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return []
        # Try JSON parsing first (themeTags often stored as JSON arrays)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(v) for v in parsed if isinstance(v, str) and v.strip()]
        # Fallback to Python literal lists
        try:
            literal = ast.literal_eval(candidate)
        except (ValueError, SyntaxError):
            literal = None
        if isinstance(literal, list):
            return [str(v) for v in literal if isinstance(v, str) and v.strip()]
        return [candidate]
    return []


def _load_theme_counts_from_parquet(
    parquet_path: Path,
    theme_variants: Dict[str, set[str]]
) -> Counter[str]:
    """Load theme counts from a parquet file using pandas (which uses pyarrow).
    
    Args:
        parquet_path: Path to the parquet file (commander_cards.parquet or all_cards.parquet)
        theme_variants: Dict to accumulate theme name variants
        
    Returns:
        Counter of theme occurrences
    """
    if pd is None:
        return Counter()
    
    counts: Counter[str] = Counter()
    
    if not parquet_path.exists():
        return counts
    
    # Read only themeTags column for efficiency
    try:
        df = pd.read_parquet(parquet_path, columns=["themeTags"])
    except Exception:
        # If themeTags column doesn't exist, return empty
        return counts
    
    # Convert to list for fast iteration (faster than iterrows)
    theme_tags_list = df["themeTags"].tolist()
    
    for raw_value in theme_tags_list:
        if raw_value is None or (isinstance(raw_value, float) and pd.isna(raw_value)):
            continue
        tags = parse_theme_tags(raw_value)
        if not tags:
            continue
        seen_in_row: set[str] = set()
        for tag in tags:
            display = normalize_theme_display(tag)
            if not display:
                continue
            key = canonical_key(display)
            if key in seen_in_row:
                continue
            seen_in_row.add(key)
            counts[key] += 1
            theme_variants[key].add(display)
    
    return counts


def _load_theme_counts(csv_path: Path, theme_variants: Dict[str, set[str]]) -> Counter[str]:
    """Load theme counts from CSV file (fallback method).
    
    Args:
        csv_path: Path to CSV file
        theme_variants: Dict to accumulate theme name variants
        
    Returns:
        Counter of theme occurrences
    """
    counts: Counter[str] = Counter()
    if not csv_path.exists():
        return counts
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "themeTags" not in reader.fieldnames:
            return counts
        for row in reader:
            raw_value = row.get("themeTags")
            tags = parse_theme_tags(raw_value)
            if not tags:
                continue
            seen_in_row: set[str] = set()
            for tag in tags:
                display = normalize_theme_display(tag)
                if not display:
                    continue
                key = canonical_key(display)
                if key in seen_in_row:
                    continue
                seen_in_row.add(key)
                counts[key] += 1
                theme_variants[key].add(display)
    return counts


def _select_display_name(options: Sequence[str]) -> str:
    if not options:
        return ""

    def ranking(value: str) -> tuple[int, int, str, str]:
        all_upper = int(value == value.upper())
        title_case = int(value != value.title())
        return (all_upper, title_case, value.casefold(), value)

    return min(options, key=ranking)


def _derive_generated_at(now: Optional[datetime] = None) -> str:
    current = now or datetime.now(timezone.utc)
    without_microseconds = current.replace(microsecond=0)
    iso = without_microseconds.isoformat()
    return iso.replace("+00:00", "Z")


def _compute_version_hash(theme_names: Iterable[str]) -> str:
    joined = "\n".join(sorted(theme_names)).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()[:12]


def build_theme_catalog(
    csv_directory: Path,
    output_path: Path,
    *,
    generated_at: Optional[datetime] = None,
    commander_filename: str = "commander_cards.csv",
    cards_filename: str = "cards.csv",
    logs_directory: Optional[Path] = None,
    use_parquet: bool = True,
    min_card_count: int = 3,
) -> CatalogBuildResult:
    """Build theme catalog from card data.
    
    Args:
        csv_directory: Directory containing CSV files (fallback)
        output_path: Where to write the catalog CSV
        generated_at: Optional timestamp for generation
        commander_filename: Name of commander CSV file
        cards_filename: Name of cards CSV file
        logs_directory: Optional directory to copy output to
        use_parquet: If True, try to use all_cards.parquet first (default: True)
        min_card_count: Minimum number of cards required to include theme (default: 3)
        use_parquet: If True, try to use all_cards.parquet first (default: True)
        
    Returns:
        CatalogBuildResult with generated rows and metadata
    """
    csv_directory = csv_directory.resolve()
    output_path = output_path.resolve()

    theme_variants: Dict[str, set[str]] = defaultdict(set)

    # Try to use parquet file first (much faster)
    used_parquet = False
    if use_parquet and HAS_PARQUET_SUPPORT:
        try:
            # Use processed parquet files (M4 migration)
            parquet_dir = csv_directory.parent / "card_files" / "processed"
            
            # Load all card counts from all_cards.parquet (includes commanders)
            all_cards_parquet = parquet_dir / "all_cards.parquet"
            card_counts = _load_theme_counts_from_parquet(
                all_cards_parquet, theme_variants=theme_variants
            )
            
            # For commander counts, filter all_cards by is_commander column
            if all_cards_parquet.exists() and pd is not None:
                df_commanders = pd.read_parquet(all_cards_parquet)
                df_commanders = df_commanders[df_commanders.get('is_commander', False)]
                commander_counts = Counter()
                for tags in df_commanders['themeTags'].tolist():
                    if tags is None or (isinstance(tags, float) and pd.isna(tags)):
                        continue
                    from code.deck_builder.theme_catalog_loader import parse_theme_tags, normalize_theme_display, canonical_key
                    parsed = parse_theme_tags(tags)
                    if not parsed:
                        continue
                    seen = set()
                    for tag in parsed:
                        display = normalize_theme_display(tag)
                        if not display:
                            continue
                        key = canonical_key(display)
                        if key not in seen:
                            seen.add(key)
                            commander_counts[key] += 1
                            theme_variants[key].add(display)
            else:
                commander_counts = Counter()
            
            used_parquet = True
            print("✓ Loaded theme data from parquet files")
            print(f"  - Commanders: {len(commander_counts)} themes")
            print(f"  - All cards: {len(card_counts)} themes")
            
        except Exception as e:
            print(f"⚠ Failed to load from parquet: {e}")
            print("  Falling back to CSV files...")
            used_parquet = False
    
    # Fallback to CSV files if parquet not available or failed
    if not used_parquet:
        commander_counts = _load_theme_counts(csv_directory / commander_filename, theme_variants)

        card_counts: Counter[str] = Counter()
        cards_path = csv_directory / cards_filename
        if cards_path.exists():
            card_counts = _load_theme_counts(cards_path, theme_variants)
        else:
            # Fallback: scan all *_cards.csv except commander
            for candidate in csv_directory.glob("*_cards.csv"):
                if candidate.name == commander_filename:
                    continue
                card_counts += _load_theme_counts(candidate, theme_variants)
        
        print("✓ Loaded theme data from CSV files")

    keys = sorted(set(card_counts.keys()) | set(commander_counts.keys()))
    generated_at_iso = _derive_generated_at(generated_at)
    display_names = [_select_display_name(sorted(theme_variants[key])) for key in keys]
    version_hash = _compute_version_hash(display_names)

    rows: List[CatalogRow] = []
    filtered_count = 0
    for key, display in zip(keys, display_names):
        if not display:
            continue
        card_count = int(card_counts.get(key, 0))
        commander_count = int(commander_counts.get(key, 0))
        source_count = card_count + commander_count
        
        # Filter out themes below minimum threshold
        if source_count < min_card_count:
            filtered_count += 1
            continue
        
        rows.append(
            CatalogRow(
                theme=display,
                source_count=source_count,
                commander_count=commander_count,
                card_count=card_count,
                last_generated_at=generated_at_iso,
                version=version_hash,
            )
        )

    rows.sort(key=lambda row: (row.theme.casefold(), row.theme))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        comment = (
            f"{HEADER_COMMENT_PREFIX} version={version_hash} "
            f"generated_at={generated_at_iso} total_themes={len(rows)}\n"
        )
        handle.write(comment)
        writer = csv.writer(handle)
        writer.writerow([
            "theme",
            "source_count",
            "commander_count",
            "card_count",
            "last_generated_at",
            "version",
        ])
        for row in rows:
            writer.writerow([
                row.theme,
                row.source_count,
                row.commander_count,
                row.card_count,
                row.last_generated_at,
                row.version,
            ])

    if filtered_count > 0:
        print(f"  Filtered {filtered_count} themes with <{min_card_count} cards")

    if logs_directory is not None:
        logs_directory = logs_directory.resolve()
        logs_directory.mkdir(parents=True, exist_ok=True)
        copy_path = logs_directory / output_path.name
        shutil.copyfile(output_path, copy_path)

    if not rows:
        raise RuntimeError(
            "No theme tags found while generating theme catalog; ensure card CSVs contain a themeTags column."
        )

    return CatalogBuildResult(rows=rows, generated_at=generated_at_iso, version=version_hash, output_path=output_path)


def _resolve_csv_directory(value: Optional[str]) -> Path:
    if value:
        return Path(value)
    env_override = os.environ.get("CSV_FILES_DIR")
    if env_override:
        return Path(env_override)
    return ROOT / DEFAULT_CSV_DIRECTORY


def main(argv: Optional[Sequence[str]] = None) -> CatalogBuildResult:
    parser = argparse.ArgumentParser(description="Generate a normalized theme catalog CSV.")
    parser.add_argument(
        "--csv-dir",
        dest="csv_dir",
        type=Path,
        default=None,
        help="Directory containing card CSV files (defaults to CSV_FILES_DIR or settings.CSV_DIRECTORY)",
    )
    parser.add_argument(
        "--output",
        dest="output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Destination CSV path (defaults to config/themes/theme_catalog.csv)",
    )
    parser.add_argument(
        "--logs-dir",
        dest="logs_dir",
        type=Path,
        default=None,
        help="Optional directory to mirror the generated catalog for diffing (e.g., logs/generated)",
    )
    parser.add_argument(
        "--min-cards",
        dest="min_cards",
        type=int,
        default=3,
        help="Minimum number of cards required to include theme (default: 3)",
    )
    args = parser.parse_args(argv)

    csv_dir = _resolve_csv_directory(str(args.csv_dir) if args.csv_dir else None)
    result = build_theme_catalog(
        csv_directory=csv_dir,
        output_path=args.output,
        logs_directory=args.logs_dir,
        min_card_count=args.min_cards,
    )
    print(
        f"Generated {len(result.rows)} themes -> {result.output_path} (version={result.version})",
        file=sys.stderr,
    )
    return result


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    main()
