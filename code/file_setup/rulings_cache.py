"""
Rulings cache builder for card detail view.

Downloads the Scryfall rulings bulk file (~25 MB, one request) and maps
rulings to the cards in our dataset by oracle_id. This is far more efficient
than making per-card API calls and stays within Scryfall's guidelines.

Strategy:
1. GET https://api.scryfall.com/bulk-data  →  find rulings download URL
2. Download the rulings bulk JSON
3. Build oracle_id → [rulings] from it
4. Build scryfallID → oracle_id from card_files/raw/scryfall_bulk_data.json
5. For each card in all_cards.parquet, write scryfallID → rulings to cache

The live fallback in code/web/services/rulings.py handles individual cache
misses (new cards not yet in a bulk snapshot).

Usage (standalone):
    python -c "from code.file_setup.rulings_cache import build_rulings_cache; build_rulings_cache()"
"""

import json
import logging
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

logger = logging.getLogger(__name__)

SCRYFALL_BULK_DATA_API = "https://api.scryfall.com/bulk-data"
RULINGS_CACHE_PATH = Path("card_files/processed/rulings_cache.json")
PARQUET_PATH = Path("card_files/processed/all_cards.parquet")
LOCAL_BULK_DATA_PATH = Path("card_files/raw/scryfall_bulk_data.json")

_USER_AGENT = "MTGPythonDeckbuilder/1.0 (contact via GitHub)"


def _get(url: str) -> bytes:
    """Simple HTTP GET with project User-Agent."""
    req = Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=60) as r:
        return r.read()


def _fetch_rulings_bulk_url() -> str:
    """Fetch the current rulings bulk-data download URL from Scryfall."""
    data = json.loads(_get(SCRYFALL_BULK_DATA_API))
    for item in data.get("data", []):
        if item.get("type") == "rulings":
            return item["download_uri"]
    raise ValueError("Rulings bulk-data entry not found in Scryfall API response.")


def _download_rulings_bulk(url: str, output_func=None) -> list[dict]:
    """Download and parse the Scryfall rulings bulk JSON file."""
    _log = output_func or (lambda msg: logger.info(msg))
    _log(f"Downloading rulings bulk file from Scryfall…")
    raw = _get(url)
    _log(f"Downloaded {len(raw) / 1_048_576:.1f} MB — parsing…")
    return json.loads(raw)


def _build_oracle_id_map() -> dict[str, str]:
    """
    Return scryfallID -> oracle_id using the local scryfall_bulk_data.json.
    Falls back to empty dict if the file is missing.
    """
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


def build_rulings_cache(output_func=None) -> None:
    """
    Build card_files/processed/rulings_cache.json from the Scryfall rulings
    bulk file.  Requires all_cards.parquet to exist (run initial_setup first).

    One bulk download (~25 MB) replaces thousands of individual API calls.
    This is an optional, standalone step — NOT part of the default pipeline.

    Args:
        output_func: Optional callable(str) for progress messages.
    """
    _log = output_func or (lambda msg: logger.info(msg))

    if not PARQUET_PATH.exists():
        _log(f"Parquet not found at {PARQUET_PATH}; run initial_setup() first.")
        return

    # Step 1: cards we care about
    _log("Loading card data…")
    df = pd.read_parquet(PARQUET_PATH, columns=["scryfallID"])
    our_ids: set[str] = {
        str(sid) for sid in df["scryfallID"].dropna().unique() if sid
    }
    _log(f"Found {len(our_ids)} unique Scryfall IDs in dataset.")

    # Step 2: scryfallID → oracle_id map (from local bulk data)
    _log("Building oracle_id map from local Scryfall bulk data…")
    scryfall_to_oracle = _build_oracle_id_map()
    _log(f"Mapped {len(scryfall_to_oracle):,} cards to oracle_id.")

    # Step 3: download rulings bulk file
    try:
        rulings_url = _fetch_rulings_bulk_url()
        rulings_raw = _download_rulings_bulk(rulings_url, output_func=output_func)
    except (HTTPError, URLError, OSError, ValueError) as e:
        _log(f"Failed to download rulings bulk file: {e}")
        return

    # Step 4: build oracle_id → [rulings] index
    _log("Indexing rulings by oracle_id…")
    oracle_rulings: dict[str, list[dict]] = {}
    for entry in rulings_raw:
        oid = entry.get("oracle_id", "")
        if not oid:
            continue
        oracle_rulings.setdefault(oid, []).append({
            "published_at": entry.get("published_at", ""),
            "source": entry.get("source", ""),
            "comment": entry.get("comment", ""),
        })
    _log(f"Indexed rulings for {len(oracle_rulings):,} oracle IDs.")

    # Step 5: build scryfallID → rulings cache for our cards only
    cache: dict[str, list[dict]] = {}
    missing_oracle = 0
    for sid in our_ids:
        oracle_id = scryfall_to_oracle.get(sid)
        if oracle_id:
            cache[sid] = oracle_rulings.get(oracle_id, [])
        else:
            cache[sid] = []
            missing_oracle += 1

    if missing_oracle:
        _log(f"Note: {missing_oracle} cards had no oracle_id in local bulk data (live fallback will handle them).")

    RULINGS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RULINGS_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)

    total_rulings = sum(len(v) for v in cache.values())
    _log(f"Rulings cache written: {len(cache):,} cards, {total_rulings:,} rulings total.")
    _log(f"Output: {RULINGS_CACHE_PATH}")
