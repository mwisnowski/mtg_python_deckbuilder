"""Pydantic models for request validation.

Defines typed models for all web route inputs with automatic validation.
"""
from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum


class PowerBracket(int, Enum):
    """Power bracket enumeration (1-4)."""
    BRACKET_1 = 1
    BRACKET_2 = 2
    BRACKET_3 = 3
    BRACKET_4 = 4


class DeckMode(str, Enum):
    """Deck building mode."""
    STANDARD = "standard"
    RANDOM = "random"
    HEADLESS = "headless"


class OwnedMode(str, Enum):
    """Owned cards usage mode."""
    OFF = "off"
    PREFER = "prefer"
    ONLY = "only"


class CommanderPartnerType(str, Enum):
    """Commander partner configuration type."""
    SINGLE = "single"
    PARTNER = "partner"
    BACKGROUND = "background"
    PARTNER_WITH = "partner_with"


class BuildRequest(BaseModel):
    """Build request validation model."""
    
    commander: str = Field(..., min_length=1, max_length=200, description="Commander card name")
    themes: List[str] = Field(default_factory=list, max_length=5, description="Theme tags")
    power_bracket: PowerBracket = Field(default=PowerBracket.BRACKET_2, description="Power bracket (1-4)")
    
    # Partner configuration
    partner_mode: Optional[CommanderPartnerType] = Field(default=None, description="Partner type")
    partner_name: Optional[str] = Field(default=None, max_length=200, description="Partner commander name")
    background_name: Optional[str] = Field(default=None, max_length=200, description="Background name")
    
    # Owned cards
    owned_mode: OwnedMode = Field(default=OwnedMode.OFF, description="Owned cards mode")
    
    # Custom theme
    custom_theme_name: Optional[str] = Field(default=None, max_length=100, description="Custom theme name")
    custom_theme_tags: Optional[List[str]] = Field(default=None, max_length=20, description="Custom theme tags")
    
    # Include/exclude lists
    must_include: Optional[List[str]] = Field(default=None, max_length=99, description="Must-include card names")
    must_exclude: Optional[List[str]] = Field(default=None, max_length=500, description="Must-exclude card names")
    
    # Random modes
    random_commander: bool = Field(default=False, description="Randomize commander")
    random_themes: bool = Field(default=False, description="Randomize themes")
    random_seed: Optional[int] = Field(default=None, ge=0, description="Random seed")
    
    @field_validator("commander")
    @classmethod
    def validate_commander_not_empty(cls, v: str) -> str:
        """Ensure commander name is not just whitespace."""
        if not v or not v.strip():
            raise ValueError("Commander name cannot be empty")
        return v.strip()
    
    @field_validator("themes")
    @classmethod
    def validate_themes_unique(cls, v: List[str]) -> List[str]:
        """Ensure themes are unique and non-empty."""
        if not v:
            return []
        
        cleaned = [t.strip() for t in v if t and t.strip()]
        seen = set()
        unique = []
        for theme in cleaned:
            lower = theme.lower()
            if lower not in seen:
                seen.add(lower)
                unique.append(theme)
        
        return unique
    
    @model_validator(mode="after")
    def validate_partner_consistency(self) -> "BuildRequest":
        """Validate partner configuration consistency."""
        if self.partner_mode == CommanderPartnerType.PARTNER:
            if not self.partner_name:
                raise ValueError("Partner mode requires partner_name")
        
        if self.partner_mode == CommanderPartnerType.BACKGROUND:
            if not self.background_name:
                raise ValueError("Background mode requires background_name")
        
        if self.partner_name and not self.partner_mode:
            raise ValueError("partner_name requires partner_mode to be set")
        
        if self.background_name and self.partner_mode != CommanderPartnerType.BACKGROUND:
            raise ValueError("background_name only valid with background partner_mode")
        
        return self
    
    @model_validator(mode="after")
    def validate_custom_theme_consistency(self) -> "BuildRequest":
        """Validate custom theme requires both name and tags."""
        if self.custom_theme_name and not self.custom_theme_tags:
            raise ValueError("Custom theme requires both name and tags")
        
        if self.custom_theme_tags and not self.custom_theme_name:
            raise ValueError("Custom theme tags require theme name")
        
        return self


class CommanderSearchRequest(BaseModel):
    """Commander search/validation request."""
    
    query: str = Field(..., min_length=1, max_length=200, description="Search query")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results")
    
    @field_validator("query")
    @classmethod
    def validate_query_not_empty(cls, v: str) -> str:
        """Ensure query is not just whitespace."""
        if not v or not v.strip():
            raise ValueError("Search query cannot be empty")
        return v.strip()


class ThemeValidationRequest(BaseModel):
    """Theme validation request."""
    
    themes: List[str] = Field(..., min_length=1, max_length=10, description="Themes to validate")
    
    @field_validator("themes")
    @classmethod
    def validate_themes_not_empty(cls, v: List[str]) -> List[str]:
        """Ensure themes are not empty."""
        cleaned = [t.strip() for t in v if t and t.strip()]
        if not cleaned:
            raise ValueError("At least one valid theme required")
        return cleaned


class OwnedCardsImportRequest(BaseModel):
    """Owned cards import request."""
    
    format_type: str = Field(..., pattern="^(csv|txt|arena)$", description="File format")
    content: str = Field(..., min_length=1, description="File content")
    
    @field_validator("content")
    @classmethod
    def validate_content_not_empty(cls, v: str) -> str:
        """Ensure content is not empty."""
        if not v or not v.strip():
            raise ValueError("File content cannot be empty")
        return v


class BatchBuildRequest(BaseModel):
    """Batch build request for multiple variations."""
    
    base_config: BuildRequest = Field(..., description="Base build configuration")
    count: int = Field(..., ge=1, le=10, description="Number of builds to generate")
    variation_seed: Optional[int] = Field(default=None, ge=0, description="Seed for variations")
    
    @field_validator("count")
    @classmethod
    def validate_count_reasonable(cls, v: int) -> int:
        """Ensure batch count is reasonable."""
        if v > 10:
            raise ValueError("Batch count cannot exceed 10")
        return v


class CardReplacementRequest(BaseModel):
    """Card replacement request for compliance."""
    
    card_name: str = Field(..., min_length=1, max_length=200, description="Card to replace")
    reason: Optional[str] = Field(default=None, max_length=500, description="Replacement reason")
    
    @field_validator("card_name")
    @classmethod
    def validate_card_name_not_empty(cls, v: str) -> str:
        """Ensure card name is not empty."""
        if not v or not v.strip():
            raise ValueError("Card name cannot be empty")
        return v.strip()


class DeckExportRequest(BaseModel):
    """Deck export request."""
    
    format_type: str = Field(..., pattern="^(csv|txt|json|arena)$", description="Export format")
    include_commanders: bool = Field(default=True, description="Include commanders in export")
    include_lands: bool = Field(default=True, description="Include lands in export")
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True
