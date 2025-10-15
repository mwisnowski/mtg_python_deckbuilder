"""
Legacy Loader Adapter

Provides backward-compatible wrapper functions around AllCardsLoader for smooth migration.
Existing code can continue using old file-loading patterns while benefiting from
the new consolidated Parquet backend.

This adapter will be maintained through v3.0.x and deprecated in v3.1+.

Usage:
    # Old code (still works):
    from code.services.legacy_loader_adapter import load_cards_by_type
    creatures = load_cards_by_type("Creature")
    
    # New code (preferred):
    from code.services.all_cards_loader import AllCardsLoader
    loader = AllCardsLoader()
    creatures = loader.filter_by_type("Creature")
"""

from __future__ import annotations

import warnings
from typing import Optional

import pandas as pd

from code.logging_util import get_logger
from code.services.all_cards_loader import AllCardsLoader
from code.settings import USE_ALL_CARDS_FILE

# Initialize logger
logger = get_logger(__name__)

# Shared loader instance for performance
_shared_loader: Optional[AllCardsLoader] = None


def _get_loader() -> AllCardsLoader:
    """Get or create shared AllCardsLoader instance."""
    global _shared_loader
    if _shared_loader is None:
        _shared_loader = AllCardsLoader()
    return _shared_loader


def _deprecation_warning(func_name: str, replacement: str) -> None:
    """Log deprecation warning for legacy functions."""
    warnings.warn(
        f"{func_name} is deprecated and will be removed in v3.1+. "
        f"Use {replacement} instead.",
        DeprecationWarning,
        stacklevel=3,
    )
    logger.warning(
        f"DEPRECATION: {func_name} called. Migrate to {replacement} before v3.1+"
    )


def load_all_cards(use_cache: bool = True) -> pd.DataFrame:
    """
    Load all cards from consolidated Parquet file.
    
    Legacy function for backward compatibility.
    
    Args:
        use_cache: Whether to use cached data (default: True)
    
    Returns:
        DataFrame containing all cards
    
    Deprecated:
        Use AllCardsLoader().load() instead.
    """
    _deprecation_warning("load_all_cards()", "AllCardsLoader().load()")
    
    if not USE_ALL_CARDS_FILE:
        logger.warning("USE_ALL_CARDS_FILE is disabled, returning empty DataFrame")
        return pd.DataFrame()
    
    loader = _get_loader()
    return loader.load(force_reload=not use_cache)


def load_cards_by_name(name: str) -> Optional[pd.Series]:
    """
    Load a single card by exact name match.
    
    Legacy function for backward compatibility.
    
    Args:
        name: Card name to search for
    
    Returns:
        Series containing card data, or None if not found
    
    Deprecated:
        Use AllCardsLoader().get_by_name() instead.
    """
    _deprecation_warning("load_cards_by_name()", "AllCardsLoader().get_by_name()")
    
    if not USE_ALL_CARDS_FILE:
        logger.warning("USE_ALL_CARDS_FILE is disabled, returning None")
        return None
    
    loader = _get_loader()
    return loader.get_by_name(name)


def load_cards_by_names(names: list[str]) -> pd.DataFrame:
    """
    Load multiple cards by exact name matches.
    
    Legacy function for backward compatibility.
    
    Args:
        names: List of card names to search for
    
    Returns:
        DataFrame containing matching cards
    
    Deprecated:
        Use AllCardsLoader().get_by_names() instead.
    """
    _deprecation_warning("load_cards_by_names()", "AllCardsLoader().get_by_names()")
    
    if not USE_ALL_CARDS_FILE:
        logger.warning("USE_ALL_CARDS_FILE is disabled, returning empty DataFrame")
        return pd.DataFrame()
    
    loader = _get_loader()
    return loader.get_by_names(names)


