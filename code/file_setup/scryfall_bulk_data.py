"""
Scryfall Bulk Data API client.

Fetches bulk data JSON files from Scryfall's bulk data API, which provides
all card information including image URLs without hitting rate limits.

See: https://scryfall.com/docs/api/bulk-data
"""

import logging
import os
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

BULK_DATA_API_URL = "https://api.scryfall.com/bulk-data"
DEFAULT_BULK_TYPE = "default_cards"  # All cards in Scryfall's database
# Fallback types if the primary bulk type CDN URL returns 404 (e.g. Cloudflare cache issue)
FALLBACK_BULK_TYPES = ["unique_artwork", "all_cards"]
RATE_LIMIT_DELAY = 0.1  # 100ms between requests (50-100ms per Scryfall guidelines)


def resolve_download_uri(info: dict[str, Any]) -> str:
    """Return the best download URL from a Scryfall bulk-data info dict.

    Scryfall now serves bulk data as gzip-compressed JSONL via
    ``jsonl_download_uri``; the legacy plain-JSON ``download_uri`` field has
    been removed from the API response. Prefer the JSONL URL and fall back to
    ``download_uri`` in case Scryfall ever restores plain JSON downloads.

    Raises:
        KeyError: If neither field is present.
    """
    uri = info.get("jsonl_download_uri") or info.get("download_uri")
    if not uri:
        raise KeyError("download_uri")
    return uri


