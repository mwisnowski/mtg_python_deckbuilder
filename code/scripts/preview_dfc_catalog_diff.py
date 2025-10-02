"""Catalog diff helper for verifying multi-face merge output.

This utility regenerates the card CSV catalog (optionally writing compatibility
snapshots) and then compares the merged outputs against the baseline snapshots.
It is intended to support the MDFC rollout checklist by providing a concise summary
of how many rows were merged, which cards collapsed into a single record, and
whether any tag unions diverge from expectations.

Example usage (from repo root, inside virtualenv):

    python -m code.scripts.preview_dfc_catalog_diff --compat-snapshot --output logs/dfc_catalog_diff.json

The script prints a human readable summary to stdout and optionally writes a JSON
artifact for release/staging review.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import pandas as pd

from settings import COLORS, CSV_DIRECTORY

DEFAULT_COMPAT_DIR = Path(os.getenv("DFC_COMPAT_DIR", "csv_files/compat_faces"))
CSV_ROOT = Path(CSV_DIRECTORY)


def _parse_list_cell(value: Any) -> List[str]:
    """Convert serialized list cells ("['A', 'B']") into Python lists."""
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    if isinstance(value, float) and pd.isna(value):  # type: ignore[arg-type]
        return []
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return [text]
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return [str(parsed)]


def _load_catalog(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Catalog file missing: {path}")
    df = pd.read_csv(path)
    for column in ("themeTags", "keywords", "creatureTypes"):
        if column in df.columns:
            df[column] = df[column].apply(_parse_list_cell)
    return df


def _multi_face_names(df: pd.DataFrame) -> List[str]:
    counts = Counter(df.get("name", []))
    return [name for name, count in counts.items() if isinstance(name, str) and count > 1]


def _collect_tags(series: Iterable[List[str]]) -> List[str]:
    tags: List[str] = []
    for value in series:
        if isinstance(value, list):
            tags.extend(str(item) for item in value)
    return sorted(set(tags))


def _summarize_color(
    color: str,
    merged: pd.DataFrame,
    baseline: pd.DataFrame,
    sample_size: int,
) -> Dict[str, Any]:
    merged_names = set(merged.get("name", []))
    baseline_names = list(baseline.get("name", []))
    baseline_name_set = set(name for name in baseline_names if isinstance(name, str))

    multi_face = _multi_face_names(baseline)
    collapsed = []
    tag_mismatches: List[str] = []
    missing_after_merge: List[str] = []

    for name in multi_face:
        group = baseline[baseline["name"] == name]
        merged_row = merged[merged["name"] == name]
        if merged_row.empty:
            missing_after_merge.append(name)
            continue
        expected_tags = _collect_tags(group["themeTags"]) if "themeTags" in group else []
        merged_tags = _collect_tags(merged_row.iloc[[0]]["themeTags"]) if "themeTags" in merged_row else []
        if expected_tags != merged_tags:
            tag_mismatches.append(name)
        collapsed.append(name)

    removed_names = sorted(baseline_name_set - merged_names)
    added_names = sorted(merged_names - baseline_name_set)

    return {
        "rows_merged": len(merged),
        "rows_baseline": len(baseline),
        "row_delta": len(merged) - len(baseline),
        "multi_face_groups": len(multi_face),
        "collapsed_sample": collapsed[:sample_size],
        "tag_union_mismatches": tag_mismatches[:sample_size],
        "missing_after_merge": missing_after_merge[:sample_size],
        "removed_names": removed_names[:sample_size],
        "added_names": added_names[:sample_size],
    }


def _refresh_catalog(colors: Sequence[str], compat_snapshot: bool) -> None:
    os.environ.pop("ENABLE_DFC_MERGE", None)
    os.environ["DFC_COMPAT_SNAPSHOT"] = "1" if compat_snapshot else "0"
    importlib.invalidate_caches()
    # Reload tagger to pick up the new env var
    tagger = importlib.import_module("code.tagging.tagger")
    tagger = importlib.reload(tagger)  # type: ignore[assignment]

    for color in colors:
        tagger.load_dataframe(color)


def generate_diff(
    colors: Sequence[str],
    compat_dir: Path,
    sample_size: int,
) -> Dict[str, Any]:
    per_color: Dict[str, Any] = {}
    overall = {
        "total_rows_merged": 0,
        "total_rows_baseline": 0,
        "total_multi_face_groups": 0,
        "colors": len(colors),
        "tag_union_mismatches": 0,
        "missing_after_merge": 0,
    }

    for color in colors:
        merged_path = CSV_ROOT / f"{color}_cards.csv"
        baseline_path = compat_dir / f"{color}_cards_unmerged.csv"
        merged_df = _load_catalog(merged_path)
        baseline_df = _load_catalog(baseline_path)
        summary = _summarize_color(color, merged_df, baseline_df, sample_size)
        per_color[color] = summary
        overall["total_rows_merged"] += summary["rows_merged"]
        overall["total_rows_baseline"] += summary["rows_baseline"]
        overall["total_multi_face_groups"] += summary["multi_face_groups"]
        overall["tag_union_mismatches"] += len(summary["tag_union_mismatches"])
        overall["missing_after_merge"] += len(summary["missing_after_merge"])

    overall["row_delta_total"] = overall["total_rows_merged"] - overall["total_rows_baseline"]
    return {"overall": overall, "per_color": per_color}


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Preview merged vs baseline DFC catalog diff")
    parser.add_argument(
        "--skip-refresh",
        action="store_true",
        help="Skip rebuilding the catalog in compatibility mode (requires existing compat snapshots)",
    )
    parser.add_argument(
        "--mode",
        default="",
        help="[Deprecated] Legacy ENABLE_DFC_MERGE value (compat|1|0 etc.)",
    )
    parser.add_argument(
        "--compat-snapshot",
        dest="compat_snapshot",
        action="store_true",
        help="Write compatibility snapshots before diffing (default: off unless legacy --mode compat)",
    )
    parser.add_argument(
        "--no-compat-snapshot",
        dest="compat_snapshot",
        action="store_false",
        help="Skip compatibility snapshots even if legacy --mode compat is supplied",
    )
    parser.set_defaults(compat_snapshot=None)
    parser.add_argument(
        "--colors",
        nargs="*",
        help="Optional subset of colors to diff (defaults to full COLORS list)",
    )
    parser.add_argument(
        "--compat-dir",
        type=Path,
        default=DEFAULT_COMPAT_DIR,
        help="Directory containing unmerged compatibility snapshots (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON file to write with the diff summary",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=10,
        help="Number of sample entries to include per section (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    colors = tuple(args.colors) if args.colors else tuple(COLORS)
    compat_dir = args.compat_dir

    mode = str(args.mode or "").strip().lower()
    if mode and mode not in {"compat", "dual", "both", "1", "on", "true", "0", "off", "false", "disabled"}:
        print(
            f"ℹ Legacy --mode value '{mode}' detected; merge remains enabled. Use --compat-snapshot as needed.",
            flush=True,
        )

    if args.compat_snapshot is None:
        compat_snapshot = mode in {"compat", "dual", "both"}
    else:
        compat_snapshot = args.compat_snapshot
        if mode:
            print(
                "ℹ Ignoring deprecated --mode value because --compat-snapshot/--no-compat-snapshot was supplied.",
                flush=True,
            )

    if mode in {"0", "off", "false", "disabled"}:
        print(
            "⚠ ENABLE_DFC_MERGE=off is deprecated; the merge remains enabled regardless of the value.",
            flush=True,
        )

    if not args.skip_refresh:
        start = time.perf_counter()
        _refresh_catalog(colors, compat_snapshot)
        duration = time.perf_counter() - start
        snapshot_msg = "with compat snapshot" if compat_snapshot else "merged-only"
        print(f"✔ Refreshed catalog in {duration:.1f}s ({snapshot_msg})")
    else:
        print("ℹ Using existing catalog outputs (refresh skipped)")

    try:
        diff = generate_diff(colors, compat_dir, args.sample_size)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        print("Run without --skip-refresh (or ensure compat snapshots exist).", file=sys.stderr)
        return 2

    overall = diff["overall"]
    print("\n=== DFC Catalog Diff Summary ===")
    print(
        f"Merged rows: {overall['total_rows_merged']:,} | Baseline rows: {overall['total_rows_baseline']:,} | "
        f"Δ rows: {overall['row_delta_total']:,}"
    )
    print(
        f"Multi-face groups: {overall['total_multi_face_groups']:,} | "
        f"Tag union mismatches: {overall['tag_union_mismatches']} | Missing after merge: {overall['missing_after_merge']}"
    )

    for color, summary in diff["per_color"].items():
        print(f"\n[{color}] baseline={summary['rows_baseline']} merged={summary['rows_merged']} Δ={summary['row_delta']}")
        if summary["multi_face_groups"]:
            print(f"  multi-face groups: {summary['multi_face_groups']}")
        if summary["collapsed_sample"]:
            sample = ", ".join(summary["collapsed_sample"][:3])
            print(f"  collapsed sample: {sample}")
        if summary["tag_union_mismatches"]:
            print(f"  TAG MISMATCH sample: {', '.join(summary['tag_union_mismatches'])}")
        if summary["missing_after_merge"]:
            print(f"  MISSING sample: {', '.join(summary['missing_after_merge'])}")
        if summary["removed_names"]:
            print(f"  removed sample: {', '.join(summary['removed_names'])}")
        if summary["added_names"]:
            print(f"  added sample: {', '.join(summary['added_names'])}")

    if args.output:
        payload = {
            "captured_at": int(time.time()),
            "mode": args.mode,
            "colors": colors,
            "compat_dir": str(compat_dir),
            "summary": diff,
        }
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            print(f"\n📄 Wrote JSON summary to {args.output}")
        except Exception as exc:  # pragma: no cover
            print(f"Failed to write output file {args.output}: {exc}", file=sys.stderr)
            return 3

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
