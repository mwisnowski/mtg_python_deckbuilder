"""
Oracle Tag reconciliation: dry-run comparison of Scryfall's Oracle Tags
(community-maintained "Tagger" project, see
https://scryfall.com/docs/tagger-tags) against our own themeTags/metadataTags
vocabulary.

Downloads the Scryfall Oracle Tags bulk file and classifies each tag as
already covered by our own tagging pipeline, a new theme-tag candidate, a new
metadata-tag candidate, not applicable (flavor/lore-only), a parent-only tag
(no direct taggings, only children), a consolidation candidate (cards tagged
with it overwhelmingly already carry one specific local tag, suggesting a
duplicate/synonym rather than something new), a metadata-or-synergy candidate
(same strong overlap, but the tag names a specific mechanic worth tracking as
a finer-grained metadataTag/synergyTag alongside the existing theme), an
insufficient-sample tag (too few local cards to judge, below THEME_MIN_CARDS),
or ambiguous (needs human review).

This is a READ-ONLY report: zero writes to all_cards.parquet, and no tags are
merged into our data by this script. Actual adoption of new tags is a
separate, deferred future roadmap.

Each tag entry includes two fields for manual review, intended to be filled
in directly in this JSON file:
- "consolidate_to": local themeTag/metadataTag name(s) that already exist and
  should be added to the cards carrying this Oracle Tag (a merge/dedup
  decision).
- "possible_metadata_tags": brand-new metadataTag name(s) you're considering
  introducing for this Oracle Tag (does not need to exist in our vocabulary
  yet).
Re-running this script preserves both fields' existing values (matched by
the Oracle Tag's stable id) so review decisions aren't lost when the report
is regenerated.

Re-running also compares the new Oracle Tag ids against the previous report
(if one exists) and logs/records any brand-new Oracle Tags introduced since
the last run, under the report's "new_oracle_tags_since_last_run" key.

Usage (standalone):
    .venv/Scripts/python.exe code/scripts/compare_oracle_tags.py
"""
from __future__ import annotations

import gzip
import json
import logging
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.file_setup.scryfall_bulk_data import ScryfallBulkDataClient, resolve_download_uri  # noqa: E402
from code.settings import THEME_MIN_CARDS  # noqa: E402

logger = logging.getLogger(__name__)

PARQUET_PATH = Path("card_files/processed/all_cards.parquet")
LOCAL_BULK_DATA_PATH = Path("card_files/raw/scryfall_bulk_data.json")
REPORT_PATH = Path("logs/roadmaps/artifacts/oracle_tag_comparison.json")

# Below this fraction of overlap with a single local tag, don't suggest consolidation/synergy.
CONSOLIDATION_OVERLAP_THRESHOLD = 0.6

_USER_AGENT = "MTGPythonDeckbuilder/1.0 (contact via GitHub)"

# Slugs/labels containing these substrings are pure flavor/lore tags, not gameplay function.
# NOTE: hints are matched against normalized text (hyphens/underscores collapsed to spaces).
NOT_APPLICABLE_HINTS = [
    "flavor", "joke", "meme", "you make the card", "card name", "magic term",
    "reference to", "un set", "easter egg",
]
# Keyword hints used only for the rare Oracle Tag that reads as internal/rules-admin.
METADATA_HINTS = ["errata", "reminder text", "rules wording", "templating", "template"]
# Keyword hints for gameplay-function tags (the vast majority of real Oracle Tags).
THEME_HINTS = [
    "ramp", "removal", "draw", "counter", "sacrifice", "tribal", "token",
    "recursion", "graveyard", "combo", "control", "aggro", "lifegain", "mill",
    "tempo", "stax", "wipe", "protection", "tutor", "extra turn", "copy",
    "clone", "discard", "burn", "aristocrat", "voltron", "aura", "equipment",
    "vehicle", "landfall", "blink", "flicker", "reanimat", "theft", "steal",
]


def _get(url: str) -> bytes:
    """Simple HTTP GET with project User-Agent."""
    req = Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=60) as r:
        return r.read()


