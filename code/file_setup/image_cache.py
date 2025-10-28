"""
Card image caching system.

Downloads and manages local cache of Magic: The Gathering card images
from Scryfall, with graceful fallback to API when images are missing.

Features:
- Optional caching (disabled by default for open source users)
- Uses Scryfall bulk data API (respects rate limits and guidelines)
- Downloads from Scryfall CDN (no rate limits on image files)
- Progress tracking for long downloads
- Resume capability if interrupted
- Graceful fallback to API if images missing

Environment Variables:
    CACHE_CARD_IMAGES: 1=enable caching, 0=disable (default: 0)

Image Sizes:
    - small: 160px width (for list views)
    - normal: 488px width (for prominent displays, hover previews)

Directory Structure:
    card_files/images/small/    - Small thumbnails (~900 MB - 1.5 GB)
    card_files/images/normal/   - Normal images (~2.4 GB - 4.5 GB)

See: https://scryfall.com/docs/api
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional
from urllib.request import Request, urlopen

from code.file_setup.scryfall_bulk_data import ScryfallBulkDataClient

logger = logging.getLogger(__name__)

# Scryfall CDN has no rate limits, but we'll be conservative
DOWNLOAD_DELAY = 0.05  # 50ms between image downloads (20 req/sec)

# Image sizes to cache
IMAGE_SIZES = ["small", "normal"]

# Card name sanitization (filesystem-safe)
INVALID_CHARS = r'[<>:"/\\|?*]'


def sanitize_filename(card_name: str) -> str:
    """
    Sanitize card name for use as filename.

    Args:
        card_name: Original card name

    Returns:
        Filesystem-safe filename
    """
    # Replace invalid characters with underscore
    safe_name = re.sub(INVALID_CHARS, "_", card_name)
    # Remove multiple consecutive underscores
    safe_name = re.sub(r"_+", "_", safe_name)
    # Trim leading/trailing underscores
    safe_name = safe_name.strip("_")
    return safe_name


class ImageCache:
    """Manages local card image cache."""

    def __init__(
        self,
        base_dir: str = "card_files/images",
        bulk_data_path: str = "card_files/raw/scryfall_bulk_data.json",
    ):
        """
        Initialize image cache.

        Args:
            base_dir: Base directory for cached images
            bulk_data_path: Path to Scryfall bulk data JSON
        """
        self.base_dir = Path(base_dir)
        self.bulk_data_path = Path(bulk_data_path)
        self.client = ScryfallBulkDataClient()
        self._last_download_time: float = 0.0

    def is_enabled(self) -> bool:
        """Check if image caching is enabled via environment variable."""
        return os.getenv("CACHE_CARD_IMAGES", "0") == "1"

    def get_image_path(self, card_name: str, size: str = "normal") -> Optional[Path]:
        """
        Get local path to cached image if it exists.

        Args:
            card_name: Card name
            size: Image size ('small' or 'normal')

        Returns:
            Path to cached image, or None if not cached
        """
        if not self.is_enabled():
            return None

        safe_name = sanitize_filename(card_name)
        image_path = self.base_dir / size / f"{safe_name}.jpg"

        if image_path.exists():
            return image_path
        return None

    def get_image_url(self, card_name: str, size: str = "normal") -> str:
        """
        Get image URL (local path if cached, Scryfall API otherwise).

        Args:
            card_name: Card name
            size: Image size ('small' or 'normal')

        Returns:
            URL or local path to image
        """
        # Check local cache first
        local_path = self.get_image_path(card_name, size)
        if local_path:
            # Return as static file path for web serving
            return f"/static/card_images/{size}/{sanitize_filename(card_name)}.jpg"

        # Fallback to Scryfall API
        from urllib.parse import quote
        card_query = quote(card_name)
        return f"https://api.scryfall.com/cards/named?fuzzy={card_query}&format=image&version={size}"

    def _rate_limit_wait(self) -> None:
        """Wait to respect rate limits between downloads."""
        elapsed = time.time() - self._last_download_time
        if elapsed < DOWNLOAD_DELAY:
            time.sleep(DOWNLOAD_DELAY - elapsed)
        self._last_download_time = time.time()

    def _download_image(self, image_url: str, output_path: Path) -> bool:
        """
        Download single image from Scryfall CDN.

        Args:
            image_url: Image URL from bulk data
            output_path: Local path to save image

        Returns:
            True if successful, False otherwise
        """
        self._rate_limit_wait()

        try:
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            req = Request(image_url)
            req.add_header("User-Agent", "MTG-Deckbuilder/3.0 (Image Cache)")

            with urlopen(req, timeout=30) as response:
                image_data = response.read()
                with open(output_path, "wb") as f:
                    f.write(image_data)

            return True

        except Exception as e:
            logger.debug(f"Failed to download {image_url}: {e}")
            # Clean up partial download
            if output_path.exists():
                output_path.unlink()
            return False

    def _load_bulk_data(self) -> list[dict[str, Any]]:
        """
        Load card data from bulk data JSON.

        Returns:
            List of card objects with image URLs

        Raises:
            FileNotFoundError: If bulk data file doesn't exist
            json.JSONDecodeError: If file is invalid JSON
        """
        if not self.bulk_data_path.exists():
            raise FileNotFoundError(
                f"Bulk data file not found: {self.bulk_data_path}. "
                "Run download_bulk_data() first."
            )

        logger.info(f"Loading bulk data from {self.bulk_data_path}")
        with open(self.bulk_data_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _filter_to_our_cards(self, bulk_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Filter bulk data to only cards in our all_cards.parquet file.
        Deduplicates by card name (takes first printing only).

        Args:
            bulk_cards: Full Scryfall bulk data

        Returns:
            Filtered list of cards matching our dataset (one per unique name)
        """
        try:
            import pandas as pd
            from code.path_util import get_processed_cards_path
            
            # Load our card names
            parquet_path = get_processed_cards_path()
            df = pd.read_parquet(parquet_path, columns=["name"])
            our_card_names = set(df["name"].str.lower())
            
            logger.info(f"Filtering {len(bulk_cards)} Scryfall cards to {len(our_card_names)} cards in our dataset")
            
            # Filter and deduplicate - keep only first printing of each card
            seen_names = set()
            filtered = []
            
            for card in bulk_cards:
                card_name_lower = card.get("name", "").lower()
                if card_name_lower in our_card_names and card_name_lower not in seen_names:
                    filtered.append(card)
                    seen_names.add(card_name_lower)
            
            logger.info(f"Filtered to {len(filtered)} unique cards with image data")
            return filtered
            
        except Exception as e:
            logger.warning(f"Could not filter to our cards: {e}. Using all Scryfall cards.")
            return bulk_cards

    def download_bulk_data(self, progress_callback=None) -> None:
        """
        Download latest Scryfall bulk data JSON.

        Args:
            progress_callback: Optional callback(bytes_downloaded, total_bytes)

        Raises:
            Exception: If download fails
        """
        logger.info("Downloading Scryfall bulk data...")
        self.bulk_data_path.parent.mkdir(parents=True, exist_ok=True)
        self.client.get_bulk_data(
            output_path=str(self.bulk_data_path),
            progress_callback=progress_callback,
        )
        logger.info("Bulk data download complete")

    def download_images(
        self,
        sizes: Optional[list[str]] = None,
        progress_callback=None,
        max_cards: Optional[int] = None,
    ) -> dict[str, int]:
        """
        Download card images from Scryfall CDN.

        Args:
            sizes: Image sizes to download (default: ['small', 'normal'])
            progress_callback: Optional callback(current, total, card_name)
            max_cards: Maximum cards to download (for testing)

        Returns:
            Dictionary with download statistics

        Raises:
            FileNotFoundError: If bulk data not available
        """
        if not self.is_enabled():
            logger.info("Image caching disabled (CACHE_CARD_IMAGES=0)")
            return {"skipped": 0}

        if sizes is None:
            sizes = IMAGE_SIZES

        logger.info(f"Starting image download for sizes: {sizes}")

        # Load bulk data and filter to our cards
        bulk_cards = self._load_bulk_data()
        cards = self._filter_to_our_cards(bulk_cards)
        total_cards = len(cards) if max_cards is None else min(max_cards, len(cards))

        stats = {
            "total": total_cards,
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
        }

        for i, card in enumerate(cards[:total_cards]):
            card_name = card.get("name")
            if not card_name:
                stats["skipped"] += 1
                continue

            # Collect all faces to download (single-faced or multi-faced)
            faces_to_download = []
            
            # Check if card has direct image_uris (single-faced card)
            if card.get("image_uris"):
                faces_to_download.append({
                    "name": card_name,
                    "image_uris": card["image_uris"],
                })
            # Handle double-faced cards (get all faces)
            elif card.get("card_faces"):
                for face_idx, face in enumerate(card["card_faces"]):
                    if face.get("image_uris"):
                        # For multi-faced cards, append face name or index
                        face_name = face.get("name", f"{card_name}_face{face_idx}")
                        faces_to_download.append({
                            "name": face_name,
                            "image_uris": face["image_uris"],
                        })
            
            # Skip if no faces found
            if not faces_to_download:
                logger.debug(f"No image URIs for {card_name}")
                stats["skipped"] += 1
                continue

            # Download each face in each requested size
            for face in faces_to_download:
                face_name = face["name"]
                image_uris = face["image_uris"]
                
                for size in sizes:
                    image_url = image_uris.get(size)
                    if not image_url:
                        continue

                    # Check if already cached
                    safe_name = sanitize_filename(face_name)
                    output_path = self.base_dir / size / f"{safe_name}.jpg"

                    if output_path.exists():
                        stats["skipped"] += 1
                        continue

                    # Download image
                    if self._download_image(image_url, output_path):
                        stats["downloaded"] += 1
                    else:
                        stats["failed"] += 1

            # Progress callback
            if progress_callback:
                progress_callback(i + 1, total_cards, card_name)

        # Invalidate cached summary since we just downloaded new images
        self.invalidate_summary_cache()

        logger.info(f"Image download complete: {stats}")
        return stats

    def cache_statistics(self) -> dict[str, Any]:
        """
        Get statistics about cached images.
        
        Uses a cached summary.json file to avoid scanning thousands of files.
        Regenerates summary if it doesn't exist or is stale (based on WEB_AUTO_REFRESH_DAYS,
        default 7 days, matching the main card data staleness check).

        Returns:
            Dictionary with cache stats (count, size, etc.)
        """
        stats = {"enabled": self.is_enabled()}

        if not self.is_enabled():
            return stats

        summary_file = self.base_dir / "summary.json"
        
        # Get staleness threshold from environment (same as card data check)
        try:
            refresh_days = int(os.getenv('WEB_AUTO_REFRESH_DAYS', '7'))
        except Exception:
            refresh_days = 7
        
        if refresh_days <= 0:
            # Never consider stale
            refresh_seconds = float('inf')
        else:
            refresh_seconds = refresh_days * 24 * 60 * 60  # Convert days to seconds
        
        # Check if summary exists and is recent (less than refresh_seconds old)
        use_cached = False
        if summary_file.exists():
            try:
                import time
                file_age = time.time() - summary_file.stat().st_mtime
                if file_age < refresh_seconds:
                    use_cached = True
            except Exception:
                pass
        
        # Try to use cached summary
        if use_cached:
            try:
                import json
                with summary_file.open('r', encoding='utf-8') as f:
                    cached_stats = json.load(f)
                    stats.update(cached_stats)
                    return stats
            except Exception as e:
                logger.warning(f"Could not read cache summary: {e}")
        
        # Regenerate summary (fast - just count files and estimate size)
        for size in IMAGE_SIZES:
            size_dir = self.base_dir / size
            if size_dir.exists():
                # Fast count: count .jpg files without statting each one
                count = sum(1 for _ in size_dir.glob("*.jpg"))
                
                # Estimate total size based on typical averages to avoid stat() calls
                # Small images: ~40 KB avg, Normal images: ~100 KB avg
                avg_size_kb = 40 if size == "small" else 100
                estimated_size_mb = (count * avg_size_kb) / 1024
                
                stats[size] = {
                    "count": count,
                    "size_mb": round(estimated_size_mb, 1),
                }
            else:
                stats[size] = {"count": 0, "size_mb": 0.0}
        
        # Save summary for next time
        try:
            import json
            with summary_file.open('w', encoding='utf-8') as f:
                json.dump({k: v for k, v in stats.items() if k != "enabled"}, f)
        except Exception as e:
            logger.warning(f"Could not write cache summary: {e}")

        return stats
    
    def invalidate_summary_cache(self) -> None:
        """Delete the cached summary file to force regeneration on next call."""
        if not self.is_enabled():
            return
        
        summary_file = self.base_dir / "summary.json"
        if summary_file.exists():
            try:
                summary_file.unlink()
                logger.debug("Invalidated cache summary file")
            except Exception as e:
                logger.warning(f"Could not delete cache summary: {e}")


