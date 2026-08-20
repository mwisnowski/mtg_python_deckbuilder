"""
Apply Oracle Tag adoptions: turns Roadmap 36 Milestone 1's dry-run comparison
report (logs/roadmaps/artifacts/oracle_tag_comparison.json) into real writes
to card_files/processed/all_cards.parquet's themeTags/metadataTags columns.

Two independent decision sources are read from the report, per oracle tag:
- "consolidate_to": existing-tag merges and/or brand-new tag names. Honored
  whenever a human has filled it in, regardless of the tag's classification
  bucket. When empty, falls back to the report's own overlap signal
  (related_local_tag_candidates/related_local_tag), but only for tags
  classified "consolidation_candidate"/"metadata_or_synergy_candidate" (the
  only classifications where that signal is meaningful).
- "possible_metadata_tags": brand-new metadataTag names, always applied
  directly to metadataTags regardless of classification.

Brand-new tag names (not already in our themeTags/metadataTags vocabulary)
from "consolidate_to" are auto-classified theme-vs-metadata via
tag_utils.classify_tag(), optionally overridden by
config/tagging/oracle_tag_adoptions.yml.

This does not run as part of run_full_pipeline(); it's a standalone, opt-in
script. Defaults to a dry run (prints a summary, writes nothing).

Usage:
    # Dry run (default): prints summary, writes nothing
    .venv/Scripts/python.exe code/scripts/apply_oracle_tag_adoptions.py

    # Apply for real (writes all_cards.parquet, creates a timestamped backup)
    .venv/Scripts/python.exe code/scripts/apply_oracle_tag_adoptions.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.scripts.compare_oracle_tags import (  # noqa: E402
    _build_oracle_id_map,
    _normalize,
    fetch_oracle_tags_bulk,
)
from code.tagging.tag_utils import classify_tag  # noqa: E402
from code.tagging.theme_stripper import backup_parquet_file  # noqa: E402

REPORT_PATH = Path("logs/roadmaps/artifacts/oracle_tag_comparison.json")
OVERRIDES_PATH = Path("config/tagging/oracle_tag_adoptions.yml")
PARQUET_PATH = Path("card_files/processed/all_cards.parquet")

# Classifications where related_local_tag/related_local_tag_candidates is a
# meaningful auto-merge signal (the overlap-based candidate/synergy buckets).
ACTIONABLE_CLASSIFICATIONS = {"consolidation_candidate", "metadata_or_synergy_candidate"}

# If related_local_tag_candidates ties across more than this many local tags,
# skip the automatic fallback (too ambiguous) and flag for manual review.
MAX_AUTO_FALLBACK_CANDIDATES = 3


def load_comparison_report(path: Path) -> dict:
    """Read Roadmap 36 Milestone 1's oracle_tag_comparison.json report."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run code/scripts/compare_oracle_tags.py first."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_classification_overrides(path: Path) -> dict[str, str]:
    """Read the optional tag_name -> 'theme'|'metadata' override map.

    Keys are normalized (case/hyphen/underscore-insensitive). Empty dict if
    the file doesn't exist.
    """
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {_normalize(str(k)): str(v).strip().lower() for k, v in data.items()}


def collect_consolidate_to_adoptions(report: dict) -> dict[str, list[str]]:
    """Return {oracle_tag_id: target_tag_names} from each tag's consolidate_to.

    Explicit consolidate_to values are honored for any classification (a
    human decision overrides the auto-classification bucket). When empty,
    falls back to related_local_tag_candidates (capped at
    MAX_AUTO_FALLBACK_CANDIDATES) or related_local_tag, but only for tags
    classified consolidation_candidate/metadata_or_synergy_candidate. Tags
    with neither an explicit value nor a usable fallback are omitted.
    """
    adoptions: dict[str, list[str]] = {}
    for tag in report.get("tags", []):
        tag_id = tag.get("id")
        if not tag_id:
            continue
        targets = tag.get("consolidate_to") or []
        if targets:
            adoptions[tag_id] = list(dict.fromkeys(targets))
            continue
        if tag.get("classification") not in ACTIONABLE_CLASSIFICATIONS:
            continue
        candidates = tag.get("related_local_tag_candidates")
        if candidates:
            if len(candidates) <= MAX_AUTO_FALLBACK_CANDIDATES:
                adoptions[tag_id] = list(dict.fromkeys(candidates))
            continue
        related = tag.get("related_local_tag")
        if related:
            adoptions[tag_id] = [related]
    return adoptions


def find_needs_manual_review(report: dict, consolidate_adoptions: dict[str, list[str]]) -> list[str]:
    """Return oracle tag ids that are candidate/synergy classified but have
    neither an explicit consolidate_to nor a usable fallback (or whose
    related_local_tag_candidates tie exceeded the safety cap).
    """
    return [
        tag["id"]
        for tag in report.get("tags", [])
        if tag.get("classification") in ACTIONABLE_CLASSIFICATIONS
        and tag.get("id") not in consolidate_adoptions
    ]


