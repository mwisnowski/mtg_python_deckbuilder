"""
All Cards Loader

Provides efficient loading and querying of the consolidated all_cards.parquet file.
Features in-memory caching with TTL and automatic reload on file changes.

Usage:
    loader = AllCardsLoader()
    
    # Single card lookup
    card = loader.get_by_name("Sol Ring")
    
    # Batch lookup
    cards = loader.get_by_names(["Sol Ring", "Lightning Bolt", "Counterspell"])
    
    # Filter by color identity
    blue_cards = loader.filter_by_color_identity(["U"])
    
    # Filter by themes
    token_cards = loader.filter_by_themes(["tokens"], mode="any")
    
    # Simple text search
    results = loader.search("create token", limit=100)
"""

from __future__ import annotations

import os
import time
from typing import Optional

import pandas as pd

from code.logging_util import get_logger

# Initialize logger
logger = get_logger(__name__)


class AllCardsLoader:
    """Loads and caches the consolidated all_cards.parquet file with query methods."""

    def __init__(self, file_path: Optional[str] = None, cache_ttl: int = 300) -> None:
        """
        Initialize AllCardsLoader.

        Args:
            file_path: Path to all_cards.parquet (defaults to card_files/processed/all_cards.parquet)
            cache_ttl: Time-to-live for cache in seconds (default: 300 = 5 minutes)
        """
        if file_path is None:
            from code.path_util import get_processed_cards_path
            file_path = get_processed_cards_path()
        
        self.file_path = file_path
        self.cache_ttl = cache_ttl
        self._df: Optional[pd.DataFrame] = None
        self._last_load_time: float = 0
        self._file_mtime: float = 0

    def load(self, force_reload: bool = False) -> pd.DataFrame:
        """
        Load all_cards.parquet with caching.

        Returns cached DataFrame if:
        - Cache exists
        - Cache is not expired (within TTL)
        - File hasn't been modified since last load
        - force_reload is False

        Args:
            force_reload: Force reload from disk even if cached

        Returns:
            DataFrame containing all cards

        Raises:
            FileNotFoundError: If all_cards.parquet doesn't exist
        """
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"All cards file not found: {self.file_path}")

        # Check if we need to reload
        current_time = time.time()
        file_mtime = os.path.getmtime(self.file_path)

        cache_valid = (
            self._df is not None
            and not force_reload
            and (current_time - self._last_load_time) < self.cache_ttl
            and file_mtime == self._file_mtime
        )

        if cache_valid:
            return self._df  # type: ignore

        # Load from disk
        logger.info(f"Loading all_cards from {self.file_path}...")
        start_time = time.time()
        self._df = pd.read_parquet(self.file_path, engine="pyarrow")
        elapsed = time.time() - start_time

        self._last_load_time = current_time
        self._file_mtime = file_mtime

        logger.info(
            f"Loaded {len(self._df)} cards with {len(self._df.columns)} columns in {elapsed:.3f}s"
        )

        return self._df

    def get_by_name(self, name: str) -> Optional[pd.Series]:
        """
        Get a single card by exact name match.

        Args:
            name: Card name to search for

        Returns:
            Series containing card data, or None if not found
        """
        df = self.load()
        if "name" not in df.columns:
            logger.warning("'name' column not found in all_cards")
            return None

        # Use .loc[] for faster exact match lookup
        try:
            matches = df.loc[df["name"] == name]
            if matches.empty:
                return None
            return matches.iloc[0]
        except (KeyError, IndexError):
            return None

    def get_by_names(self, names: list[str]) -> pd.DataFrame:
        """
        Get multiple cards by exact name matches (batch lookup).

        Args:
            names: List of card names to search for

        Returns:
            DataFrame containing matching cards (may be empty)
        """
        df = self.load()
        if "name" not in df.columns:
            logger.warning("'name' column not found in all_cards")
            return pd.DataFrame()

        return df[df["name"].isin(names)]

    def filter_by_color_identity(self, colors: list[str]) -> pd.DataFrame:
        """
        Filter cards by color identity.

        Args:
            colors: List of color codes (e.g., ["W", "U"], ["Colorless"], ["G", "R", "U"])

        Returns:
            DataFrame containing cards matching the color identity
        """
        df = self.load()
        if "colorIdentity" not in df.columns:
            logger.warning("'colorIdentity' column not found in all_cards")
            return pd.DataFrame()

        # Convert colors list to a set for comparison
        color_set = set(colors)

        # Handle special case for colorless
        if "Colorless" in color_set or "colorless" in color_set:
            return df[df["colorIdentity"].isin(["Colorless", "colorless"])]

        # For multi-color searches, match any card that contains those colors
        # This is a simple exact match - could be enhanced for subset/superset matching
        if len(colors) == 1:
            # Single color - exact match
            return df[df["colorIdentity"] == colors[0]]
        else:
            # Multi-color - match any of the provided colors (could be refined)
            return df[df["colorIdentity"].isin(colors)]

    def filter_by_themes(self, themes: list[str], mode: str = "any") -> pd.DataFrame:
        """
        Filter cards by theme tags.

        Args:
            themes: List of theme tags to search for
            mode: "any" (at least one theme) or "all" (must have all themes)

        Returns:
            DataFrame containing cards matching the theme criteria
        """
        df = self.load()
        if "themeTags" not in df.columns:
            logger.warning("'themeTags' column not found in all_cards")
            return pd.DataFrame()

        if mode == "all":
            # Card must have all specified themes
            mask = pd.Series([True] * len(df), index=df.index)
            for theme in themes:
                mask &= df["themeTags"].str.contains(theme, case=False, na=False)
            return df[mask]
        else:
            # Card must have at least one of the specified themes (default)
            mask = pd.Series([False] * len(df), index=df.index)
            for theme in themes:
                mask |= df["themeTags"].str.contains(theme, case=False, na=False)
            return df[mask]

    def search(self, query: str, limit: int = 100) -> pd.DataFrame:
        """
        Simple text search across card name, type, and oracle text.

        Args:
            query: Search query string
            limit: Maximum number of results to return

        Returns:
            DataFrame containing matching cards (up to limit)
        """
        df = self.load()

        # Search across multiple columns
        mask = pd.Series([False] * len(df), index=df.index)

        if "name" in df.columns:
            mask |= df["name"].str.contains(query, case=False, na=False)

        if "type" in df.columns:
            mask |= df["type"].str.contains(query, case=False, na=False)

        if "text" in df.columns:
            mask |= df["text"].str.contains(query, case=False, na=False)

        results = df[mask]

        if len(results) > limit:
            return results.head(limit)

        return results

    def filter_by_type(self, type_query: str) -> pd.DataFrame:
        """
        Filter cards by type line (supports partial matching).

        Args:
            type_query: Type string to search for (e.g., "Creature", "Instant", "Artifact")

        Returns:
            DataFrame containing cards matching the type
        """
        df = self.load()
        if "type" not in df.columns:
            logger.warning("'type' column not found in all_cards")
            return pd.DataFrame()

        return df[df["type"].str.contains(type_query, case=False, na=False)]

    def get_stats(self) -> dict:
        """
        Get statistics about the loaded card data.

        Returns:
            Dictionary with card count, column count, file size, and load time
        """
        df = self.load()

        stats = {
            "total_cards": len(df),
            "columns": len(df.columns),
            "file_path": self.file_path,
            "file_size_mb": (
                round(os.path.getsize(self.file_path) / (1024 * 1024), 2)
                if os.path.exists(self.file_path)
                else 0
            ),
            "cached": self._df is not None,
            "cache_age_seconds": int(time.time() - self._last_load_time)
            if self._last_load_time > 0
            else None,
        }

        return stats

    def clear_cache(self) -> None:
        """Clear the cached DataFrame, forcing next load to read from disk."""
        self._df = None
        self._last_load_time = 0
        logger.info("Cache cleared")
