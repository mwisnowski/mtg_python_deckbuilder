"""
Card Query Builder

Provides a fluent API for building complex card queries against the consolidated all_cards.parquet.

Usage:
    from code.services.card_query_builder import CardQueryBuilder
    
    # Simple query
    builder = CardQueryBuilder()
    cards = builder.colors(["W", "U"]).execute()
    
    # Complex query
    cards = (CardQueryBuilder()
        .colors(["G"])
        .themes(["tokens"], mode="any")
        .types("Creature")
        .limit(20)
        .execute())
    
    # Get specific cards
    cards = CardQueryBuilder().names(["Sol Ring", "Lightning Bolt"]).execute()
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from code.services.all_cards_loader import AllCardsLoader


class CardQueryBuilder:
    """Fluent API for building card queries."""

    def __init__(self, loader: Optional[AllCardsLoader] = None) -> None:
        """
        Initialize CardQueryBuilder.

        Args:
            loader: AllCardsLoader instance (creates default if None)
        """
        self._loader = loader or AllCardsLoader()
        self._color_filter: Optional[list[str]] = None
        self._theme_filter: Optional[list[str]] = None
        self._theme_mode: str = "any"
        self._type_filter: Optional[str] = None
        self._name_filter: Optional[list[str]] = None
        self._search_query: Optional[str] = None
        self._limit: Optional[int] = None

    def colors(self, colors: list[str]) -> CardQueryBuilder:
        """
        Filter by color identity.

        Args:
            colors: List of color codes (e.g., ["W", "U"])

        Returns:
            Self for chaining
        """
        self._color_filter = colors
        return self

    def themes(self, themes: list[str], mode: str = "any") -> CardQueryBuilder:
        """
        Filter by theme tags.

        Args:
            themes: List of theme tags
            mode: "any" (at least one) or "all" (must have all)

        Returns:
            Self for chaining
        """
        self._theme_filter = themes
        self._theme_mode = mode
        return self

    def types(self, type_query: str) -> CardQueryBuilder:
        """
        Filter by type line (partial match).

        Args:
            type_query: Type string to search for

        Returns:
            Self for chaining
        """
        self._type_filter = type_query
        return self

    def names(self, names: list[str]) -> CardQueryBuilder:
        """
        Filter by specific card names (batch lookup).

        Args:
            names: List of card names

        Returns:
            Self for chaining
        """
        self._name_filter = names
        return self

    def search(self, query: str) -> CardQueryBuilder:
        """
        Add text search across name, type, and oracle text.

        Args:
            query: Search query string

        Returns:
            Self for chaining
        """
        self._search_query = query
        return self

    def limit(self, limit: int) -> CardQueryBuilder:
        """
        Limit number of results.

        Args:
            limit: Maximum number of results

        Returns:
            Self for chaining
        """
        self._limit = limit
        return self

    def execute(self) -> pd.DataFrame:
        """
        Execute the query and return results.

        Returns:
            DataFrame containing matching cards
        """
        # Start with all cards or specific names
        if self._name_filter:
            df = self._loader.get_by_names(self._name_filter)
        else:
            df = self._loader.load()

        # Apply color filter
        if self._color_filter:
            color_results = self._loader.filter_by_color_identity(self._color_filter)
            df = df[df.index.isin(color_results.index)]

        # Apply theme filter
        if self._theme_filter:
            theme_results = self._loader.filter_by_themes(self._theme_filter, mode=self._theme_mode)
            df = df[df.index.isin(theme_results.index)]

        # Apply type filter
        if self._type_filter:
            type_results = self._loader.filter_by_type(self._type_filter)
            df = df[df.index.isin(type_results.index)]

        # Apply text search
        if self._search_query:
            search_results = self._loader.search(self._search_query, limit=999999)
            df = df[df.index.isin(search_results.index)]

        # Apply limit
        if self._limit and len(df) > self._limit:
            df = df.head(self._limit)

        return df

    def count(self) -> int:
        """
        Count results without returning full DataFrame.

        Returns:
            Number of matching cards
        """
        return len(self.execute())

    def first(self) -> Optional[pd.Series]:
        """
        Get first result only.

        Returns:
            First matching card as Series, or None if no results
        """
        results = self.execute()
        if results.empty:
            return None
        return results.iloc[0]

    def reset(self) -> CardQueryBuilder:
        """
        Reset all filters.

        Returns:
            Self for chaining
        """
        self._color_filter = None
        self._theme_filter = None
        self._theme_mode = "any"
        self._type_filter = None
        self._name_filter = None
        self._search_query = None
        self._limit = None
        return self