def collect_possible_metadata_tag_adoptions(report: dict) -> dict[str, list[str]]:
    """Return {oracle_tag_id: metadata_tag_names} from possible_metadata_tags.

    Applies regardless of classification; a tag can have consolidate_to,
    possible_metadata_tags, both, or neither.
    """
    return {
        tag["id"]: list(dict.fromkeys(tag["possible_metadata_tags"]))
        for tag in report.get("tags", [])
        if tag.get("id") and tag.get("possible_metadata_tags")
    }


def resolve_target_column(
    tag_name: str,
    our_tag_vocab_by_column: dict[str, str],
    overrides: dict[str, str],
) -> str:
    """Return 'themeTags' or 'metadataTags' for tag_name.

    If tag_name (case/hyphen/underscore-insensitive) already exists in the
    local vocab, returns the column it already lives in. Otherwise it's a
    brand-new tag: checks overrides first, then falls back to
    classify_tag()'s theme-vs-metadata heuristic.
    """
    norm = _normalize(tag_name)
    existing_column = our_tag_vocab_by_column.get(norm)
    if existing_column:
        return existing_column
    override = overrides.get(norm)
    if override:
        return "metadataTags" if override == "metadata" else "themeTags"
    return "metadataTags" if classify_tag(tag_name) == "metadata" else "themeTags"


def _column_values(val: Any) -> list[str]:
    """Normalize a themeTags/metadataTags cell (list or numpy ndarray) to a list."""
    if hasattr(val, "tolist"):
        return list(val.tolist())
    if isinstance(val, (list, tuple)):
        return list(val)
    return []


def _build_tag_vocab_maps(df: pd.DataFrame) -> tuple[dict[str, str], dict[str, str]]:
    """Return (normalized_name -> column, normalized_name -> canonical casing)
    for every distinct themeTag/metadataTag currently in df.
    """
    column_by_normalized: dict[str, str] = {}
    canonical_by_normalized: dict[str, str] = {}
    for col in ("themeTags", "metadataTags"):
        if col not in df.columns:
            continue
        for val in df[col]:
            for t in _column_values(val):
                norm = _normalize(t)
                if norm not in column_by_normalized:
                    column_by_normalized[norm] = col
                    canonical_by_normalized[norm] = t
    return column_by_normalized, canonical_by_normalized


