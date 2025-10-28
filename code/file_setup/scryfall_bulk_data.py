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
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

BULK_DATA_API_URL = "https://api.scryfall.com/bulk-data"
DEFAULT_BULK_TYPE = "default_cards"  # All cards in Scryfall's database
RATE_LIMIT_DELAY = 0.1  # 100ms between requests (50-100ms per Scryfall guidelines)


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
            Dictionary with bulk data info including 'download_uri'

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
        Download bulk data JSON file.

        Args:
            download_uri: Direct download URL from get_bulk_data_info()
            output_path: Local path to save the JSON file
            progress_callback: Optional callback(bytes_downloaded, total_bytes)

        Raises:
            Exception: If download fails
        """
        logger.info(f"Downloading bulk data from: {download_uri}")
        logger.info(f"Saving to: {output_path}")

        # No rate limit on bulk data downloads per Scryfall docs
        try:
            req = Request(download_uri)
            req.add_header("User-Agent", "MTG-Deckbuilder/3.0 (Image Cache)")

            with urlopen(req, timeout=60) as response:
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 1024 * 1024  # 1MB chunks

                # Ensure output directory exists
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                with open(output_path, "wb") as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total_size)

            logger.info(f"Downloaded {downloaded / 1024 / 1024:.1f} MB successfully")

        except Exception as e:
            logger.error(f"Failed to download bulk data: {e}")
            # Clean up partial download
            if os.path.exists(output_path):
                os.remove(output_path)
            raise

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
        info = self.get_bulk_data_info(bulk_type)
        download_uri = info["download_uri"]
        self.download_bulk_data(download_uri, output_path, progress_callback)
        return output_path
