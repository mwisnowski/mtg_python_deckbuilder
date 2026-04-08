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
import shutil
import time
from pathlib import Path
from typing import Any, Generator, Optional
from urllib.request import Request, urlopen

from code.file_setup.scryfall_bulk_data import ScryfallBulkDataClient

logger = logging.getLogger(__name__)

# Scryfall CDN (cards.scryfall.io) has no hard rate limits.
# We use a small delay to be a polite CDN citizen.
DOWNLOAD_DELAY = 0.025  # 25ms between image downloads (~40 req/sec)

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
        
        # In-memory index of available images (avoids repeated filesystem checks)
        # Key: (size, sanitized_filename), Value: True if exists
        self._image_index: dict[tuple[str, str], bool] = {}
        self._index_built = False

    def is_enabled(self) -> bool:
        """Check if image caching is enabled via environment variable."""
        return os.getenv("CACHE_CARD_IMAGES", "0") == "1"
    
    def _build_image_index(self) -> None:
        """
        Build in-memory index of cached images to avoid repeated filesystem checks.
        This dramatically improves performance by eliminating stat() calls for every image.
        """
        if self._index_built or not self.is_enabled():
            return
        
        logger.info("Building image cache index...")
        start_time = time.time()
        
        for size in IMAGE_SIZES:
            size_dir = self.base_dir / size
            if not size_dir.exists():
                continue
            
            # Scan directory for .jpg files
            for image_file in size_dir.glob("*.jpg"):
                # Store just the filename without extension
                filename = image_file.stem
                self._image_index[(size, filename)] = True
        
        elapsed = time.time() - start_time
        total_images = len(self._image_index)
        logger.info(f"Image index built: {total_images} images indexed in {elapsed:.3f}s")
        self._index_built = True

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
        
        # Build index on first access (lazy initialization)
        if not self._index_built:
            self._build_image_index()

        safe_name = sanitize_filename(card_name)
        
        # Check in-memory index first (fast)
        if (size, safe_name) in self._image_index:
            return self.base_dir / size / f"{safe_name}.jpg"
        
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
                with open(output_path, "wb") as f:
                    shutil.copyfileobj(response, f, length=65536)

            return True

        except Exception as e:
            logger.debug(f"Failed to download {image_url}: {e}")
            # Clean up partial download
            if output_path.exists():
                output_path.unlink()
            return False

    # Frame effects that mark a non-standard treatment (showcase, extended-art, etc.).
    _SPECIAL_FRAME_EFFECTS: frozenset[str] = frozenset(
        {"showcase", "extendedart", "inverted", "step_and_compleat_foil",
         "etched", "sunmoondfc", "compasslandmark", "mooneldraziclock"}
    )

    def _score_printing(self, card: dict[str, Any]) -> int:
        """
        Score a printing by how "standard" it looks.

        Higher = more standard frame, preferred for image caching.
        Fields used: full_art, textless, promo, border_color, booster,
        variation, frame_effects.
        """
        score = 0
        if not card.get("full_art", False):
            score += 3
        if not card.get("textless", False):
            score += 2
        if not card.get("promo", False):
            score += 2
        if card.get("border_color") == "black":
            score += 3
        if card.get("booster", False):
            score += 1
        if not card.get("variation", False):
            score += 1
        frame_effects = card.get("frame_effects") or []
        if not any(e in self._SPECIAL_FRAME_EFFECTS for e in frame_effects):
            score += 2
        return score

    def _stream_card_image_data(
        self,
    ) -> Generator[tuple[str, dict[str, str]], None, None]:
        """
        Stream image URI data for our cards from bulk JSON, yielding the most
        standard-looking printing per card name.

        Does a single pass through the bulk JSON, scoring each printing with
        `_score_printing` and keeping only the best-scoring one per card name.
        Only minimal data (image URIs + card name) is retained, so peak RAM
        stays in the tens-of-MB range. Yields (face_name, image_uris) tuples
        for the chosen printing of every card in our dataset.

        Raises:
            FileNotFoundError: If bulk data file doesn't exist.
        """
        if not self.bulk_data_path.exists():
            raise FileNotFoundError(
                f"Bulk data file not found: {self.bulk_data_path}. "
                "Run download_bulk_data() first."
            )

        # Load only card names from parquet — a small set of strings.
        our_card_names: set[str] | None = None
        try:
            import pandas as pd
            from code.path_util import get_processed_cards_path

            parquet_path = get_processed_cards_path()
            df = pd.read_parquet(parquet_path, columns=["name"])
            our_card_names = set(df["name"].str.lower())
            logger.info(
                f"Streaming bulk data for {len(our_card_names)} cards in our dataset"
            )
        except Exception as e:
            logger.warning(f"Could not load card names from parquet: {e}. Streaming all cards.")

        # best: name_lower -> (score, [(face_name, image_uris)])
        # Stores only the minimal image URI data needed — not full card objects.
        best: dict[str, tuple[int, list[tuple[str, dict[str, str]]]]] = {}

        with open(self.bulk_data_path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip().rstrip(",")
                if not line or line in ("[", "]"):
                    continue
                try:
                    card = json.loads(line)
                except json.JSONDecodeError:
                    continue

                card_name: str = card.get("name", "")
                if not card_name:
                    continue

                name_lower = card_name.lower()
                if our_card_names is not None and name_lower not in our_card_names:
                    continue

                # Collect image-URI faces for this printing.
                faces: list[tuple[str, dict[str, str]]] = []
                if card.get("image_uris"):
                    faces.append((card_name, card["image_uris"]))
                elif card.get("card_faces"):
                    for face in card["card_faces"]:
                        if face.get("image_uris"):
                            face_name: str = face.get("name", card_name)
                            faces.append((face_name, face["image_uris"]))

                if not faces:
                    continue

                score = self._score_printing(card)
                existing = best.get(name_lower)
                if existing is None or score > existing[0]:
                    best[name_lower] = (score, faces)

        # Yield the best printing for each card.
        for _score, faces in best.values():
            for face_name, image_uris in faces:
                yield face_name, image_uris

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

        # Estimate total from parquet so the progress bar has a denominator.
        # This is a lightweight read (one column) and avoids loading bulk JSON twice.
        total_cards: int = 0
        try:
            import pandas as pd
            from code.path_util import get_processed_cards_path

            df_est = pd.read_parquet(get_processed_cards_path(), columns=["name"])
            total_cards = len(df_est)
            del df_est  # release immediately
        except Exception:
            pass  # progress will show 0 total if parquet unavailable

        if max_cards is not None:
            total_cards = min(max_cards, total_cards) if total_cards else max_cards

        stats = {
            "total": total_cards,
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
        }

        # Stream bulk JSON one card at a time — never loads entire file into RAM.
        card_index = 0
        for face_name, image_uris in self._stream_card_image_data():
            if max_cards is not None and card_index >= max_cards:
                break

            for size in sizes:
                image_url = image_uris.get(size)
                if not image_url:
                    continue

                safe_name = sanitize_filename(face_name)
                output_path = self.base_dir / size / f"{safe_name}.jpg"

                if output_path.exists():
                    stats["skipped"] += 1
                    continue

                if self._download_image(image_url, output_path):
                    stats["downloaded"] += 1
                else:
                    stats["failed"] += 1

            card_index += 1

            if progress_callback:
                progress_callback(card_index, total_cards, face_name)

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