def apply_adoptions(
    df: pd.DataFrame,
    report: dict,
    tags_bulk: list[dict],
    classification_overrides: dict[str, str],
    dry_run: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Apply consolidate_to + possible_metadata_tags adoptions to df.

    Maps each oracle tag id to matching local cards via tags_bulk's taggings
    (oracle_id) and df's scryfallID column (through the local
    scryfall_bulk_data.json snapshot's scryfallID -> oracle_id mapping).
    Returns (df, summary) when dry_run; otherwise returns (a new, modified
    DataFrame, summary).
    """
    tag_meta = {t["id"]: t for t in report.get("tags", []) if t.get("id")}
    consolidate_adoptions = collect_consolidate_to_adoptions(report)
    metadata_adoptions = collect_possible_metadata_tag_adoptions(report)
    needs_manual_review = find_needs_manual_review(report, consolidate_adoptions)

    scryfall_to_oracle = _build_oracle_id_map()
    oracle_id_to_rows: dict[str, list[int]] = {}
    for pos, sid in enumerate(df["scryfallID"].tolist()):
        oid = scryfall_to_oracle.get(sid)
        if oid:
            oracle_id_to_rows.setdefault(oid, []).append(pos)

    tag_id_to_oracle_ids = {
        t.get("id"): {tg["oracle_id"] for tg in (t.get("taggings") or []) if tg.get("oracle_id")}
        for t in tags_bulk
    }

    def rows_for_tag(tag_id: str) -> set[int]:
        rows: set[int] = set()
        for oid in tag_id_to_oracle_ids.get(tag_id, ()):
            rows.update(oracle_id_to_rows.get(oid, ()))
        return rows

    column_by_normalized, canonical_by_normalized = _build_tag_vocab_maps(df)

    def canonical_name(name: str) -> str:
        norm = _normalize(name)
        if norm in canonical_by_normalized:
            return canonical_by_normalized[norm]
        canonical_by_normalized[norm] = name
        return name

    theme_additions: dict[int, set[str]] = {}
    metadata_additions: dict[int, set[str]] = {}
    newly_created_tags: dict[str, str] = {}
    resolution_stats = {"explicit": 0, "fallback_candidates": 0, "fallback_single": 0}
    cards_affected: set[int] = set()
    tag_applications = 0

    for tag_id, targets in consolidate_adoptions.items():
        rows = rows_for_tag(tag_id)
        if not rows:
            continue
        entry = tag_meta.get(tag_id, {})
        if entry.get("consolidate_to"):
            resolution_stats["explicit"] += 1
        elif entry.get("related_local_tag_candidates"):
            resolution_stats["fallback_candidates"] += 1
        else:
            resolution_stats["fallback_single"] += 1
        for target in targets:
            name = canonical_name(target)
            norm = _normalize(name)
            column = resolve_target_column(name, column_by_normalized, classification_overrides)
            if norm not in column_by_normalized:
                column_by_normalized[norm] = column
                newly_created_tags[name] = column
            bucket = theme_additions if column == "themeTags" else metadata_additions
            for row in rows:
                bucket.setdefault(row, set()).add(name)
                cards_affected.add(row)
                tag_applications += 1

    for tag_id, names in metadata_adoptions.items():
        rows = rows_for_tag(tag_id)
        if not rows:
            continue
        for target in names:
            name = canonical_name(target)
            norm = _normalize(name)
            if norm not in column_by_normalized:
                column_by_normalized[norm] = "metadataTags"
                newly_created_tags[name] = "metadataTags"
            for row in rows:
                metadata_additions.setdefault(row, set()).add(name)
                cards_affected.add(row)
                tag_applications += 1

    summary = {
        "consolidate_to_tags_processed": len(consolidate_adoptions),
        "possible_metadata_tags_processed": len(metadata_adoptions),
        "needs_manual_review": needs_manual_review,
        "resolution_stats": resolution_stats,
        "newly_created_tags": newly_created_tags,
        "cards_affected": len(cards_affected),
        "tag_applications": tag_applications,
    }

    if dry_run:
        return df, summary

    result = df.copy()
    for col_name, additions in (("themeTags", theme_additions), ("metadataTags", metadata_additions)):
        if not additions:
            continue
        current = result[col_name].tolist()
        for row, new_tags in additions.items():
            merged = sorted(set(_column_values(current[row])) | new_tags)
            current[row] = merged
        result[col_name] = pd.Series(current, index=result.index, dtype=object)

    return result, summary


def _print_summary(summary: dict, dry_run: bool) -> None:
    print("=" * 70)
    print(f"{'DRY RUN' if dry_run else 'APPLY'} summary")
    print("=" * 70)
    print(f"consolidate_to tags processed: {summary['consolidate_to_tags_processed']}")
    stats = summary["resolution_stats"]
    print(f"  resolved explicitly: {stats['explicit']}")
    print(f"  resolved via candidate-tie fallback: {stats['fallback_candidates']}")
    print(f"  resolved via single related_local_tag fallback: {stats['fallback_single']}")
    print(f"  needs manual review (no usable value): {len(summary['needs_manual_review'])}")
    print(f"possible_metadata_tags tags processed: {summary['possible_metadata_tags_processed']}")
    if summary["newly_created_tags"]:
        print(f"Newly created tags ({len(summary['newly_created_tags'])}):")
        for name, col in sorted(summary["newly_created_tags"].items()):
            print(f"  {name} -> {col}")
    print(f"Cards affected: {summary['cards_affected']}")
    print(f"Total tag applications: {summary['tag_applications']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply Oracle Tag consolidate_to/possible_metadata_tags adoptions to all_cards.parquet",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes to parquet (default is dry-run)")
    parser.add_argument("--report-path", type=Path, default=REPORT_PATH)
    parser.add_argument("--overrides-path", type=Path, default=OVERRIDES_PATH)
    parser.add_argument("--parquet-path", type=Path, default=PARQUET_PATH)
    parser.add_argument("--no-backup", action="store_true", help="Skip creating a timestamped backup before writing")
    args = parser.parse_args(argv)

    report = load_comparison_report(args.report_path)
    overrides = load_classification_overrides(args.overrides_path)

    if not args.parquet_path.exists():
        print(f"Parquet not found at {args.parquet_path}; run initial_setup() first.")
        return 1
    df = pd.read_parquet(args.parquet_path)

    print("Fetching Oracle Tags bulk file from Scryfall (for per-card taggings)...")
    tags_bulk = fetch_oracle_tags_bulk()

    result_df, summary = apply_adoptions(df, report, tags_bulk, overrides, dry_run=not args.apply)
    _print_summary(summary, dry_run=not args.apply)

    if args.apply:
        if not args.no_backup:
            backup_path = backup_parquet_file(args.parquet_path)
            print(f"Backup created: {backup_path}")
        result_df.to_parquet(args.parquet_path, index=False)
        print(f"Wrote changes to {args.parquet_path}")
    else:
        print("Dry run only, no changes written. Pass --apply to write.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
