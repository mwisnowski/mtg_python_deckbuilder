"""Error message templates for validation errors.

Provides consistent, user-friendly error messages for validation failures.
"""
from __future__ import annotations

from typing import List


class ValidationMessages:
    """Standard validation error messages."""
    
    # Commander validation
    COMMANDER_REQUIRED = "Commander name is required"
    COMMANDER_INVALID = "Commander '{name}' not found in database"
    COMMANDER_NOT_LEGENDARY = "'{name}' is not a Legendary creature (cannot be commander)"
    COMMANDER_CANNOT_COMMAND = "'{name}' cannot be a commander"
    
    # Partner validation
    PARTNER_REQUIRES_NAME = "Partner mode requires a partner commander name"
    BACKGROUND_REQUIRES_NAME = "Background mode requires a background name"
    PARTNER_NAME_REQUIRES_MODE = "Partner name specified but partner mode not set"
    BACKGROUND_INVALID_MODE = "Background name only valid with background partner mode"
    
    # Theme validation
    THEME_INVALID = "Theme '{name}' not found in catalog"
    THEMES_INVALID = "Invalid themes: {names}"
    THEME_REQUIRED = "At least one theme is required"
    
    # Card validation
    CARD_NOT_FOUND = "Card '{name}' not found in database"
    CARD_NAME_EMPTY = "Card name cannot be empty"
    CARDS_NOT_FOUND = "Cards not found: {names}"
    
    # Bracket validation
    BRACKET_INVALID = "Power bracket must be between 1 and 4"
    BRACKET_EXCEEDED = "'{name}' is bracket {card_bracket}, exceeds limit of {limit}"
    
    # Color validation
    COLOR_IDENTITY_MISMATCH = "Card '{name}' colors ({card_colors}) exceed commander colors ({commander_colors})"
    
    # Custom theme validation
    CUSTOM_THEME_REQUIRES_NAME_AND_TAGS = "Custom theme requires both name and tags"
    CUSTOM_THEME_NAME_REQUIRED = "Custom theme tags require a theme name"
    CUSTOM_THEME_TAGS_REQUIRED = "Custom theme name requires tags"
    
    # List validation
    MUST_INCLUDE_TOO_MANY = "Must-include list cannot exceed 99 cards"
    MUST_EXCLUDE_TOO_MANY = "Must-exclude list cannot exceed 500 cards"
    
    # Batch validation
    BATCH_COUNT_INVALID = "Batch count must be between 1 and 10"
    BATCH_COUNT_EXCEEDED = "Batch count cannot exceed 10"
    
    # File validation
    FILE_CONTENT_EMPTY = "File content cannot be empty"
    FILE_FORMAT_INVALID = "File format '{format}' not supported"
    
    # General
    VALUE_REQUIRED = "Value is required"
    VALUE_TOO_LONG = "Value exceeds maximum length of {max_length}"
    VALUE_TOO_SHORT = "Value must be at least {min_length} characters"
    
    @staticmethod
    def format_commander_invalid(name: str) -> str:
        """Format commander invalid message."""
        return ValidationMessages.COMMANDER_INVALID.format(name=name)
    
    @staticmethod
    def format_commander_not_legendary(name: str) -> str:
        """Format commander not legendary message."""
        return ValidationMessages.COMMANDER_NOT_LEGENDARY.format(name=name)
    
    @staticmethod
    def format_theme_invalid(name: str) -> str:
        """Format theme invalid message."""
        return ValidationMessages.THEME_INVALID.format(name=name)
    
    @staticmethod
    def format_themes_invalid(names: List[str]) -> str:
        """Format multiple invalid themes message."""
        return ValidationMessages.THEMES_INVALID.format(names=", ".join(names))
    
    @staticmethod
    def format_card_not_found(name: str) -> str:
        """Format card not found message."""
        return ValidationMessages.CARD_NOT_FOUND.format(name=name)
    
    @staticmethod
    def format_cards_not_found(names: List[str]) -> str:
        """Format multiple cards not found message."""
        return ValidationMessages.CARDS_NOT_FOUND.format(names=", ".join(names))
    
    @staticmethod
    def format_bracket_exceeded(name: str, card_bracket: int, limit: int) -> str:
        """Format bracket exceeded message."""
        return ValidationMessages.BRACKET_EXCEEDED.format(
            name=name,
            card_bracket=card_bracket,
            limit=limit
        )
    
    @staticmethod
    def format_color_mismatch(name: str, card_colors: str, commander_colors: str) -> str:
        """Format color identity mismatch message."""
        return ValidationMessages.COLOR_IDENTITY_MISMATCH.format(
            name=name,
            card_colors=card_colors,
            commander_colors=commander_colors
        )
    
    @staticmethod
    def format_file_format_invalid(format_type: str) -> str:
        """Format invalid file format message."""
        return ValidationMessages.FILE_FORMAT_INVALID.format(format=format_type)
    
    @staticmethod
    def format_value_too_long(max_length: int) -> str:
        """Format value too long message."""
        return ValidationMessages.VALUE_TOO_LONG.format(max_length=max_length)
    
    @staticmethod
    def format_value_too_short(min_length: int) -> str:
        """Format value too short message."""
        return ValidationMessages.VALUE_TOO_SHORT.format(min_length=min_length)


# Convenience access
MSG = ValidationMessages
