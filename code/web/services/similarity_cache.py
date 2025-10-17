"""
Similarity cache manager for card similarity calculations.

Provides persistent caching of pre-computed card similarity scores to improve
card detail page load times from 2-6s down to <500ms.

Cache format: Parquet file with columnar structure:
- card_name: str (source card)
- similar_name: str (similar card name)
- similarity: float (similarity score)
- edhrecRank: float (EDHREC rank of similar card)
- rank: int (ranking position, 0-19 for top 20)

Metadata stored in separate JSON sidecar file.

Benefits vs JSON:
- 5-10x faster load times
- 50-70% smaller file size
- Better compression for large datasets
- Consistent with other card data storage
"""

import json
import logging
import os
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default cache settings
CACHE_VERSION = "2.0"  # Bumped for Parquet format
DEFAULT_CACHE_PATH = Path(__file__).parents[3] / "card_files" / "similarity_cache.parquet"
DEFAULT_METADATA_PATH = Path(__file__).parents[3] / "card_files" / "similarity_cache_metadata.json"


class SimilarityCache:
    """Manages persistent cache for card similarity calculations using Parquet."""

    def __init__(self, cache_path: Optional[Path] = None, enabled: bool = True):
        """
        Initialize similarity cache manager.

        Args:
            cache_path: Path to cache file. If None, uses DEFAULT_CACHE_PATH
            enabled: Whether cache is enabled (can be disabled via env var)
        """
        self.cache_path = cache_path or DEFAULT_CACHE_PATH
        self.metadata_path = self.cache_path.with_name(
            self.cache_path.stem + "_metadata.json"
        )
        self.enabled = enabled and os.getenv("SIMILARITY_CACHE_ENABLED", "1") == "1"
        self._cache_df: Optional[pd.DataFrame] = None
        self._metadata: Optional[dict] = None

        # Ensure cache directory exists
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        if self.enabled:
            logger.info(f"SimilarityCache initialized at {self.cache_path}")
        else:
            logger.info("SimilarityCache disabled")

    def load_cache(self) -> pd.DataFrame:
        """
        Load cache from disk.

        Returns:
            DataFrame with columns: card_name, similar_name, similarity, edhrecRank, rank
            Returns empty DataFrame if file doesn't exist or loading fails
        """
        if not self.enabled:
            return self._empty_cache_df()

        if self._cache_df is not None:
            return self._cache_df

        if not self.cache_path.exists():
            logger.info("Cache file not found, returning empty cache")
            self._cache_df = self._empty_cache_df()
            return self._cache_df

        try:
            # Load Parquet file
            self._cache_df = pq.read_table(self.cache_path).to_pandas()
            
            # Load metadata
            if self.metadata_path.exists():
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    self._metadata = json.load(f)
            else:
                self._metadata = self._empty_metadata()

            # Validate cache structure
            if not self._validate_cache(self._cache_df):
                logger.warning("Cache validation failed, returning empty cache")
                self._cache_df = self._empty_cache_df()
                return self._cache_df

            total_cards = len(self._cache_df["card_name"].unique()) if len(self._cache_df) > 0 else 0
            logger.info(
                f"Loaded similarity cache v{self._metadata.get('version', 'unknown')} with {total_cards:,} cards ({len(self._cache_df):,} entries)"
            )

            return self._cache_df

        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
            self._cache_df = self._empty_cache_df()
            return self._cache_df

    def save_cache(self, cache_df: pd.DataFrame, metadata: Optional[dict] = None) -> bool:
        """
        Save cache to disk.

        Args:
            cache_df: DataFrame with similarity data
            metadata: Optional metadata dict. If None, uses current metadata with updates.

        Returns:
            True if save successful, False otherwise
        """
        if not self.enabled:
            logger.debug("Cache disabled, skipping save")
            return False

        try:
            # Ensure directory exists
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)

            # Update metadata
            if metadata is None:
                metadata = self._metadata or self._empty_metadata()
            
            total_cards = len(cache_df["card_name"].unique()) if len(cache_df) > 0 else 0
            metadata["total_cards"] = total_cards
            metadata["last_updated"] = datetime.now().isoformat()
            metadata["total_entries"] = len(cache_df)

            # Write Parquet file (with compression)
            temp_cache = self.cache_path.with_suffix(".tmp")
            pq.write_table(
                pa.table(cache_df),
                temp_cache,
                compression="snappy",
                version="2.6",
            )
            temp_cache.replace(self.cache_path)

            # Write metadata file
            temp_meta = self.metadata_path.with_suffix(".tmp")
            with open(temp_meta, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            temp_meta.replace(self.metadata_path)

            self._cache_df = cache_df
            self._metadata = metadata
            
            logger.info(f"Saved similarity cache with {total_cards:,} cards ({len(cache_df):,} entries)")

            return True

        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
            return False

    def get_similar(self, card_name: str, limit: int = 5, randomize: bool = True) -> Optional[list[dict]]:
        """
        Get cached similar cards for a given card.

        Args:
            card_name: Name of the card to look up
            limit: Maximum number of results to return
            randomize: If True, randomly sample from cached results; if False, return top by rank

        Returns:
            List of similar cards with similarity scores, or None if not in cache
        """
        if not self.enabled:
            return None

        cache_df = self.load_cache()
        
        if len(cache_df) == 0:
            return None

        # Filter to this card
        card_data = cache_df[cache_df["card_name"] == card_name]
        
        if len(card_data) == 0:
            return None

        # Randomly sample if requested and we have more results than limit
        if randomize and len(card_data) > limit:
            card_data = card_data.sample(n=limit, random_state=None)
        else:
            # Sort by rank and take top N
            card_data = card_data.sort_values("rank").head(limit)

        # Convert to list of dicts
        results = []
        for _, row in card_data.iterrows():
            results.append({
                "name": row["similar_name"],
                "similarity": row["similarity"],
                "edhrecRank": row["edhrecRank"],
            })

        return results

    def set_similar(self, card_name: str, similar_cards: list[dict]) -> bool:
        """
        Cache similar cards for a given card.

        Args:
            card_name: Name of the card
            similar_cards: List of similar cards with similarity scores

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False

        cache_df = self.load_cache()

        # Remove existing entries for this card
        cache_df = cache_df[cache_df["card_name"] != card_name]

        # Add new entries
        new_rows = []
        for rank, card in enumerate(similar_cards):
            new_rows.append({
                "card_name": card_name,
                "similar_name": card["name"],
                "similarity": card["similarity"],
                "edhrecRank": card.get("edhrecRank", float("inf")),
                "rank": rank,
            })

        if new_rows:
            new_df = pd.DataFrame(new_rows)
            cache_df = pd.concat([cache_df, new_df], ignore_index=True)

        return self.save_cache(cache_df)

    def invalidate(self, card_name: Optional[str] = None) -> bool:
        """
        Invalidate cache entries.

        Args:
            card_name: If provided, invalidate only this card. If None, clear entire cache.

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False

        if card_name is None:
            # Clear entire cache
            logger.info("Clearing entire similarity cache")
            self._cache_df = self._empty_cache_df()
            self._metadata = self._empty_metadata()
            return self.save_cache(self._cache_df, self._metadata)

        # Clear specific card
        cache_df = self.load_cache()
        
        initial_len = len(cache_df)
        cache_df = cache_df[cache_df["card_name"] != card_name]
        
        if len(cache_df) < initial_len:
            logger.info(f"Invalidated cache for card: {card_name}")
            return self.save_cache(cache_df)

        return False

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats (version, total_cards, build_date, file_size, etc.)
        """
        if not self.enabled:
            return {"enabled": False}

        cache_df = self.load_cache()
        metadata = self._metadata or self._empty_metadata()

        stats = {
            "enabled": True,
            "version": metadata.get("version", "unknown"),
            "total_cards": len(cache_df["card_name"].unique()) if len(cache_df) > 0 else 0,
            "total_entries": len(cache_df),
            "build_date": metadata.get("build_date"),
            "last_updated": metadata.get("last_updated"),
            "file_exists": self.cache_path.exists(),
            "file_path": str(self.cache_path),
            "format": "parquet",
        }

        if self.cache_path.exists():
            stats["file_size_mb"] = round(
                self.cache_path.stat().st_size / (1024 * 1024), 2
            )

        return stats

    @staticmethod
    def _empty_cache_df() -> pd.DataFrame:
        """
        Create empty cache DataFrame.

        Returns:
            Empty DataFrame with correct schema
        """
        return pd.DataFrame(columns=["card_name", "similar_name", "similarity", "edhrecRank", "rank"])

    @staticmethod
    def _empty_metadata() -> dict:
        """
        Create empty metadata structure.

        Returns:
            Empty metadata dictionary
        """
        return {
            "version": CACHE_VERSION,
            "total_cards": 0,
            "total_entries": 0,
            "build_date": None,
            "last_updated": None,
            "threshold": 0.6,
            "min_results": 3,
        }

    @staticmethod
    def _validate_cache(cache_df: pd.DataFrame) -> bool:
        """
        Validate cache DataFrame structure.

        Args:
            cache_df: DataFrame to validate

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(cache_df, pd.DataFrame):
            return False

        # Check required columns
        required_cols = {"card_name", "similar_name", "similarity", "edhrecRank", "rank"}
        if not required_cols.issubset(cache_df.columns):
            logger.warning(f"Cache missing required columns. Expected: {required_cols}, Got: {set(cache_df.columns)}")
            return False

        return True


# Singleton instance for global access
_cache_instance: Optional[SimilarityCache] = None


def get_cache() -> SimilarityCache:
    """
    Get singleton cache instance.

    Returns:
        Global SimilarityCache instance
    """
    global _cache_instance

    if _cache_instance is None:
        # Check environment variables for custom path
        cache_path_str = os.getenv("SIMILARITY_CACHE_PATH")
        cache_path = Path(cache_path_str) if cache_path_str else None

        _cache_instance = SimilarityCache(cache_path=cache_path)

    return _cache_instance
