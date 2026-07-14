"""
Rulings lookup service for the card detail view.

Strategy (hybrid):
1. Load rulings_cache.json once at startup (module-level singleton).
2. On cache hit: return immediately, no network.
3. On cache miss: fetch live from Scryfall, cache result in memory for the
   process lifetime (not written to disk — persisted on next pipeline run).

Live fetches are rate-limited to ≤10 req/s using an asyncio.Lock.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RULINGS_CACHE_PATH = Path("card_files/processed/rulings_cache.json")
SCRYFALL_RULINGS_URL = "https://api.scryfall.com/cards/{scryfall_id}/rulings"
_RATE_LIMIT_INTERVAL = 0.1  # 100ms between live fetches (10 req/s)
_USER_AGENT = "MTGPythonDeckbuilder/1.0 (contact via GitHub)"

# Module-level in-memory cache (loaded once)
_rulings_cache: dict[str, list[dict]] | None = None
_cache_lock = asyncio.Lock()
_last_live_fetch: float = 0.0
_live_lock = asyncio.Lock()


def load_rulings_cache() -> dict[str, list[dict]]:
    """Read rulings_cache.json from disk. Returns empty dict if not found."""
    if not RULINGS_CACHE_PATH.exists():
        logger.debug("rulings_cache.json not found; live fallback will be used.")
        return {}
    try:
        with open(RULINGS_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Could not load rulings cache: {e}")
        return {}


async def _ensure_cache_loaded() -> dict[str, list[dict]]:
    """Lazily load the on-disk cache (thread-safe, loads once)."""
    global _rulings_cache
    if _rulings_cache is None:
        async with _cache_lock:
            if _rulings_cache is None:  # double-checked locking
                _rulings_cache = load_rulings_cache()
    return _rulings_cache


async def _live_fetch(scryfall_id: str) -> list[dict]:
    """Fetch rulings from Scryfall live. Rate-limited; returns [] on error."""
    global _last_live_fetch
    async with _live_lock:
        now = time.monotonic()
        wait = _RATE_LIMIT_INTERVAL - (now - _last_live_fetch)
        if wait > 0:
            await asyncio.sleep(wait)

        url = SCRYFALL_RULINGS_URL.format(scryfall_id=scryfall_id)
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": _USER_AGENT}, timeout=10.0
            ) as client:
                resp = await client.get(url)
                _last_live_fetch = time.monotonic()
                if resp.status_code == 404:
                    return []
                resp.raise_for_status()
                data = resp.json()
                return [
                    {
                        "published_at": r.get("published_at", ""),
                        "source": r.get("source", ""),
                        "comment": r.get("comment", ""),
                    }
                    for r in data.get("data", [])
                ]
        except httpx.HTTPError as e:
            logger.warning(f"Scryfall rulings fetch failed for {scryfall_id}: {e}")
            return []
        except Exception as e:
            logger.warning(f"Unexpected error fetching rulings for {scryfall_id}: {e}")
            return []


async def get_rulings(scryfall_id: str) -> list[dict]:
    """
    Return rulings for a card by Scryfall ID.

    Checks in-memory cache first; falls back to a live Scryfall request on miss.
    Caches live results in memory for the process lifetime.

    Args:
        scryfall_id: Scryfall UUID string.

    Returns:
        List of ruling dicts: [{"published_at", "source", "comment"}, ...]
        Empty list if no rulings exist or any error occurs.
    """
    if not scryfall_id:
        return []

    cache = await _ensure_cache_loaded()

    if scryfall_id in cache:
        return cache[scryfall_id]

    # Cache miss — fetch live and store in memory
    logger.debug(f"Rulings cache miss for {scryfall_id}; fetching from Scryfall.")
    rulings = await _live_fetch(scryfall_id)
    cache[scryfall_id] = rulings
    return rulings
