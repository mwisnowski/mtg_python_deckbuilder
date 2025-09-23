from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class ThemeSummary(BaseModel):
    id: str
    theme: str
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    popularity_bucket: Optional[str] = None
    deck_archetype: Optional[str] = None
    description: Optional[str] = None
    synergies: List[str] = Field(default_factory=list)
    synergy_count: int = 0
    # Diagnostics-only fields (gated by flag)
    has_fallback_description: Optional[bool] = None
    editorial_quality: Optional[str] = None


class ThemeDetail(ThemeSummary):
    curated_synergies: List[str] = Field(default_factory=list)
    enforced_synergies: List[str] = Field(default_factory=list)
    inferred_synergies: List[str] = Field(default_factory=list)
    example_commanders: List[str] = Field(default_factory=list)
    example_cards: List[str] = Field(default_factory=list)
    synergy_commanders: List[str] = Field(default_factory=list)
    # Diagnostics-only optional uncapped list
    uncapped_synergies: Optional[List[str]] = None