class ScryfallBulkDataClient:
    """Client for fetching Scryfall bulk data."""

    def __init__(self, rate_limit_delay: float = RATE_LIMIT_DELAY):
        """
        Initialize Scryfall bulk data client.

        Args:
            rate_limit_delay: Seconds to wait between API requests (default 100ms)
        """
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time: float = 0.0

    def _rate_limit_wait(self) -> None:
        """Wait to respect rate limits between API calls."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _make_request(self, url: str) -> Any:
        """
        Make HTTP request with rate limiting and error handling.

        Args:
            url: URL to fetch

        Returns:
            Parsed JSON response

        Raises:
            Exception: If request fails after retries
        """
        self._rate_limit_wait()

        try:
            req = Request(url)
            req.add_header("User-Agent", "MTG-Deckbuilder/3.0 (Image Cache)")
            req.add_header("Accept", "application/json")
            with urlopen(req, timeout=30) as response:
                import json
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            raise

    def get_bulk_data_info(self, bulk_type: str = DEFAULT_BULK_TYPE) -> dict[str, Any]:
        """
        Get bulk data metadata (download URL, size, last updated).

        Args:
            bulk_type: Type of bulk data to fetch (default: default_cards)

        Returns:
            Dictionary with bulk data info including 'jsonl_download_uri'
            (see resolve_download_uri())

        Raises:
            ValueError: If bulk_type not found
            Exception: If API request fails
        """
        logger.info(f"Fetching bulk data info for type: {bulk_type}")
        response = self._make_request(BULK_DATA_API_URL)

        # Find the requested bulk data type
        for item in response.get("data", []):
            if item.get("type") == bulk_type:
                logger.info(
                    f"Found bulk data: {item.get('name')} "
                    f"(size: {item.get('size', 0) / 1024 / 1024:.1f} MB, "
                    f"updated: {item.get('updated_at', 'unknown')})"
                )
                return item

        raise ValueError(f"Bulk data type '{bulk_type}' not found")

    def download_bulk_data(
        self, download_uri: str, output_path: str, progress_callback=None
    ) -> None:
        """
        Download bulk data file and write it out as a JSON array at output_path.

        Scryfall bulk-data files are now served as gzip-compressed JSONL
        (URLs ending in ``.gz``); this transparently decompresses them and
        reassembles a single JSON array so downstream code can keep reading
        ``output_path`` with ``json.load()`` exactly as before. Plain
        (uncompressed) JSON download URLs are still supported.

        Args:
            download_uri: Direct download URL from get_bulk_data_info()
                (see resolve_download_uri())
            output_path: Local path to save the JSON file
            progress_callback: Optional callback(bytes_downloaded, total_bytes)

        Raises:
            Exception: If download fails
        """
        logger.info(f"Downloading bulk data from: {download_uri}")
        logger.info(f"Saving to: {output_path}")

        is_gzip = download_uri.endswith(".gz")
        raw_tmp_path = f"{output_path}.download.gz" if is_gzip else f"{output_path}.download"
        # Final JSON array is always assembled in a separate temp file first,
        # then atomically renamed into place -- this guarantees any other
        # thread/process reading `output_path` concurrently (e.g. the token
        # image download building its printings index) always sees either the
        # complete previous file or the complete new one, never a partially
        # written one.
        final_tmp_path = f"{output_path}.tmp"

        # No rate limit on bulk data downloads per Scryfall docs
        try:
            req = Request(download_uri)
            req.add_header("User-Agent", "MTG-Deckbuilder/3.0 (Image Cache)")

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with urlopen(req, timeout=60) as response:
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 1024 * 1024  # 1MB chunks

                with open(raw_tmp_path, "wb") as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total_size)

            if is_gzip:
                logger.info("Decompressing gzip JSONL bulk data …")
                self._convert_jsonl_gz_to_json_array(raw_tmp_path, final_tmp_path)
                os.remove(raw_tmp_path)
            else:
                os.replace(raw_tmp_path, final_tmp_path)

            # Atomically publish the fully-written file so concurrent readers
            # never observe a partial write.
            os.replace(final_tmp_path, output_path)

            logger.info(f"Downloaded {downloaded / 1024 / 1024:.1f} MB successfully")

        except Exception as e:
            logger.error(f"Failed to download bulk data: {e}")
            # Clean up partial download(s); output_path itself is never
            # touched until the final atomic rename, so it's left as-is.
            for path in (raw_tmp_path, final_tmp_path):
                if os.path.exists(path):
                    os.remove(path)
            raise

    @staticmethod
    def _convert_jsonl_gz_to_json_array(gz_path: str, output_path: str) -> None:
        """Decompress a gzip JSONL file and write it out as a JSON array with
        one card object per line.

        Several downstream consumers (price_service._rebuild_cache,
        setup.refresh_card_lists_from_bulk, setup._compute_is_new_from_bulk)
        stream-parse this file line-by-line rather than loading the whole
        array into memory, matching the format of Scryfall's legacy
        pretty-printed plain-JSON bulk files (one object per line, skipping
        lines that are just "[" or "]"). Writing everything on a single line
        would still be valid JSON but breaks that line-by-line parsing, so
        the newlines here are load-bearing, not just cosmetic.

        Reads and writes line-by-line to keep memory usage low even for the
        larger bulk types (e.g. default_cards, all_cards); each line of a
        Scryfall JSONL bulk file is already a valid JSON object, so lines are
        concatenated as-is rather than reparsed/redumped.
        """
        import gzip

        with gzip.open(gz_path, "rt", encoding="utf-8") as gz, \
                open(output_path, "w", encoding="utf-8") as out:
            out.write("[\n")
            first = True
            for line in gz:
                line = line.strip()
                if not line:
                    continue
                if not first:
                    out.write(",\n")
                out.write(line)
                first = False
            out.write("\n]")

    def get_bulk_data(
        self,
        bulk_type: str = DEFAULT_BULK_TYPE,
        output_path: str = "card_files/raw/scryfall_bulk_data.json",
        progress_callback=None,
    ) -> str:
        """
        Fetch bulk data info and download the JSON file.

        Args:
            bulk_type: Type of bulk data to fetch
            output_path: Where to save the JSON file
            progress_callback: Optional progress callback

        Returns:
            Path to downloaded file

        Raises:
            Exception: If fetch or download fails
        """
        types_to_try = [bulk_type] + [t for t in FALLBACK_BULK_TYPES if t != bulk_type]
        last_exc: Exception | None = None
        for attempt_type in types_to_try:
            try:
                info = self.get_bulk_data_info(attempt_type)
                download_uri = resolve_download_uri(info)
                if attempt_type != bulk_type:
                    logger.warning(
                        f"Bulk type '{bulk_type}' unavailable; using '{attempt_type}' as fallback"
                    )
                self.download_bulk_data(download_uri, output_path, progress_callback)
                return output_path
            except HTTPError as exc:
                if exc.code == 404:
                    logger.warning(
                        f"Bulk type '{attempt_type}' download_uri returned 404 "
                        "(possible Scryfall CDN cache issue); trying next type"
                    )
                    last_exc = exc
                    continue
                raise
        raise RuntimeError(
            "All bulk data types returned 404. This is likely a temporary Scryfall CDN issue; "
            "please try again later."
        ) from last_exc
