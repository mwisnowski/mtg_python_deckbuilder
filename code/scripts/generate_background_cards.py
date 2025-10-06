"""Generate `background_cards.csv` from the master card dataset.

This script filters the full `cards.csv` export for cards whose type line contains
"Background" and writes the filtered rows to `background_cards.csv`. The output
maintains the same columns as the source data, ensures deterministic ordering,
and prepends a metadata comment with version and row count.

Usage (default paths derived from CSV_FILES_DIR environment variable)::

    python -m code.scripts.generate_background_cards
    python -m code.scripts.generate_background_cards --source other/cards.csv --output some/backgrounds.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from path_util import csv_dir

BACKGROUND_KEYWORD = "background"
DEFAULT_SOURCE_NAME = "cards.csv"
DEFAULT_OUTPUT_NAME = "background_cards.csv"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate background cards CSV")
    parser.add_argument(
        "--source",
        type=Path,
        help="Optional override for the source cards.csv file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional override for the generated background_cards.csv file",
    )
    parser.add_argument(
        "--version",
        type=str,
        help="Optional version string to embed in the output metadata comment",
    )
    return parser.parse_args(argv)


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    base = Path(csv_dir()).resolve()
    source = (args.source or (base / DEFAULT_SOURCE_NAME)).resolve()
    output = (args.output or (base / DEFAULT_OUTPUT_NAME)).resolve()
    return source, output


def _is_background_type(type_line: str | None) -> bool:
    if not type_line:
        return False
    return BACKGROUND_KEYWORD in type_line.lower()


def _parse_theme_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    text = raw.strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        body = text[1:-1].strip()
        if not body:
            return []
        tokens = [token.strip(" '\"") for token in body.split(",")]
        return [token for token in tokens if token]
    return [part.strip() for part in text.split(";") if part.strip()]


def _is_background_row(row: Dict[str, str]) -> bool:
    if _is_background_type(row.get("type")):
        return True
    theme_tags = _parse_theme_tags(row.get("themeTags"))
    return any(BACKGROUND_KEYWORD in tag.lower() for tag in theme_tags)


def _row_priority(row: Dict[str, str]) -> tuple[int, int]:
    """Return priority tuple for duplicate selection.

    Prefer rows that explicitly declare a background type line, then those with
    longer oracle text. Higher tuple values take precedence when comparing
    candidates.
    """

    type_line = row.get("type", "") or ""
    has_type = BACKGROUND_KEYWORD in type_line.lower()
    text_length = len((row.get("text") or "").strip())
    return (1 if has_type else 0, text_length)


def _gather_background_rows(reader: csv.DictReader) -> list[Dict[str, str]]:
    selected: Dict[str, Dict[str, str]] = {}
    for row in reader:
        if not row:
            continue
        name = (row.get("name") or "").strip()
        if not name:
            continue
        if not _is_background_row(row):
            continue
        current = selected.get(name.lower())
        if current is None:
            selected[name.lower()] = row
            continue
        if _row_priority(row) > _row_priority(current):
            selected[name.lower()] = row
    ordered_names = sorted(selected.keys())
    return [selected[key] for key in ordered_names]


def _ensure_all_columns(rows: Iterable[Dict[str, str]], headers: List[str]) -> None:
    for row in rows:
        for header in headers:
            row.setdefault(header, "")


def _write_background_csv(output: Path, headers: List[str], rows: List[Dict[str, str]], version: str, source: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    now_utc = _dt.datetime.now(_dt.UTC).replace(microsecond=0)
    metadata = {
        "version": version,
        "count": str(len(rows)),
        "source": source.name,
        "generated": now_utc.isoformat().replace("+00:00", "Z"),
    }
    meta_line = "# " + " ".join(f"{key}={value}" for key, value in metadata.items())
    with output.open("w", encoding="utf-8", newline="") as handle:
        handle.write(meta_line + "\n")
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in headers})


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    source, output = _resolve_paths(args)
    if not source.exists():
        raise FileNotFoundError(f"Source cards CSV not found: {source}")

    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("cards.csv is missing header row")
        rows = _gather_background_rows(reader)
        _ensure_all_columns(rows, list(reader.fieldnames))

    version = args.version or _dt.datetime.now(_dt.UTC).strftime("%Y%m%d")
    _write_background_csv(output, list(reader.fieldnames), rows, version, source)


if __name__ == "__main__":
    main()
