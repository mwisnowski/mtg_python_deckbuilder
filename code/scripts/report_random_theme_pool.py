"""Summarize the curated random theme pool and exclusion rules.

Usage examples:

    python -m code.scripts.report_random_theme_pool --format markdown
    python -m code.scripts.report_random_theme_pool --output logs/random_theme_pool.json

The script refreshes the commander catalog, rebuilds the curated random
pool using the same heuristics as Random Mode auto-fill, and prints a
summary (JSON by default).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from deck_builder.random_entrypoint import (  # noqa: E402
    _build_random_theme_pool,
    _ensure_theme_tag_cache,
    _load_commanders_df,
    _OVERREPRESENTED_SHARE_THRESHOLD,
)


def build_report(refresh: bool = False) -> Dict[str, Any]:
    df = _load_commanders_df()
    if refresh:
        # Force re-cache of tag structures
        df = _ensure_theme_tag_cache(df)
    else:
        try:
            df = _ensure_theme_tag_cache(df)
        except Exception:
            pass
    allowed, metadata = _build_random_theme_pool(df, include_details=True)
    detail = metadata.pop("excluded_detail", {})
    report = {
        "allowed_tokens": sorted(allowed),
        "allowed_count": len(allowed),
        "metadata": metadata,
        "excluded_detail": detail,
    }
    return report


def format_markdown(report: Dict[str, Any], *, limit: int = 20) -> str:
    lines: List[str] = []
    meta = report.get("metadata", {})
    rules = meta.get("rules", {})
    lines.append("# Curated Random Theme Pool")
    lines.append("")
    lines.append(f"- Allowed tokens: **{report.get('allowed_count', 0)}**")
    total_commander_count = meta.get("total_commander_count")
    if total_commander_count is not None:
        lines.append(f"- Commander entries analyzed: **{total_commander_count}**")
    coverage = meta.get("coverage_ratio")
    if coverage is not None:
        pct = round(float(coverage) * 100.0, 2)
        lines.append(f"- Coverage: **{pct}%** of catalog tokens")
    if rules:
        thresh = rules.get("overrepresented_share_threshold", _OVERREPRESENTED_SHARE_THRESHOLD)
        thresh_pct = round(float(thresh) * 100.0, 2)
        lines.append("- Exclusion rules:")
        lines.append("  - Minimum commander coverage: 5 unique commanders")
        lines.append(f"  - Kindred filter keywords: {', '.join(rules.get('kindred_keywords', []))}")
        lines.append(f"  - Global theme keywords: {', '.join(rules.get('excluded_keywords', []))}")
        pattern_str = ", ".join(rules.get("excluded_patterns", []))
        if pattern_str:
            lines.append(f"  - Global theme patterns: {pattern_str}")
        lines.append(f"  - Over-represented threshold: ≥ {thresh_pct}% of commanders")
        manual_src = rules.get("manual_exclusions_source")
        manual_groups = rules.get("manual_exclusions") or []
        if manual_src or manual_groups:
            lines.append(f"  - Manual exclusion config: {manual_src or 'config/random_theme_exclusions.yml'}")
        if manual_groups:
            lines.append(f"  - Manual categories: {len(manual_groups)} tracked groups")
    counts = meta.get("excluded_counts", {}) or {}
    if counts:
        lines.append("")
        lines.append("## Excluded tokens by reason")
        lines.append("Reason | Count")
        lines.append("------ | -----")
        for reason, count in sorted(counts.items(), key=lambda item: item[0]):
            lines.append(f"{reason} | {count}")
    samples = meta.get("excluded_samples", {}) or {}
    if samples:
        lines.append("")
        lines.append("## Sample tokens per exclusion reason")
        for reason, tokens in sorted(samples.items(), key=lambda item: item[0]):
            subset = tokens[:limit]
            more = "" if len(tokens) <= limit else f" … (+{len(tokens) - limit})"
            lines.append(f"- **{reason}**: {', '.join(subset)}{more}")
    detail = report.get("excluded_detail", {}) or {}
    if detail:
        lines.append("")
        lines.append("## Detailed exclusions (first few)")
        for token, reasons in list(sorted(detail.items()))[:limit]:
            lines.append(f"- {token}: {', '.join(reasons)}")
        if len(detail) > limit:
            lines.append(f"… (+{len(detail) - limit} more tokens)")
    manual_detail = meta.get("manual_exclusion_detail", {}) or {}
    if manual_detail:
        lines.append("")
        lines.append("## Manual exclusions applied")
        for token, info in sorted(manual_detail.items(), key=lambda item: item[0]):
            display = info.get("display", token)
            category = info.get("category")
            summary = info.get("summary")
            notes = info.get("notes")
            descriptors: List[str] = []
            if category:
                descriptors.append(f"category={category}")
            if summary:
                descriptors.append(summary)
            if notes:
                descriptors.append(notes)
            suffix = f" — {'; '.join(descriptors)}" if descriptors else ""
            lines.append(f"- {display}{suffix}")

    if rules.get("manual_exclusions"):
        lines.append("")
        lines.append("## Manual exclusion categories")
        for group in rules["manual_exclusions"]:
            if not isinstance(group, dict):
                continue
            category = group.get("category", "manual")
            summary = group.get("summary")
            tokens = group.get("tokens", []) or []
            notes = group.get("notes")
            lines.append(f"- **{category}** — {summary or 'no summary provided'}")
            if notes:
                lines.append(f"  - Notes: {notes}")
            if tokens:
                token_list = tokens[:limit]
                more = "" if len(tokens) <= limit else f" … (+{len(tokens) - limit})"
                lines.append(f"  - Tokens: {', '.join(token_list)}{more}")

    return "\n".join(lines)


def write_output(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def write_manual_exclusions(path: Path, report: Dict[str, Any]) -> None:
    meta = report.get("metadata", {}) or {}
    rules = meta.get("rules", {}) or {}
    detail = meta.get("manual_exclusion_detail", {}) or {}
    payload = {
        "source": rules.get("manual_exclusions_source"),
        "categories": rules.get("manual_exclusions", []),
        "tokens": detail,
    }
    write_output(path, payload)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report the curated random theme pool heuristics")
    parser.add_argument("--format", choices={"json", "markdown"}, default="json", help="Output format (default: json)")
    parser.add_argument("--output", type=Path, help="Optional path to write the structured report (JSON regardless of --format)")
    parser.add_argument("--limit", type=int, default=20, help="Max sample tokens per reason when printing markdown (default: 20)")
    parser.add_argument("--refresh", action="store_true", help="Bypass caches when rebuilding commander stats")
    parser.add_argument("--write-exclusions", type=Path, help="Optional path for writing manual exclusion tokens + metadata (JSON)")
    args = parser.parse_args(argv)

    report = build_report(refresh=args.refresh)

    if args.output:
        write_output(args.output, report)

    if args.write_exclusions:
        write_manual_exclusions(args.write_exclusions, report)

    if args.format == "markdown":
        print(format_markdown(report, limit=max(1, args.limit)))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
