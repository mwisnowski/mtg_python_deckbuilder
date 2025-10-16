"""Fast tag indexing for reverse lookups and bulk operations.

Provides a reverse index (tag → cards) for efficient tag-based queries.
Typical queries complete in <1ms after index is built.

Usage:
    # Build index from all_cards
    index = TagIndex()
    index.build()
    
    # Query cards with specific tag
    cards = index.get_cards_with_tag("ramp")  # Returns set of card names
    
    # Query cards with multiple tags (AND logic)
    cards = index.get_cards_with_all_tags(["tokens", "sacrifice"])
    
    # Query cards with any of several tags (OR logic)
    cards = index.get_cards_with_any_tags(["lifegain", "lifelink"])
    
    # Get tags for a specific card
    tags = index.get_tags_for_card("Sol Ring")
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Optional

from code.logging_util import get_logger
from code.services.all_cards_loader import AllCardsLoader

logger = get_logger(__name__)

# Default cache path for persisted index
DEFAULT_CACHE_PATH = Path("card_files/.tag_index_metadata.json")


@dataclass
class IndexStats:
    """Statistics about the tag index."""
    total_cards: int
    total_tags: int
    total_mappings: int
    build_time_seconds: float
    indexed_at: float  # Unix timestamp
    all_cards_mtime: float  # Unix timestamp of source file


class TagIndex:
    """Fast reverse index for tag-based card queries.
    
    Builds two indexes:
    - tag → set(card names) - Reverse index for fast tag queries
    - card → list(tags) - Forward index for card tag lookups
    
    Performance:
    - Index build: <5s for 50k cards
    - Query time: <1ms per lookup
    - Memory: ~50-100MB for 30k cards
    """
    
    def __init__(self, cache_path: Optional[Path] = None):
        """Initialize empty tag index.
        
        Args:
            cache_path: Path to persist index (default: card_files/.tag_index_metadata.json)
        """
        self._tag_to_cards: Dict[str, Set[str]] = {}
        self._card_to_tags: Dict[str, List[str]] = {}
        self._stats: Optional[IndexStats] = None
        self._cache_path = cache_path or DEFAULT_CACHE_PATH
        self._loader = AllCardsLoader()
    
    def build(self, force_rebuild: bool = False) -> IndexStats:
        """Build the tag index from all_cards.
        
        Loads all_cards and creates reverse index. If a cached index exists
        and is up-to-date, loads from cache instead.
        
        Args:
            force_rebuild: If True, rebuild even if cache is valid
            
        Returns:
            IndexStats with build metrics
        """
        # Check if we can use cached index
        if not force_rebuild and self._try_load_from_cache():
            logger.info(f"Loaded tag index from cache: {self._stats.total_cards} cards, {self._stats.total_tags} tags")
            return self._stats
        
        logger.info("Building tag index from all_cards...")
        start_time = time.perf_counter()
        
        # Load all cards
        df = self._loader.load()
        
        if "themeTags" not in df.columns:
            logger.warning("themeTags column not found in all_cards")
            self._stats = IndexStats(
                total_cards=0,
                total_tags=0,
                total_mappings=0,
                build_time_seconds=0,
                indexed_at=time.time(),
                all_cards_mtime=0
            )
            return self._stats
        
        # Clear existing indexes
        self._tag_to_cards.clear()
        self._card_to_tags.clear()
        
        # Build indexes
        total_mappings = 0
        for _, row in df.iterrows():
            name = row.get("name")
            if not name:
                continue
            
            tags = self._normalize_tags(row.get("themeTags", []))
            if not tags:
                continue
            
            # Store forward mapping (card → tags)
            self._card_to_tags[name] = tags
            
            # Build reverse mapping (tag → cards)
            for tag in tags:
                if tag not in self._tag_to_cards:
                    self._tag_to_cards[tag] = set()
                self._tag_to_cards[tag].add(name)
                total_mappings += 1
        
        build_time = time.perf_counter() - start_time
        
        # Get all_cards mtime for cache validation
        all_cards_mtime = 0
        if os.path.exists(self._loader.file_path):
            all_cards_mtime = os.path.getmtime(self._loader.file_path)
        
        self._stats = IndexStats(
            total_cards=len(self._card_to_tags),
            total_tags=len(self._tag_to_cards),
            total_mappings=total_mappings,
            build_time_seconds=build_time,
            indexed_at=time.time(),
            all_cards_mtime=all_cards_mtime
        )
        
        logger.info(
            f"Built tag index: {self._stats.total_cards} cards, "
            f"{self._stats.total_tags} unique tags, "
            f"{self._stats.total_mappings} mappings in {build_time:.2f}s"
        )
        
        # Save to cache
        self._save_to_cache()
        
        return self._stats
    
    def _normalize_tags(self, tags: object) -> List[str]:
        """Normalize tags from various formats to list of strings.
        
        Handles:
        - List of strings/objects
        - String representations like "['tag1', 'tag2']"
        - Comma-separated strings
        - Empty/None values
        """
        if not tags:
            return []
        
        if isinstance(tags, list):
            # Already a list - normalize to strings
            return [str(t).strip() for t in tags if t and str(t).strip()]
        
        if isinstance(tags, str):
            # Handle empty or list repr
            if not tags or tags == "[]":
                return []
            
            # Try parsing as list repr
            if tags.startswith("["):
                import ast
                try:
                    parsed = ast.literal_eval(tags)
                    if isinstance(parsed, list):
                        return [str(t).strip() for t in parsed if t and str(t).strip()]
                except (ValueError, SyntaxError):
                    pass
            
            # Fall back to comma-separated
            return [t.strip() for t in tags.split(",") if t.strip()]
        
        return []
    
    def get_cards_with_tag(self, tag: str) -> Set[str]:
        """Get all card names that have a specific tag.
        
        Args:
            tag: Theme tag to search for (case-sensitive)
            
        Returns:
            Set of card names with the tag (empty if tag not found)
            
        Performance: O(1) lookup after index is built
        """
        return self._tag_to_cards.get(tag, set()).copy()
    
    def get_cards_with_all_tags(self, tags: List[str]) -> Set[str]:
        """Get cards that have ALL specified tags (AND logic).
        
        Args:
            tags: List of tags (card must have all of them)
            
        Returns:
            Set of card names with all tags (empty if no matches)
            
        Performance: O(k) where k is number of tags
        """
        if not tags:
            return set()
        
        # Start with cards for first tag
        result = self.get_cards_with_tag(tags[0])
        
        # Intersect with cards for each additional tag
        for tag in tags[1:]:
            result &= self.get_cards_with_tag(tag)
            if not result:
                # Short-circuit if no cards remain
                break
        
        return result
    
    def get_cards_with_any_tags(self, tags: List[str]) -> Set[str]:
        """Get cards that have ANY of the specified tags (OR logic).
        
        Args:
            tags: List of tags (card needs at least one)
            
        Returns:
            Set of card names with at least one tag
            
        Performance: O(k) where k is number of tags
        """
        result: Set[str] = set()
        for tag in tags:
            result |= self.get_cards_with_tag(tag)
        return result
    
    def get_tags_for_card(self, card_name: str) -> List[str]:
        """Get all tags for a specific card.
        
        Args:
            card_name: Name of the card
            
        Returns:
            List of theme tags for the card (empty if not found)
            
        Performance: O(1) lookup
        """
        return self._card_to_tags.get(card_name, []).copy()
    
    def get_all_tags(self) -> List[str]:
        """Get list of all tags in the index.
        
        Returns:
            Sorted list of all unique tags
        """
        return sorted(self._tag_to_cards.keys())
    
    def get_tag_stats(self, tag: str) -> Dict[str, int]:
        """Get statistics for a specific tag.
        
        Args:
            tag: Tag to get stats for
            
        Returns:
            Dict with 'card_count' key
        """
        return {
            "card_count": len(self._tag_to_cards.get(tag, set()))
        }
    
    def get_popular_tags(self, limit: int = 50) -> List[tuple[str, int]]:
        """Get most popular tags sorted by card count.
        
        Args:
            limit: Maximum number of tags to return
            
        Returns:
            List of (tag, card_count) tuples sorted by count descending
        """
        tag_counts = [
            (tag, len(cards))
            for tag, cards in self._tag_to_cards.items()
        ]
        tag_counts.sort(key=lambda x: x[1], reverse=True)
        return tag_counts[:limit]
    
    def _save_to_cache(self) -> None:
        """Save index to cache file."""
        if not self._stats:
            return
        
        try:
            cache_data = {
                "stats": {
                    "total_cards": self._stats.total_cards,
                    "total_tags": self._stats.total_tags,
                    "total_mappings": self._stats.total_mappings,
                    "build_time_seconds": self._stats.build_time_seconds,
                    "indexed_at": self._stats.indexed_at,
                    "all_cards_mtime": self._stats.all_cards_mtime
                },
                "tag_to_cards": {
                    tag: list(cards)
                    for tag, cards in self._tag_to_cards.items()
                },
                "card_to_tags": self._card_to_tags
            }
            
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self._cache_path.open("w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)
            
            logger.debug(f"Saved tag index cache to {self._cache_path}")
            
        except Exception as e:
            logger.warning(f"Failed to save tag index cache: {e}")
    
    def _try_load_from_cache(self) -> bool:
        """Try to load index from cache file.
        
        Returns:
            True if cache loaded successfully and is up-to-date
        """
        if not self._cache_path.exists():
            return False
        
        try:
            with self._cache_path.open("r", encoding="utf-8") as f:
                cache_data = json.load(f)
            
            # Check if cache is up-to-date
            stats_data = cache_data.get("stats", {})
            cached_mtime = stats_data.get("all_cards_mtime", 0)
            
            current_mtime = 0
            if os.path.exists(self._loader.file_path):
                current_mtime = os.path.getmtime(self._loader.file_path)
            
            if current_mtime > cached_mtime:
                logger.debug("Tag index cache outdated (all_cards modified)")
                return False
            
            # Load indexes
            self._tag_to_cards = {
                tag: set(cards)
                for tag, cards in cache_data.get("tag_to_cards", {}).items()
            }
            self._card_to_tags = cache_data.get("card_to_tags", {})
            
            # Restore stats
            self._stats = IndexStats(**stats_data)
            
            return True
            
        except Exception as e:
            logger.warning(f"Failed to load tag index cache: {e}")
            return False
    
    def clear_cache(self) -> None:
        """Delete the cached index file."""
        if self._cache_path.exists():
            self._cache_path.unlink()
            logger.debug(f"Deleted tag index cache: {self._cache_path}")
    
    def get_stats(self) -> Optional[IndexStats]:
        """Get index statistics.
        
        Returns:
            IndexStats if index has been built, None otherwise
        """
        return self._stats


# Global index instance
_global_index: Optional[TagIndex] = None


def get_tag_index(force_rebuild: bool = False) -> TagIndex:
    """Get or create the global tag index.
    
    Lazy-loads the index on first access. Subsequent calls return
    the cached instance.
    
    Args:
        force_rebuild: If True, rebuild the index even if cached
        
    Returns:
        Global TagIndex instance
    """
    global _global_index
    
    if _global_index is None or force_rebuild:
        _global_index = TagIndex()
        _global_index.build(force_rebuild=force_rebuild)
    elif _global_index._stats is None:
        # Index exists but hasn't been built yet
        _global_index.build()
    
    return _global_index


def clear_global_index() -> None:
    """Clear the global tag index instance."""
    global _global_index
    if _global_index:
        _global_index.clear_cache()
    _global_index = None