def main():
    """CLI entry point for image caching."""
    import argparse

    parser = argparse.ArgumentParser(description="Card image cache management")
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download images from Scryfall",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show cache statistics",
    )
    parser.add_argument(
        "--max-cards",
        type=int,
        help="Maximum cards to download (for testing)",
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        default=IMAGE_SIZES,
        choices=IMAGE_SIZES,
        help="Image sizes to download",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download of bulk data even if recent",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    cache = ImageCache()

    if args.stats:
        stats = cache.cache_statistics()
        print("\nCache Statistics:")
        print(f"  Enabled: {stats['enabled']}")
        if stats["enabled"]:
            for size in IMAGE_SIZES:
                if size in stats:
                    print(
                        f"  {size.capitalize()}: {stats[size]['count']} images "
                        f"({stats[size]['size_mb']:.1f} MB)"
                    )

    elif args.download:
        if not cache.is_enabled():
            print("Image caching is disabled. Set CACHE_CARD_IMAGES=1 to enable.")
            return

        # Check if bulk data already exists and is recent (within 24 hours)
        bulk_data_exists = cache.bulk_data_path.exists()
        bulk_data_age_hours = None
        
        if bulk_data_exists:
            import time
            age_seconds = time.time() - cache.bulk_data_path.stat().st_mtime
            bulk_data_age_hours = age_seconds / 3600
            print(f"Bulk data file exists (age: {bulk_data_age_hours:.1f} hours)")
        
        # Download bulk data if missing, old, or forced
        if not bulk_data_exists or bulk_data_age_hours > 24 or args.force:
            print("Downloading Scryfall bulk data...")

            def bulk_progress(downloaded, total):
                if total > 0:
                    pct = (downloaded / total) * 100
                    print(f"  Progress: {downloaded / 1024 / 1024:.1f} MB / "
                          f"{total / 1024 / 1024:.1f} MB ({pct:.1f}%)", end="\r")

            cache.download_bulk_data(progress_callback=bulk_progress)
            print("\nBulk data downloaded successfully")
        else:
            print("Bulk data is recent, skipping download (use --force to re-download)")

        # Download images
        print(f"\nDownloading card images (sizes: {', '.join(args.sizes)})...")

        def image_progress(current, total, card_name):
            pct = (current / total) * 100
            print(f"  Progress: {current}/{total} ({pct:.1f}%) - {card_name}", end="\r")

        stats = cache.download_images(
            sizes=args.sizes,
            progress_callback=image_progress,
            max_cards=args.max_cards,
        )
        print("\n\nDownload complete:")
        print(f"  Total: {stats['total']}")
        print(f"  Downloaded: {stats['downloaded']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Failed: {stats['failed']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
