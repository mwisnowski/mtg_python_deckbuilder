"""Pydantic models for theme catalog (Phase C groundwork).

These mirror the merged catalog structure produced by build_theme_catalog.py.
They are intentionally minimal now; editorial extensions (examples, archetypes) will
be added in later phases.
"""
from __future__ import annotations

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
import os
import sys


ALLOWED_DECK_ARCHETYPES: List[str] = [
    'Graveyard', 'Tokens', 'Counters', 'Spells', 'Artifacts', 'Enchantments', 'Lands', 'Politics', 'Combo',
    'Aggro', 'Control', 'Midrange', 'Stax', 'Ramp', 'Toolbox'
]

PopularityBucket = Literal['Very Common', 'Common', 'Uncommon', 'Niche', 'Rare']


class ThemeEntry(BaseModel):
    id: Optional[str] = Field(
        None,
        description="Stable, slugified identifier for the theme (mirrors fast-path catalog id); optional for backward compatibility.",
    )
    theme: str = Field(..., description="Canonical theme display name")
    synergies: List[str] = Field(default_factory=list, description="Ordered synergy list (curated > enforced > inferred, possibly trimmed)")
    primary_color: Optional[str] = Field(None, description="Primary color (TitleCase) if detectable")
    secondary_color: Optional[str] = Field(None, description="Secondary color (TitleCase) if detectable")
    # Phase D editorial enhancements (optional)
    example_commanders: List[str] = Field(default_factory=list, description="Curated example commanders illustrating the theme")
    example_cards: List[str] = Field(default_factory=list, description="Representative non-commander cards (short, curated list)")
    synergy_example_cards: List[str] = Field(default_factory=list, description="Optional curated synergy-relevant cards distinct from general example_cards")
    synergy_commanders: List[str] = Field(default_factory=list, description="Commanders surfaced from top synergies (3/2/1 from top three synergies)")
    deck_archetype: Optional[str] = Field(
        None,
        description="Higher-level archetype cluster (enumerated); validated against ALLOWED_DECK_ARCHETYPES",
    )
    popularity_hint: Optional[str] = Field(None, description="Optional editorial popularity or guidance note or derived bucket label")
    popularity_bucket: Optional[PopularityBucket] = Field(
        None, description="Derived frequency bucket for theme prevalence (Very Common/Common/Uncommon/Niche/Rare)"
    )
    description: Optional[str] = Field(
        None,
        description="Auto-generated or curated short sentence/paragraph describing the deck plan / strategic intent of the theme",
    )
    editorial_quality: Optional[str] = Field(
        None,
        description="Lifecycle quality flag (draft|reviewed|final); optional and not yet enforced strictly",
    )

    model_config = ConfigDict(extra='forbid')


class ThemeMetadataInfo(BaseModel):
    """Renamed from 'ThemeProvenance' for clearer semantic meaning.

    Backward compatibility: JSON/YAML that still uses 'provenance' will be loaded and mapped.
    """
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
    metadata_info: ThemeMetadataInfo | None = Field(None, description="Catalog-level generation metadata (formerly 'provenance')")
    # Backward compatibility shim: accept 'provenance' during parsing
    provenance: ThemeMetadataInfo | None = Field(None, description="(Deprecated) legacy key; prefer 'metadata_info'")
    # Optional editorial analytics artifact (behind env flag); flexible structure so keep as dict
    description_fallback_summary: Dict[str, Any] | None = Field(
        None,
        description="Aggregate fallback description metrics injected when EDITORIAL_INCLUDE_FALLBACK_SUMMARY=1",
    )

    model_config = ConfigDict(extra='forbid')

    def theme_names(self) -> List[str]:  # convenience
        return [t.theme for t in self.themes]

    def model_post_init(self, __context: Any) -> None:
        # If only legacy 'provenance' provided, alias to metadata_info
        if self.metadata_info is None and self.provenance is not None:
            object.__setattr__(self, 'metadata_info', self.provenance)
        # If both provided emit deprecation warning (one-time per process) unless suppressed
        if self.metadata_info is not None and self.provenance is not None:
            if not os.environ.get('SUPPRESS_PROVENANCE_DEPRECATION') and not getattr(sys.modules.setdefault('__meta_warn_state__', object()), 'catalog_warned', False):
                try:
                    # Mark warned
                    setattr(sys.modules['__meta_warn_state__'], 'catalog_warned', True)
                except Exception:
                    pass
                print("[deprecation] Both 'metadata_info' and legacy 'provenance' present in catalog. 'provenance' will be removed in 2.4.0 (2025-11-01)", file=sys.stderr)

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
    synergy_example_cards: List[str] = Field(default_factory=list)
    synergy_commanders: List[str] = Field(default_factory=list)
    deck_archetype: Optional[str] = None
    popularity_hint: Optional[str] = None  # Free-form editorial note; bucket computed during merge
    popularity_bucket: Optional[PopularityBucket] = None  # Authors may pin; else derived
    description: Optional[str] = None  # Curated short description (auto-generated if absent)
    # Editorial quality lifecycle flag (draft|reviewed|final); optional and not yet enforced via governance.
    editorial_quality: Optional[str] = None
    # Per-file metadata (recently renamed from provenance). We intentionally keep this
    # flexible (dict) because individual theme YAMLs may accumulate forward-compatible
    # keys during editorial workflows. Catalog-level strongly typed metadata lives in
    # ThemeCatalog.metadata_info; this per-theme block is mostly backfill / lifecycle hints.
    metadata_info: Dict[str, Any] = Field(default_factory=dict, description="Per-theme lifecycle / editorial metadata (renamed from provenance)")
    provenance: Optional[Dict[str, Any]] = Field(default=None, description="(Deprecated) legacy key; will be dropped after migration window")

    model_config = ConfigDict(extra='forbid')

    def model_post_init(self, __context: Any) -> None:
        if not self.metadata_info and self.provenance:
            object.__setattr__(self, 'metadata_info', self.provenance)
        if self.metadata_info and self.provenance:
            if not os.environ.get('SUPPRESS_PROVENANCE_DEPRECATION') and not getattr(sys.modules.setdefault('__meta_warn_state__', object()), 'yaml_warned', False):
                try:
                    setattr(sys.modules['__meta_warn_state__'], 'yaml_warned', True)
                except Exception:
                    pass
                print("[deprecation] Theme YAML defines both 'metadata_info' and legacy 'provenance'; legacy key removed in 2.4.0 (2025-11-01)", file=sys.stderr)
