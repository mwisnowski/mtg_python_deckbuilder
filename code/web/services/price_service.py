"""Price service for card price lookups.

Loads prices from the local Scryfall bulk data file (one card per line),
caches results in a compact JSON file under card_files/, and provides
thread-safe batch lookups for budget evaluation.

Cache strategy:
  - On first access, load from prices_cache.json if < TTL hours old
  - If cache is stale or missing, rebuild by streaming the bulk data file
  - In-memory dict (normalized lowercase key) is kept for fast lookups
  - Background refresh available via refresh_cache_background()
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from code.path_util import card_files_dir, card_files_raw_dir
from code.web.services.base import BaseService
from code import logging_util

logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
logger.addHandler(logging_util.file_handler)
logger.addHandler(logging_util.stream_handler)

_CACHE_TTL_SECONDS = 86400  # 24 hours
_BULK_DATA_FILENAME = "scryfall_bulk_data.json"
_PRICE_CACHE_FILENAME = "prices_cache.json"
_CK_CACHE_FILENAME = "ck_prices_cache.json"
_CK_API_URL = "https://api.cardkingdom.com/api/v2/pricelist"


class PriceService(BaseService):
    """Service for card price lookups backed by Scryfall bulk data.

    Reads prices from the local Scryfall bulk data file that the setup
    pipeline already downloads.  A compact JSON cache is written to
    card_files/ so subsequent startups load instantly without re-scanning
    the 500 MB bulk file.

    All public methods are thread-safe.
    """

    def __init__(
        self,
        *,
        bulk_data_path: Optional[str] = None,
        cache_path: Optional[str] = None,
        cache_ttl: int = _CACHE_TTL_SECONDS,
    ) -> None:
        super().__init__()
        self._bulk_path: str = bulk_data_path or os.path.join(
            card_files_raw_dir(), _BULK_DATA_FILENAME
        )
        self._cache_path: str = cache_path or os.path.join(
            card_files_dir(), _PRICE_CACHE_FILENAME
        )
        self._ttl: int = cache_ttl

        # {normalized_card_name: {"usd": float, "usd_foil": float, "eur": float, "eur_foil": float}}
        self._cache: Dict[str, Dict[str, float]] = {}
        self._lock = threading.RLock()
        self._loaded = False
        self._last_refresh: float = 0.0
        self._hit_count = 0
        self._miss_count = 0
        self._refresh_thread: Optional[threading.Thread] = None

        # CK price cache: {normalized_card_name: float (cheapest non-foil retail)}
        self._ck_cache_path: str = os.path.join(card_files_dir(), _CK_CACHE_FILENAME)
        self._ck_cache: Dict[str, float] = {}
        self._ck_loaded: bool = False

        # scryfall_id map built during _rebuild_cache: {name.lower(): scryfall_id}
        self._scryfall_id_map: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_price(
        self,
        card_name: str,
        region: str = "usd",
        foil: bool = False,
    ) -> Optional[float]:
        """Return the price for *card_name* or ``None`` if not found.

        Args:
            card_name: Card name (case-insensitive).
            region: Price region - ``"usd"`` or ``"eur"``.
            foil: If ``True`` return foil price.

        Returns:
            Price as float or ``None`` when missing / card unknown.
        """
        self._ensure_loaded()
        price_key = region + ("_foil" if foil else "")
        entry = self._cache.get(card_name.lower().strip())
        self.queue_lazy_refresh(card_name)
        with self._lock:
            if entry is not None:
                self._hit_count += 1
                return entry.get(price_key)
            self._miss_count += 1
        return None

    def get_prices_batch(
        self,
        card_names: List[str],
        region: str = "usd",
        foil: bool = False,
    ) -> Dict[str, Optional[float]]:
        """Return a mapping of card name → price for all requested cards.

        Missing cards map to ``None``.  Preserves input ordering and
        original case in the returned keys.

        Args:
            card_names: List of card names to look up.
            region: Price region - ``"usd"`` or ``"eur"``.
            foil: If ``True`` return foil prices.

        Returns:
            Dict mapping each input name to its price (or ``None``).
        """
        self._ensure_loaded()
        price_key = region + ("_foil" if foil else "")
        result: Dict[str, Optional[float]] = {}
        hits = 0
        misses = 0
        for name in card_names:
            entry = self._cache.get(name.lower().strip())
            if entry is not None:
                result[name] = entry.get(price_key)
                hits += 1
            else:
                result[name] = None
                misses += 1
        with self._lock:
            self._hit_count += hits
            self._miss_count += misses
        return result

    def cache_stats(self) -> Dict[str, Any]:
        """Return telemetry snapshot about cache performance.

        Returns:
            Dict with ``total_entries``, ``hit_count``, ``miss_count``,
            ``hit_rate``, ``last_refresh``, ``loaded``, ``cache_path``.
        """
        self._ensure_loaded()
        with self._lock:
            total = self._hit_count + self._miss_count
            return {
                "total_entries": len(self._cache),
                "hit_count": self._hit_count,
                "miss_count": self._miss_count,
                "hit_rate": (self._hit_count / total) if total > 0 else 0.0,
                "last_refresh": self._last_refresh,
                "loaded": self._loaded,
                "cache_path": self._cache_path,
                "bulk_data_available": os.path.exists(self._bulk_path),
            }

    # ------------------------------------------------------------------
    # CK Public API
    # ------------------------------------------------------------------

    def get_ck_price(self, card_name: str) -> Optional[float]:
        """Return the Card Kingdom retail price for *card_name*, or None."""
        self._ensure_ck_loaded()
        return self._ck_cache.get(card_name.lower().strip())

    def get_ck_prices_batch(self, card_names: List[str]) -> Dict[str, Optional[float]]:
        """Return a mapping of card name → CK retail price for all requested cards."""
        self._ensure_ck_loaded()
        return {
            name: self._ck_cache.get(name.lower().strip())
            for name in card_names
        }

    def get_ck_built_at(self) -> Optional[str]:
        """Return a human-readable CK cache build date, or None if unavailable."""
        try:
            if os.path.exists(self._ck_cache_path):
                import datetime
                built = os.path.getmtime(self._ck_cache_path)
                dt = datetime.datetime.fromtimestamp(built, tz=datetime.timezone.utc)
                return dt.strftime("%B %d, %Y")
        except Exception:
            pass
        return None

    def refresh_cache_background(self) -> None:
        """Spawn a daemon thread to rebuild the price cache asynchronously.

        If a refresh is already in progress, this call is a no-op.
        """
        with self._lock:
            if self._refresh_thread and self._refresh_thread.is_alive():
                logger.debug("Price cache background refresh already running")
                return
            t = threading.Thread(
                target=self._rebuild_cache,
                daemon=True,
                name="price-cache-refresh",
            )
            self._refresh_thread = t
        t.start()

    def get_cache_built_at(self) -> str | None:
        """Return a human-readable price cache build date, or None if unavailable."""
        try:
            if os.path.exists(self._cache_path):
                import datetime
                built = os.path.getmtime(self._cache_path)
                if built:
                    dt = datetime.datetime.fromtimestamp(built, tz=datetime.timezone.utc)
                    return dt.strftime("%B %d, %Y")
        except Exception:
            pass
        return None

    def start_daily_refresh(self, hour: int = 1, on_after_rebuild: Optional[Callable] = None) -> None:
        """Start a daemon thread that rebuilds prices once daily at *hour* UTC.

        Checks every 30 minutes. Safe to call multiple times — only one
        scheduler thread will be started.

        Args:
            hour: UTC hour (0–23) at which to run the nightly rebuild.
            on_after_rebuild: Optional callable invoked after each successful
                rebuild (e.g., to update the parquet files).
        """
        with self._lock:
            if getattr(self, "_daily_thread", None) and self._daily_thread.is_alive():  # type: ignore[attr-defined]
                return

        def _loop() -> None:
            import datetime
            last_date: "datetime.date | None" = None
            while True:
                try:
                    now = datetime.datetime.now(tz=datetime.timezone.utc)
                    today = now.date()
                    if now.hour >= hour and today != last_date:
                        logger.info("Scheduled price refresh running (daily at %02d:00 UTC) …", hour)
                        self._rebuild_cache()
                        last_date = today
                        if on_after_rebuild:
                            try:
                                on_after_rebuild()
                            except Exception as exc:
                                logger.error("on_after_rebuild callback failed: %s", exc)
                        logger.info("Scheduled price refresh complete.")
                except Exception as exc:
                    logger.error("Daily price refresh error: %s", exc)
                time.sleep(1800)

        t = threading.Thread(target=_loop, daemon=True, name="price-daily-refresh")
        self._daily_thread = t  # type: ignore[attr-defined]
        t.start()
        logger.info("Daily price refresh scheduler started (hour=%d UTC)", hour)

    def start_lazy_refresh(self, stale_days: int = 7) -> None:
        """Start a background worker that refreshes per-card prices from the
        Scryfall API when they have not been updated within *stale_days* days.

        Queuing: call queue_lazy_refresh(card_name) to mark a card as stale.
        The worker runs every 60 seconds, processes up to 20 cards per cycle,
        and respects Scryfall's 100 ms rate-limit guideline.
        """
        with self._lock:
            if getattr(self, "_lazy_thread", None) and self._lazy_thread.is_alive():  # type: ignore[attr-defined]
                return
        self._lazy_stale_seconds: float = stale_days * 86400
        self._lazy_queue: set[str] = set()
        self._lazy_ts: dict[str, float] = self._load_lazy_ts()
        self._lazy_lock = threading.Lock()

        def _worker() -> None:
            while True:
                try:
                    time.sleep(60)
                    with self._lazy_lock:
                        batch = list(self._lazy_queue)[:20]
                        self._lazy_queue -= set(batch)
                    if batch:
                        self._fetch_lazy_batch(batch)
                except Exception as exc:
                    logger.error("Lazy price refresh error: %s", exc)

        t = threading.Thread(target=_worker, daemon=True, name="price-lazy-refresh")
        self._lazy_thread = t  # type: ignore[attr-defined]
        t.start()
        logger.info("Lazy price refresh worker started (stale_days=%d)", stale_days)

    def queue_lazy_refresh(self, card_name: str) -> None:
        """Mark *card_name* for a lazy per-card price update if its cached
        price is stale or missing.  No-op when lazy mode is not enabled."""
        if not hasattr(self, "_lazy_queue"):
            return
        key = card_name.lower().strip()
        ts = self._lazy_ts.get(key)
        if ts is None or (time.time() - ts) > self._lazy_stale_seconds:
            with self._lazy_lock:
                self._lazy_queue.add(card_name.strip())

    def _fetch_lazy_batch(self, names: list[str]) -> None:
        """Fetch fresh prices for *names* from the Scryfall named-card API."""
        import urllib.request as _urllib
        import urllib.parse as _urlparse
        now = time.time()
        updated: dict[str, float] = {}
        for name in names:
            try:
                url = "https://api.scryfall.com/cards/named?" + _urlparse.urlencode({"exact": name, "format": "json"})
                req = _urllib.Request(url, headers={"User-Agent": "MTGPythonDeckbuilder/1.0"})
                with _urllib.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                raw_prices: dict = data.get("prices") or {}
                entry = self._extract_prices(raw_prices)
                if entry:
                    key = name.lower()
                    with self._lock:
                        self._cache[key] = entry
                    updated[key] = now
                    logger.debug("Lazy refresh: %s → $%.2f", name, entry.get("usd", 0))
            except Exception as exc:
                logger.debug("Lazy price fetch skipped for %s: %s", name, exc)
            time.sleep(0.1)  # 100 ms — Scryfall rate-limit guideline
        if updated:
            self._lazy_ts.update(updated)
            self._save_lazy_ts()
            # Also persist the updated in-memory cache to the JSON cache file
            try:
                self._persist_cache_snapshot()
            except Exception:
                pass

    def _load_lazy_ts(self) -> dict[str, float]:
        """Load per-card timestamps from companion file."""
        ts_path = self._cache_path + ".ts"
        try:
            if os.path.exists(ts_path):
                with open(ts_path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
        except Exception:
            pass
        return {}

    def _save_lazy_ts(self) -> None:
        """Atomically persist per-card timestamps."""
        ts_path = self._cache_path + ".ts"
        tmp = ts_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._lazy_ts, fh, separators=(",", ":"))
            os.replace(tmp, ts_path)
        except Exception as exc:
            logger.warning("Failed to save lazy timestamps: %s", exc)

    def get_stale_cards(self, threshold_hours: int = 24) -> set[str]:
        """Return the set of card names whose cached price is older than *threshold_hours*.

        Uses the per-card timestamp sidecar (``prices_cache.json.ts``).  If the
        sidecar is absent, all priced cards are considered stale (safe default).
        Returns an empty set when *threshold_hours* is 0 (warnings disabled).
        Card names are returned in their original (display-name) casing as stored
        in ``self._cache``.
        """
        import time as _t
        if threshold_hours <= 0:
            return set()
        cutoff = _t.time() - threshold_hours * 3600
        with self._lock:
            ts_map: dict[str, float] = dict(self._lazy_ts)
            cached_keys: set[str] = set(self._cache.keys())
        stale: set[str] = set()
        for key in cached_keys:
            ts = ts_map.get(key)
            if ts is None or ts < cutoff:
                stale.add(key)
        return stale

    def _persist_cache_snapshot(self) -> None:
        """Write the current in-memory cache to the JSON cache file (atomic)."""
        import time as _t
        with self._lock:
            snapshot = dict(self._cache)
            built = self._last_refresh or _t.time()
        cache_data = {"prices": snapshot, "built_at": built}
        tmp_path = self._cache_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(cache_data, fh, separators=(",", ":"))
        os.replace(tmp_path, self._cache_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Lazy-load the price cache on first access (double-checked lock)."""
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load_or_rebuild()
            self._loaded = True

    def _load_or_rebuild(self) -> None:
        """Load from JSON cache if fresh; otherwise rebuild from bulk data."""
        if os.path.exists(self._cache_path):
            try:
                age = time.time() - os.path.getmtime(self._cache_path)
                if age < self._ttl:
                    self._load_from_cache_file()
                    logger.info(
                        "Loaded %d prices from cache (age %.1fh)",
                        len(self._cache),
                        age / 3600,
                    )
                    return
                logger.info("Price cache stale (%.1fh old), rebuilding", age / 3600)
            except Exception as exc:
                logger.warning("Price cache unreadable, rebuilding: %s", exc)
        self._rebuild_cache()

    def _load_from_cache_file(self) -> None:
        """Deserialize the compact prices cache JSON into memory."""
        with open(self._cache_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self._cache = data.get("prices", {})
        self._last_refresh = data.get("built_at", 0.0)

    def _rebuild_cache(self) -> None:
        """Stream the Scryfall bulk data file and extract prices.

        Writes a compact cache JSON then swaps the in-memory dict.
        Uses an atomic rename so concurrent readers see a complete file.
        """
        if not os.path.exists(self._bulk_path):
            logger.warning("Scryfall bulk data not found at %s", self._bulk_path)
            return

        logger.info("Building price cache from %s ...", self._bulk_path)
        new_cache: Dict[str, Dict[str, float]] = {}
        new_scryfall_id_map: Dict[str, str] = {}
        built_at = time.time()

        try:
            with open(self._bulk_path, "r", encoding="utf-8") as fh:
                for raw_line in fh:
                    line = raw_line.strip().rstrip(",")
                    if not line or line in ("[", "]"):
                        continue
                    try:
                        card = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    name: str = card.get("name", "")
                    scryfall_id: str = card.get("id", "")
                    prices: Dict[str, Any] = card.get("prices") or {}
                    if not name:
                        continue

                    entry = self._extract_prices(prices)
                    if not entry:
                        continue

                    # Index by both the combined name and each face name
                    names_to_index = [name]
                    if " // " in name:
                        names_to_index += [part.strip() for part in name.split(" // ")]

                    for idx_name in names_to_index:
                        key = idx_name.lower()
                        existing = new_cache.get(key)
                        # Prefer cheapest non-foil USD price across printings
                        new_usd = entry.get("usd", 9999.0)
                        if existing is None or new_usd < existing.get("usd", 9999.0):
                            new_cache[key] = entry
                            # Track the scryfall_id of the cheapest-priced printing
                            if scryfall_id:
                                new_scryfall_id_map[key] = scryfall_id

        except Exception as exc:
            logger.error("Failed to parse bulk data: %s", exc)
            return

        # Write compact cache atomically
        try:
            cache_data = {"prices": new_cache, "built_at": built_at}
            tmp_path = self._cache_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(cache_data, fh, separators=(",", ":"))
            os.replace(tmp_path, self._cache_path)
            logger.info(
                "Price cache written: %d cards → %s", len(new_cache), self._cache_path
            )
        except Exception as exc:
            logger.error("Failed to write price cache: %s", exc)

        with self._lock:
            self._cache = new_cache
            self._scryfall_id_map = new_scryfall_id_map
            self._last_refresh = built_at
            # Stamp all keys as fresh so get_stale_cards() reflects the rebuild.
            # _lazy_ts may not exist if start_lazy_refresh() was never called
            # (e.g. when invoked from setup/CI without the full web app).
            if not hasattr(self, "_lazy_ts"):
                self._lazy_ts = self._load_lazy_ts()
            for key in new_cache:
                self._lazy_ts[key] = built_at
        self._save_lazy_ts()

    # ------------------------------------------------------------------
    # CK internal helpers
    # ------------------------------------------------------------------

    def _ensure_ck_loaded(self) -> None:
        """Lazy-load the CK price cache on first access (double-checked lock)."""
        if self._ck_loaded:
            return
        with self._lock:
            if self._ck_loaded:
                return
            if os.path.exists(self._ck_cache_path):
                try:
                    age = time.time() - os.path.getmtime(self._ck_cache_path)
                    if age < self._ttl:
                        self._load_ck_from_cache()
                        logger.info("Loaded %d CK prices from cache (age %.1fh)", len(self._ck_cache), age / 3600)
                        self._ck_loaded = True
                        return
                except Exception as exc:
                    logger.warning("CK cache unreadable: %s", exc)
            # No fresh cache — set loaded flag anyway so we degrade gracefully
            # rather than blocking every request. CK rebuild happens via Setup page.
            self._ck_loaded = True

    def _rebuild_ck_cache(self) -> None:
        """Fetch the Card Kingdom price list and cache retail prices by card name.

        Fetches https://api.cardkingdom.com/api/v2/pricelist, takes the cheapest
        non-foil price_retail per card name (across all printings), and writes
        ck_prices_cache.json atomically.
        """
        import urllib.request as _urllib
        logger.info("Fetching CK price list from %s ...", _CK_API_URL)
        try:
            req = _urllib.Request(_CK_API_URL, headers={"User-Agent": "MTGPythonDeckbuilder/1.0"})
            with _urllib.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except Exception as exc:
            logger.warning("CK price fetch failed: %s", exc)
            return

        items = data.get("data", [])
        meta_created_at = data.get("meta", {}).get("created_at", "")
        new_ck: Dict[str, float] = {}

        for item in items:
            if item.get("is_foil") == "true":
                continue
            name = item.get("name", "")
            price_str = item.get("price_retail", "")
            if not name or not price_str:
                continue
            try:
                price = float(price_str)
            except (ValueError, TypeError):
                continue
            if price <= 0:
                continue

            # Index by full name and each face for split/DFC cards
            keys_to_index = [name.lower()]
            if " // " in name:
                keys_to_index += [part.strip().lower() for part in name.split(" // ")]

            for key in keys_to_index:
                if key not in new_ck or price < new_ck[key]:
                    new_ck[key] = price

        # Write cache atomically
        try:
            cache_data = {"ck_prices": new_ck, "built_at": time.time(), "meta_created_at": meta_created_at}
            tmp = self._ck_cache_path + ".tmp"
            os.makedirs(os.path.dirname(self._ck_cache_path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(cache_data, fh, separators=(",", ":"))
            os.replace(tmp, self._ck_cache_path)
            logger.info("CK price cache written: %d cards → %s", len(new_ck), self._ck_cache_path)
        except Exception as exc:
            logger.error("Failed to write CK price cache: %s", exc)
            return

        with self._lock:
            self._ck_cache = new_ck
            self._ck_loaded = True

    def _load_ck_from_cache(self) -> None:
        """Deserialize the CK prices cache JSON into memory."""
        with open(self._ck_cache_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self._ck_cache = data.get("ck_prices", {})

    @staticmethod
    def _extract_prices(prices: Dict[str, Any]) -> Dict[str, float]:
        """Convert raw Scryfall prices dict to {region_key: float} entries."""

        result: Dict[str, float] = {}
        for key in ("usd", "usd_foil", "eur", "eur_foil"):
            raw = prices.get(key)
            if raw is not None and raw != "":
                try:
                    result[key] = float(raw)
                except (ValueError, TypeError):
                    pass
        return result


# ---------------------------------------------------------------------------
# Module-level singleton (lazy)
# ---------------------------------------------------------------------------

_INSTANCE: Optional[PriceService] = None
_INSTANCE_LOCK = threading.Lock()


def get_price_service() -> PriceService:
    """Return the shared PriceService singleton, creating it on first call."""
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = PriceService()
    return _INSTANCE
