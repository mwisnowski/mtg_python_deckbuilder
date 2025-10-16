"""Efficient tag loading using consolidated all_cards file.

Provides batch tag loading functions that leverage the all_cards.parquet file
instead of reading individual card CSV files. This is 10-50x faster for bulk
operations like deck building.

Usage:
    # Load tags for multiple cards at once
    tags_dict = load_tags_for_cards(["Sol Ring", "Lightning Bolt", "Counterspell"])
    # Returns: {"Sol Ring": ["artifacts"], "Lightning Bolt": ["burn"], ...}
    
    # Load tags for a single card
    tags = load_tags_for_card("Sol Ring")
    # Returns: ["artifacts", "ramp"]
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from code.logging_util import get_logger
from code.services.all_cards_loader import AllCardsLoader

logger = get_logger(__name__)

# Global loader instance for caching
_loader_instance: Optional[AllCardsLoader] = None


def _get_loader() -> AllCardsLoader:
    """Get or create the global AllCardsLoader instance."""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = AllCardsLoader()
    return _loader_instance


def clear_cache() -> None:
    """Clear the cached all_cards data (useful after updates)."""
    global _loader_instance
    _loader_instance = None


def load_tags_for_cards(card_names: List[str]) -> Dict[str, List[str]]:
    """Load theme tags for multiple cards in one batch operation.
    
    This is much faster than loading tags for each card individually,
    especially when dealing with 50+ cards (typical deck size).
    
    Args:
        card_names: List of card names to load tags for
        
    Returns:
        Dictionary mapping card name to list of theme tags.
        Cards not found or without tags will have empty list.
        
    Example:
        >>> tags = load_tags_for_cards(["Sol Ring", "Lightning Bolt"])
        >>> tags["Sol Ring"]
        ["artifacts", "ramp"]
    """
    if not card_names:
        return {}
    
    loader = _get_loader()
    
    try:
        # Batch lookup - single query for all cards
        df = loader.get_by_names(card_names)
        
        if df.empty:
            logger.debug(f"No cards found for {len(card_names)} names")
            return {name: [] for name in card_names}
        
        # Extract tags from DataFrame
        result: Dict[str, List[str]] = {}
        
        if "themeTags" not in df.columns:
            logger.warning("themeTags column not found in all_cards")
            return {name: [] for name in card_names}
        
        # Build lookup dictionary
        for _, row in df.iterrows():
            name = row.get("name")
            if not name:
                continue
                
            tags = row.get("themeTags", [])
            
            # Handle different themeTags formats
            if isinstance(tags, list):
                # Already a list - use directly
                result[name] = [str(t).strip() for t in tags if t]
            elif isinstance(tags, str):
                # String format - could be comma-separated or list repr
                if not tags or tags == "[]":
                    result[name] = []
                elif tags.startswith("["):
                    # List representation like "['tag1', 'tag2']"
                    import ast
                    try:
                        parsed = ast.literal_eval(tags)
                        if isinstance(parsed, list):
                            result[name] = [str(t).strip() for t in parsed if t]
                        else:
                            result[name] = []
                    except (ValueError, SyntaxError):
                        # Fallback to comma split
                        result[name] = [t.strip() for t in tags.split(",") if t.strip()]
                else:
                    # Comma-separated tags
                    result[name] = [t.strip() for t in tags.split(",") if t.strip()]
            else:
                result[name] = []
        
        # Fill in missing cards with empty lists
        for name in card_names:
            if name not in result:
                result[name] = []
        
        return result
        
    except FileNotFoundError:
        logger.warning("all_cards file not found, returning empty tags")
        return {name: [] for name in card_names}
    except Exception as e:
        logger.error(f"Error loading tags for cards: {e}")
        return {name: [] for name in card_names}


def load_tags_for_card(card_name: str) -> List[str]:
    """Load theme tags for a single card.
    
    For loading tags for multiple cards, use load_tags_for_cards() instead
    for better performance.
    
    Args:
        card_name: Name of the card
        
    Returns:
        List of theme tags for the card (empty if not found)
        
    Example:
        >>> tags = load_tags_for_card("Sol Ring")
        >>> "artifacts" in tags
        True
    """
    result = load_tags_for_cards([card_name])
    return result.get(card_name, [])


def get_cards_with_tag(tag: str, limit: Optional[int] = None) -> List[str]:
    """Get all card names that have a specific tag.
    
    Args:
        tag: Theme tag to search for
        limit: Maximum number of cards to return (None = no limit)
        
    Returns:
        List of card names with the tag
        
    Example:
        >>> cards = get_cards_with_tag("ramp", limit=10)
        >>> len(cards) <= 10
        True
    """
    loader = _get_loader()
    
    try:
        df = loader.filter_by_themes([tag], mode="any")
        
        if "name" not in df.columns:
            return []
        
        cards = df["name"].tolist()
        
        if limit is not None and len(cards) > limit:
            return cards[:limit]
        
        return cards
        
    except Exception as e:
        logger.error(f"Error getting cards with tag '{tag}': {e}")
        return []


def get_cards_with_all_tags(tags: List[str], limit: Optional[int] = None) -> List[str]:
    """Get all card names that have ALL of the specified tags.
    
    Args:
        tags: List of theme tags (card must have all of them)
        limit: Maximum number of cards to return (None = no limit)
        
    Returns:
        List of card names with all specified tags
        
    Example:
        >>> cards = get_cards_with_all_tags(["ramp", "artifacts"])
        >>> # Returns cards that have both ramp AND artifacts tags
    """
    loader = _get_loader()
    
    try:
        df = loader.filter_by_themes(tags, mode="all")
        
        if "name" not in df.columns:
            return []
        
        cards = df["name"].tolist()
        
        if limit is not None and len(cards) > limit:
            return cards[:limit]
        
        return cards
        
    except Exception as e:
        logger.error(f"Error getting cards with all tags {tags}: {e}")
        return []


def is_use_all_cards_enabled() -> bool:
    """Check if all_cards-based tag loading is enabled.
    
    Returns:
        True if USE_ALL_CARDS_FOR_TAGS is enabled (default: True)
    """
    # Check environment variable
    env_value = os.environ.get("USE_ALL_CARDS_FOR_TAGS", "true").lower()
    return env_value in ("1", "true", "yes", "on")