def fetch_oracle_tags_bulk() -> list[dict]:
    """Download and parse the Scryfall Oracle Tags bulk file.

    Returns a list of Tag objects (id/slug/label/type/parent_ids/child_ids/taggings).
    """
    client = ScryfallBulkDataClient()
    info = client.get_bulk_data_info(bulk_type="oracle_tags")
    url = resolve_download_uri(info)
    raw = _get(url)
    if url.endswith(".gz"):
        text = gzip.decompress(raw).decode("utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(raw)


def _build_oracle_id_map() -> dict[str, str]:
    """Return scryfallID -> oracle_id using the local scryfall_bulk_data.json."""
    if not LOCAL_BULK_DATA_PATH.exists():
        logger.warning(f"{LOCAL_BULK_DATA_PATH} not found; oracle_id mapping unavailable.")
        return {}
    with open(LOCAL_BULK_DATA_PATH, encoding="utf-8") as f:
        cards = json.load(f)
    return {
        card["id"]: card["oracle_id"]
        for card in cards
        if "id" in card and "oracle_id" in card
    }


def build_oracle_id_to_local_tags_map(df: pd.DataFrame) -> dict[str, set[str]]:
    """Return oracle_id -> combined set of that card's themeTags + metadataTags.

    Only includes oracle_ids resolvable from the local scryfall_bulk_data.json
    snapshot; cards with no matching scryfallID are skipped.
    """
    scryfall_to_oracle = _build_oracle_id_map()
    result: dict[str, set[str]] = {}
    for _, row in df.iterrows():
        sid = row.get("scryfallID")
        oracle_id = scryfall_to_oracle.get(sid) if sid else None
        if not oracle_id:
            continue
        tags: set[str] = set()
        for col in ("themeTags", "metadataTags"):
            val = row.get(col)
            if isinstance(val, (list, tuple)):
                tags.update(val)
            elif hasattr(val, "tolist"):  # numpy ndarray from parquet round-trip
                tags.update(val.tolist())
        result.setdefault(oracle_id, set()).update(tags)
    return result


def _normalize(text: str) -> str:
    """Lowercase and collapse hyphens/underscores/whitespace for fuzzy comparison."""
    return re.sub(r"[\s_-]+", " ", (text or "").strip().lower())


def _build_tag_vocab(df: pd.DataFrame) -> set[str]:
    """Return the normalized set of every distinct themeTag/metadataTag in use."""
    vocab: set[str] = set()
    for col in ("themeTags", "metadataTags"):
        if col not in df.columns:
            continue
        for val in df[col]:
            if isinstance(val, (list, tuple)):
                vocab.update(_normalize(t) for t in val)
            elif hasattr(val, "tolist"):
                vocab.update(_normalize(t) for t in val.tolist())
    return vocab


def classify_oracle_tag_candidate(tag_label: str, tag_slug: str, our_tag_vocab: set[str]) -> str:
    """Classify a Scryfall Oracle Tag against our own tag vocabulary.

    Returns one of: "already_covered", "new_theme_candidate",
    "new_metadata_candidate", "not_applicable", "ambiguous".

    Deliberately conservative: falls back to "ambiguous" rather than guessing
    when no clear keyword signal is present, since this is a review report,
    not an auto-classifier.
    """
    normalized_label = _normalize(tag_label)
    normalized_slug = _normalize(tag_slug)
    if normalized_label in our_tag_vocab or normalized_slug in our_tag_vocab:
        return "already_covered"
    haystack = f"{normalized_label} {normalized_slug}"
    if any(hint in haystack for hint in NOT_APPLICABLE_HINTS):
        return "not_applicable"
    if any(hint in haystack for hint in METADATA_HINTS):
        return "new_metadata_candidate"
    if any(hint in haystack for hint in THEME_HINTS):
        return "new_theme_candidate"
    return "ambiguous"


def find_related_local_tag(
    taggings: list[dict], oracle_local_map: dict[str, set[str]]
) -> tuple[str | None, float, int, list[str]]:
    """Find the local tag most commonly already carried by cards with this Oracle Tag.

    Returns (dominant_local_tag, overlap_fraction, resolved_card_count, tied_tags).
    The fraction is dominant_tag_count / resolved_card_count (cards we could
    map to an oracle_id with known local tags). When multiple local tags tie
    for the highest overlap (common for small samples), dominant_local_tag is
    the alphabetically-first of the tie (for deterministic output) and
    tied_tags lists all of them so a human reviewer can see the full picture.
    Returns (None, 0.0, 0, []) when no cards resolve or none carry local tags.
    """
    resolved_tag_sets = [
        oracle_local_map[t["oracle_id"]]
        for t in taggings
        if t.get("oracle_id") in oracle_local_map
    ]
    resolved_count = len(resolved_tag_sets)
    if not resolved_count:
        return None, 0.0, 0, []
    counter: Counter[str] = Counter()
    for tags in resolved_tag_sets:
        counter.update(tags)
    if not counter:
        return None, 0.0, resolved_count, []
    max_count = max(counter.values())
    tied_tags = sorted(t for t, c in counter.items() if c == max_count)
    return tied_tags[0], max_count / resolved_count, resolved_count, tied_tags


def write_comparison_report(results: dict, path: Path) -> None:
    """Write the oracle tag comparison report as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


# Fields a human fills in directly in the JSON report; preserved across re-runs.
MANUAL_REVIEW_FIELDS = ["consolidate_to", "possible_metadata_tags"]


def _load_previous_manual_fields(path: Path) -> dict[str, dict[str, list[str]]]:
    """Return tag id -> {field: value} for MANUAL_REVIEW_FIELDS from a prior
    report, so manual review decisions survive re-running this script
    (Oracle Tag ids are stable).
    """
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            previous = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    result: dict[str, dict[str, list[str]]] = {}
    for t in previous.get("tags", []):
        tag_id = t.get("id")
        if not tag_id:
            continue
        filled_in = {field: t[field] for field in MANUAL_REVIEW_FIELDS if t.get(field)}
        if filled_in:
            result[tag_id] = filled_in
    return result


def _load_previous_tag_ids(path: Path) -> set[str]:
    """Return the set of Oracle Tag ids present in a prior report, so newly
    introduced Oracle Tags can be flagged. Empty set if no prior report.
    """
    if not path.exists():
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            previous = json.load(f)
    except (OSError, json.JSONDecodeError):
        return set()
    return {t.get("id") for t in previous.get("tags", []) if t.get("id")}


def compare_oracle_tags(output_func=None) -> dict:
    """Run the full dry-run Oracle Tag reconciliation and write the report.

    Returns the report dict (also written to REPORT_PATH). Makes zero writes
    to all_cards.parquet.
    """
    _log = output_func or (lambda msg: logger.info(msg))

    if not PARQUET_PATH.exists():
        _log(f"Parquet not found at {PARQUET_PATH}; run initial_setup() first.")
        return {}
    if not LOCAL_BULK_DATA_PATH.exists():
        _log(f"{LOCAL_BULK_DATA_PATH} not found; run initial_setup() first to fetch it.")
        return {}

    _log("Loading card data\u2026")
    df = pd.read_parquet(PARQUET_PATH, columns=["scryfallID", "themeTags", "metadataTags"])
    our_tag_vocab = _build_tag_vocab(df)
    _log(f"Local tag vocabulary: {len(our_tag_vocab)} distinct tags.")

    _log("Mapping oracle_id -> local tags\u2026")
    oracle_local_map = build_oracle_id_to_local_tags_map(df)
    _log(f"Resolved {len(oracle_local_map):,} local cards to an oracle_id.")

    _log("Fetching Oracle Tags bulk-data info\u2026")
    try:
        bulk_info = ScryfallBulkDataClient().get_bulk_data_info(bulk_type="oracle_tags")
    except Exception as e:
        _log(f"Failed to fetch Oracle Tags bulk-data info: {e}")
        return {}

    _log("Downloading Oracle Tags bulk file from Scryfall\u2026")
    try:
        tags_bulk = fetch_oracle_tags_bulk()
    except Exception as e:
        _log(f"Failed to download Oracle Tags bulk file: {e}")
        return {}
    _log(f"Downloaded {len(tags_bulk):,} Oracle Tags.")

    previous_manual_fields = _load_previous_manual_fields(REPORT_PATH)
    had_previous_report = REPORT_PATH.exists()
    previous_tag_ids = _load_previous_tag_ids(REPORT_PATH)

    tag_results: list[dict] = []
    counts: dict[str, int] = {}
    for tag in tags_bulk:
        taggings = tag.get("taggings") or []
        child_ids = tag.get("child_ids") or []
        local_match_count = sum(
            1 for t in taggings if t.get("oracle_id") in oracle_local_map
        )

        matched_tag = None
        related_local_tag = None
        related_local_tag_overlap = 0.0
        related_local_tag_candidates = None
        would_be_classification = None
        if not taggings and child_ids:
            # Parent-only tag: no direct taggings, rolls up via child_ids instead.
            classification = "skipped_parent_only"
        else:
            classification = classify_oracle_tag_candidate(
                tag.get("label", ""), tag.get("slug", ""), our_tag_vocab
            )
            if classification == "already_covered":
                normalized_label = _normalize(tag.get("label", ""))
                normalized_slug = _normalize(tag.get("slug", ""))
                matched_tag = normalized_label if normalized_label in our_tag_vocab else normalized_slug
            elif classification == "not_applicable":
                pass
            else:
                # Compute overlap regardless of sample size, so even discarded
                # low-sample tags still show what they'd relate to.
                related_local_tag, related_local_tag_overlap, _, tied_tags = find_related_local_tag(
                    taggings, oracle_local_map
                )
                if len(tied_tags) > 1:
                    related_local_tag_candidates = tied_tags
                if local_match_count < THEME_MIN_CARDS:
                    # Too few of our cards would get this tag to judge usefully; discard as one-off.
                    would_be_classification = classification
                    classification = "insufficient_sample"
                elif related_local_tag and related_local_tag_overlap >= CONSOLIDATION_OVERLAP_THRESHOLD:
                    if classification == "new_theme_candidate":
                        # Names a specific mechanic, but cards already share one dominant local
                        # tag: likely a finer-grained metadataTag/synergyTag, not a new theme.
                        classification = "metadata_or_synergy_candidate"
                    else:
                        # No specific mechanic signal and strong overlap: likely a duplicate/synonym.
                        classification = "consolidation_candidate"

        counts[classification] = counts.get(classification, 0) + 1
        tag_results.append({
            "id": tag.get("id"),
            "slug": tag.get("slug"),
            "label": tag.get("label"),
            "type": tag.get("type"),
            "total_taggings": len(taggings),
            "local_taggings_matched": local_match_count,
            "child_ids": child_ids,
            "classification": classification,
            "matched_local_tag": matched_tag,
            "related_local_tag": related_local_tag,
            "related_local_tag_overlap": round(related_local_tag_overlap, 3) if related_local_tag else None,
            "related_local_tag_candidates": related_local_tag_candidates,
            "would_be_classification": would_be_classification,
            "consolidate_to": previous_manual_fields.get(tag.get("id"), {}).get("consolidate_to", []),
            "possible_metadata_tags": previous_manual_fields.get(tag.get("id"), {}).get("possible_metadata_tags", []),
        })

    new_tags_info: list[dict] = []
    if had_previous_report:
        new_tags_info = [t for t in tag_results if t["id"] not in previous_tag_ids]
        if new_tags_info:
            slugs = ", ".join(t["slug"] for t in new_tags_info[:20])
            more = " …" if len(new_tags_info) > 20 else ""
            _log(f"ALERT: {len(new_tags_info)} new Oracle Tag(s) found since last run: {slugs}{more}")
        else:
            _log("No new Oracle Tags found since last run.")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "oracle_tags_bulk_updated_at": bulk_info.get("updated_at"),
        "local_tag_vocab_size": len(our_tag_vocab),
        "local_cards_resolved_to_oracle_id": len(oracle_local_map),
        "classification_counts": counts,
        "new_oracle_tags_since_last_run": [
            {"id": t["id"], "slug": t["slug"], "label": t["label"], "classification": t["classification"]}
            for t in new_tags_info
        ],
        "tags": tag_results,
    }
    write_comparison_report(report, REPORT_PATH)
    _log(f"Report written: {REPORT_PATH}")
    _log(f"Classification counts: {counts}")
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    compare_oracle_tags(output_func=print)
