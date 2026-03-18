"""Custom validators for business logic validation.

Provides validators for themes, commanders, and other domain-specific validation.
"""
from __future__ import annotations

from typing import List, Tuple, Optional
import pandas as pd


class ThemeValidator:
    """Validates theme tags against theme catalog."""
    
    def __init__(self) -> None:
        """Initialize validator."""
        self._themes: set[str] = set()
        self._loaded = False
    
    def _ensure_loaded(self) -> None:
        """Lazy-load theme catalog."""
        if self._loaded:
            return
        
        try:
            from ..services import theme_catalog_loader
            catalog = theme_catalog_loader.get_theme_catalog()
            
            if not catalog.empty and 'name' in catalog.columns:
                for theme in catalog['name'].dropna():
                    theme_str = str(theme).strip()
                    if theme_str:
                        self._themes.add(theme_str)
                        # Also add lowercase version for case-insensitive matching
                        self._themes.add(theme_str.lower())
            
            self._loaded = True
        except Exception:
            self._loaded = True
    
    def is_valid(self, theme: str) -> bool:
        """Check if theme exists in catalog.
        
        Args:
            theme: Theme tag to validate
            
        Returns:
            True if theme is valid
        """
        self._ensure_loaded()
        
        if not theme or not theme.strip():
            return False
        
        # Check exact match and case-insensitive
        return theme in self._themes or theme.lower() in self._themes
    
    def validate_themes(self, themes: List[str]) -> Tuple[List[str], List[str]]:
        """Validate a list of themes.
        
        Args:
            themes: List of theme tags
            
        Returns:
            (valid_themes, invalid_themes) tuple
        """
        self._ensure_loaded()
        
        valid: List[str] = []
        invalid: List[str] = []
        
        for theme in themes:
            if not theme or not theme.strip():
                continue
            
            if self.is_valid(theme):
                valid.append(theme)
            else:
                invalid.append(theme)
        
        return valid, invalid
    
    def get_all_themes(self) -> List[str]:
        """Get all available themes.
        
        Returns:
            List of theme names
        """
        self._ensure_loaded()
        # Return case-preserved versions
        return sorted([t for t in self._themes if t and t[0].isupper()])


class PowerBracketValidator:
    """Validates power bracket values and card compliance."""
    
    @staticmethod
    def is_valid_bracket(bracket: int) -> bool:
        """Check if bracket value is valid (1-4).
        
        Args:
            bracket: Power bracket value
            
        Returns:
            True if valid (1-4)
        """
        return isinstance(bracket, int) and 1 <= bracket <= 4
    
    @staticmethod
    def validate_card_for_bracket(card_name: str, bracket: int) -> Tuple[bool, Optional[str]]:
        """Check if card is allowed in power bracket.
        
        Args:
            card_name: Card name to check
            bracket: Target power bracket (1-4)
            
        Returns:
            (is_allowed, error_message) tuple
        """
        if not PowerBracketValidator.is_valid_bracket(bracket):
            return False, f"Invalid power bracket: {bracket}"
        
        try:
            from deck_builder import builder_utils as bu
            df = bu._load_all_cards_parquet()
            
            if df.empty:
                return True, None  # Assume allowed if no data
            
            card_row = df[df['name'] == card_name]
            
            if card_row.empty:
                return False, f"Card '{card_name}' not found"
            
            # Check bracket column if it exists
            if 'bracket' in card_row.columns:
                card_bracket = card_row['bracket'].iloc[0]
                if pd.notna(card_bracket):
                    card_bracket_int = int(card_bracket)
                    if card_bracket_int > bracket:
                        return False, f"'{card_name}' is bracket {card_bracket_int}, exceeds limit of {bracket}"
            
            return True, None
        
        except Exception:
            # Defensive: assume allowed if check fails
            return True, None


class ColorIdentityValidator:
    """Validates color identity constraints."""
    
    @staticmethod
    def parse_colors(color_str: str) -> set[str]:
        """Parse color identity string to set.
        
        Args:
            color_str: Color string (e.g., "W,U,B" or "Grixis")
            
        Returns:
            Set of color codes (W, U, B, R, G, C)
        """
        if not color_str:
            return set()
        
        # Handle comma-separated
        if ',' in color_str:
            return {c.strip().upper() for c in color_str.split(',') if c.strip()}
        
        # Handle concatenated (e.g., "WUB")
        colors = set()
        for char in color_str.upper():
            if char in 'WUBRGC':
                colors.add(char)
        
        return colors
    
    @staticmethod
    def is_subset(card_colors: set[str], commander_colors: set[str]) -> bool:
        """Check if card colors are subset of commander colors.
        
        Args:
            card_colors: Card's color identity
            commander_colors: Commander's color identity
            
        Returns:
            True if card is valid in commander's colors
        """
        # Colorless cards (C) are valid in any deck
        if card_colors == {'C'} or not card_colors:
            return True
        
        # Check if card colors are subset of commander colors
        return card_colors.issubset(commander_colors)


# Global validator instances
_theme_validator: Optional[ThemeValidator] = None
_bracket_validator: Optional[PowerBracketValidator] = None
_color_validator: Optional[ColorIdentityValidator] = None


def get_theme_validator() -> ThemeValidator:
    """Get global theme validator instance."""
    global _theme_validator
    if _theme_validator is None:
        _theme_validator = ThemeValidator()
    return _theme_validator


def get_bracket_validator() -> PowerBracketValidator:
    """Get global bracket validator instance."""
    global _bracket_validator
    if _bracket_validator is None:
        _bracket_validator = PowerBracketValidator()
    return _bracket_validator


def get_color_validator() -> ColorIdentityValidator:
    """Get global color validator instance."""
    global _color_validator
    if _color_validator is None:
        _color_validator = ColorIdentityValidator()
    return _color_validator