def load_cards_by_type(type_str: str) -> pd.DataFrame:
    """
    Load cards by type line (partial match).
    
    Legacy function for backward compatibility.
    
    Args:
        type_str: Type string to search for (e.g., "Creature", "Instant")
    
    Returns:
        DataFrame containing cards matching the type
    
    Deprecated:
        Use AllCardsLoader().filter_by_type() instead.
    """
    _deprecation_warning("load_cards_by_type()", "AllCardsLoader().filter_by_type()")
    
    if not USE_ALL_CARDS_FILE:
        logger.warning("USE_ALL_CARDS_FILE is disabled, returning empty DataFrame")
        return pd.DataFrame()
    
    loader = _get_loader()
    return loader.filter_by_type(type_str)


def load_cards_with_tag(tag: str) -> pd.DataFrame:
    """
    Load cards containing a specific theme tag.
    
    Legacy function for backward compatibility.
    
    Args:
        tag: Theme tag to search for
    
    Returns:
        DataFrame containing cards with the tag
    
    Deprecated:
        Use AllCardsLoader().filter_by_themes() instead.
    """
    _deprecation_warning("load_cards_with_tag()", "AllCardsLoader().filter_by_themes()")
    
    if not USE_ALL_CARDS_FILE:
        logger.warning("USE_ALL_CARDS_FILE is disabled, returning empty DataFrame")
        return pd.DataFrame()
    
    loader = _get_loader()
    return loader.filter_by_themes([tag], mode="any")


def load_cards_with_tags(tags: list[str], require_all: bool = False) -> pd.DataFrame:
    """
    Load cards containing theme tags.
    
    Legacy function for backward compatibility.
    
    Args:
        tags: List of theme tags to search for
        require_all: If True, card must have all tags; if False, at least one tag
    
    Returns:
        DataFrame containing cards matching the tag criteria
    
    Deprecated:
        Use AllCardsLoader().filter_by_themes() instead.
    """
    _deprecation_warning(
        "load_cards_with_tags()", "AllCardsLoader().filter_by_themes()"
    )
    
    if not USE_ALL_CARDS_FILE:
        logger.warning("USE_ALL_CARDS_FILE is disabled, returning empty DataFrame")
        return pd.DataFrame()
    
    loader = _get_loader()
    mode = "all" if require_all else "any"
    return loader.filter_by_themes(tags, mode=mode)


def load_cards_by_color_identity(colors: list[str]) -> pd.DataFrame:
    """
    Load cards by color identity.
    
    Legacy function for backward compatibility.
    
    Args:
        colors: List of color codes (e.g., ["W", "U"])
    
    Returns:
        DataFrame containing cards matching the color identity
    
    Deprecated:
        Use AllCardsLoader().filter_by_color_identity() instead.
    """
    _deprecation_warning(
        "load_cards_by_color_identity()", "AllCardsLoader().filter_by_color_identity()"
    )
    
    if not USE_ALL_CARDS_FILE:
        logger.warning("USE_ALL_CARDS_FILE is disabled, returning empty DataFrame")
        return pd.DataFrame()
    
    loader = _get_loader()
    return loader.filter_by_color_identity(colors)


def search_cards(query: str, limit: int = 100) -> pd.DataFrame:
    """
    Search cards by text query.
    
    Legacy function for backward compatibility.
    
    Args:
        query: Search query string
        limit: Maximum number of results
    
    Returns:
        DataFrame containing matching cards
    
    Deprecated:
        Use AllCardsLoader().search() instead.
    """
    _deprecation_warning("search_cards()", "AllCardsLoader().search()")
    
    if not USE_ALL_CARDS_FILE:
        logger.warning("USE_ALL_CARDS_FILE is disabled, returning empty DataFrame")
        return pd.DataFrame()
    
    loader = _get_loader()
    return loader.search(query, limit=limit)


def clear_card_cache() -> None:
    """
    Clear the cached card data, forcing next load to read from disk.
    
    Legacy function for backward compatibility.
    
    Deprecated:
        Use AllCardsLoader().clear_cache() instead.
    """
    _deprecation_warning("clear_card_cache()", "AllCardsLoader().clear_cache()")
    
    global _shared_loader
    if _shared_loader is not None:
        _shared_loader.clear_cache()
        _shared_loader = None
