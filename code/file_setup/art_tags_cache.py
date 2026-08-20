"""
Art tags cache builder for card detail view / search.

Downloads the Scryfall Art Tags bulk file (community-maintained illustration
tagging project, see https://scryfall.com/docs/tagger-tags) and writes an
`artTags` column directly onto all_cards.parquet, mapping tags to cards by
illustration_id (not oracle_id -- art tags describe the artwork, not the
card's function, so reprints with different art get different tags).

Strategy:
1. GET https://api.scryfall.com/bulk-data  ->  find Art Tags download URL
2. Download the Art Tags bulk JSONL (one Tag object per line, each with a
   list of "taggings" -> [{"illustration_id": ..., "weight": ...}, ...])
3. Build illustration_id -> [tag labels] from it
4. Build scryfallID -> illustration_id from card_files/raw/scryfall_bulk_data.json
5. For each card in all_cards.parquet, write scryfallID -> tags into artTags

Optional, standalone step -- not part of the default full pipeline (mirrors
code/file_setup/rulings_cache.py's rollout pattern), since it requires a
~12 MB bulk download and isn't needed for core deckbuilding.

Usage (standalone):
    python -c "from code.file_setup.art_tags_cache import build_art_tags_cache; build_art_tags_cache()"
"""

import gzip
import json
import logging
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from code.file_setup.scryfall_bulk_data import ScryfallBulkDataClient, resolve_download_uri

logger = logging.getLogger(__name__)

PARQUET_PATH = Path("card_files/processed/all_cards.parquet")
LOCAL_BULK_DATA_PATH = Path("card_files/raw/scryfall_bulk_data.json")

_USER_AGENT = "MTGPythonDeckbuilder/1.0 (contact via GitHub)"


def _get(url: str) -> bytes:
    """Simple HTTP GET with project User-Agent."""
    req = Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=60) as r:
        return r.read()


def build_illustration_id_map() -> dict[str, str]:
    """
    Return scryfallID -> illustration_id using the local scryfall_bulk_data.json.
    Falls back to empty dict if the file is missing.
    """
    if not LOCAL_BULK_DATA_PATH.exists():
        logger.warning(f"{LOCAL_BULK_DATA_PATH} not found; illustration_id mapping unavailable.")
        return {}
    with open(LOCAL_BULK_DATA_PATH, encoding="utf-8") as f:
        cards = json.load(f)
    return {
        card["id"]: card["illustration_id"]
        for card in cards
        if "id" in card and card.get("illustration_id")
    }


def fetch_art_tags_bulk(output_func=None) -> list[dict]:
    """Download and parse the Scryfall Art Tags bulk file.

    Returns a list of Tag objects (id/slug/label/parent_ids/child_ids/taggings);
    each tagging entry has an illustration_id + weight (very_strong/strong/
    median/weak -- not stored or filtered here, Scryfall's own UI doesn't
    surface weight either).
    """
    _log = output_func or (lambda msg: logger.info(msg))
    client = ScryfallBulkDataClient()
    info = client.get_bulk_data_info(bulk_type="art_tags")
    url = resolve_download_uri(info)
    _log(f"Downloading Art Tags bulk file from Scryfall (updated {info.get('updated_at', 'unknown')})\u2026")
    raw = _get(url)
    _log(f"Downloaded {len(raw) / 1_048_576:.1f} MB \u2014 parsing\u2026")
    if url.endswith(".gz"):
        text = gzip.decompress(raw).decode("utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(raw)


def build_art_tags_index(art_tags_bulk: list[dict]) -> dict[str, list[str]]:
    """Return illustration_id -> sorted, deduped list of tag labels.

    Uses each Tag's own `label` directly (Scryfall's labels are already
    space-separated, e.g. "blue glow" for slug "blue-glow" -- lowercase, not
    Title Case, matching how Scryfall's own tagger/search UI displays them),
    falling back to a de-slugged string only if `label` is missing/empty.
    Dedupes case-insensitively (keeps first-seen casing). Includes taggings
    of all weights.
    """
    index: dict[str, dict[str, str]] = {}
    for tag in art_tags_bulk:
        label = tag.get("label") or (tag.get("slug") or "").replace("-", " ").strip()
        if not label:
            continue
        for tagging in tag.get("taggings") or []:
            illustration_id = tagging.get("illustration_id")
            if not illustration_id:
                continue
            bucket = index.setdefault(illustration_id, {})
            key = label.lower()
            if key not in bucket:
                bucket[key] = label
    return {iid: sorted(labels.values()) for iid, labels in index.items()}


def build_art_tags_cache(output_func=None) -> None:
    """
    Write/refresh the `artTags` column on all_cards.parquet from Scryfall's
    Art Tags bulk file. Requires all_cards.parquet + scryfallID to already
    exist (run initial_setup() + refresh_prices_parquet() first).

    Unlike the rulings cache, this writes directly into the shared parquet
    (not a separate JSON side-cache), since artTags needs to be a real,
    filterable/sortable column.

    Args:
        output_func: Optional callable(str) for progress messages.
    """
    _log = output_func or (lambda msg: logger.info(msg))

    if not PARQUET_PATH.exists():
        _log(f"Parquet not found at {PARQUET_PATH}; run initial_setup() first.")
        return

    _log("Loading card data\u2026")
    df = pd.read_parquet(PARQUET_PATH)
    if "scryfallID" not in df.columns:
        _log("scryfallID column missing; run refresh_prices_parquet() first.")
        return

    _log("Building illustration_id map from local Scryfall bulk data\u2026")
    scryfall_to_illustration = build_illustration_id_map()
    _log(f"Mapped {len(scryfall_to_illustration):,} cards to illustration_id.")

    try:
        art_tags_bulk = fetch_art_tags_bulk(output_func=output_func)
    except (HTTPError, URLError, OSError, ValueError) as e:
        _log(f"Failed to download Art Tags bulk file: {e}")
        return

    _log("Indexing art tags by illustration_id\u2026")
    illustration_tags = build_art_tags_index(art_tags_bulk)
    _log(f"Indexed art tags for {len(illustration_tags):,} illustrations.")

    def _lookup(sid) -> list[str]:
        illustration_id = scryfall_to_illustration.get(sid) if sid else None
        if not illustration_id:
            return []
        return illustration_tags.get(illustration_id, [])

    df["artTags"] = df["scryfallID"].apply(_lookup)

    missing = int((df["artTags"].apply(len) == 0).sum())
    if missing:
        _log(f"Note: {missing:,} cards had no art tags (no illustration match or no tags found).")

    df.to_parquet(PARQUET_PATH, engine="pyarrow", compression="snappy", index=False)

    total_tags = int(df["artTags"].apply(len).sum())
    _log(f"Art tags written: {len(df):,} cards processed, {total_tags:,} tag applications total.")
    _log(f"Output: {PARQUET_PATH}")
