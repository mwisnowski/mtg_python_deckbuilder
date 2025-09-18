"""Pydantic models for theme catalog (Phase C groundwork).

These mirror the merged catalog structure produced by build_theme_catalog.py.
They are intentionally minimal now; editorial extensions (examples, archetypes) will
be added in later phases.
"""
from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class ThemeEntry(BaseModel):
    theme: str = Field(..., description="Canonical theme display name")
    synergies: List[str] = Field(default_factory=list, description="Ordered synergy list (curated > enforced > inferred, possibly trimmed)")
    primary_color: Optional[str] = Field(None, description="Primary color (TitleCase) if detectable")
    secondary_color: Optional[str] = Field(None, description="Secondary color (TitleCase) if detectable")
    # Phase D editorial enhancements (optional)
    example_commanders: List[str] = Field(default_factory=list, description="Curated example commanders illustrating the theme")
    example_cards: List[str] = Field(default_factory=list, description="Representative non-commander cards (short, curated list)")
    synergy_commanders: List[str] = Field(default_factory=list, description="Commanders surfaced from top synergies (3/2/1 from top three synergies)")
    deck_archetype: Optional[str] = Field(None, description="Higher-level archetype cluster (e.g., Graveyard, Tokens, Counters)")
    popularity_hint: Optional[str] = Field(None, description="Optional editorial popularity or guidance note")

    model_config = ConfigDict(extra='forbid')


class ThemeProvenance(BaseModel):
    mode: str = Field(..., description="Generation mode (e.g., merge)")
    generated_at: str = Field(..., description="ISO timestamp of generation")
    curated_yaml_files: int = Field(..., ge=0)
    synergy_cap: int | None = Field(None, ge=0)
    inference: str = Field(..., description="Inference method description")
    version: str = Field(..., description="Catalog build version identifier")

    model_config = ConfigDict(extra='allow')  # allow forward-compatible fields


class ThemeCatalog(BaseModel):
    themes: List[ThemeEntry]
    frequencies_by_base_color: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    generated_from: str
    provenance: ThemeProvenance

    model_config = ConfigDict(extra='forbid')

    def theme_names(self) -> List[str]:  # convenience
        return [t.theme for t in self.themes]

    def as_dict(self) -> Dict[str, Any]:  # explicit dict export
        return self.model_dump()


class ThemeYAMLFile(BaseModel):
    id: str
    display_name: str
    synergies: List[str]
    curated_synergies: List[str] = Field(default_factory=list)
    enforced_synergies: List[str] = Field(default_factory=list)
    inferred_synergies: List[str] = Field(default_factory=list)
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    notes: Optional[str] = ''
    # Phase D optional editorial metadata (may be absent in existing YAMLs)
    example_commanders: List[str] = Field(default_factory=list)
    example_cards: List[str] = Field(default_factory=list)
    synergy_commanders: List[str] = Field(default_factory=list)
    deck_archetype: Optional[str] = None
    popularity_hint: Optional[str] = None

    model_config = ConfigDict(extra='forbid')
