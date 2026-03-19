"""Theme editorial service for quality scoring and metadata management.

Roadmap R12 Milestones 1-2: Editorial Fields + Heuristics Externalization
Phase E+ enhancement for theme catalog editorial metadata.

Responsibilities:
 - Calculate editorial quality scores for theme entries
 - Validate editorial field completeness and consistency
 - Suggest example commanders and cards for themes
 - Infer deck archetypes from theme patterns
 - Calculate popularity buckets from commander/card counts
 - Load and apply external editorial heuristics
 - Provide editorial metadata APIs for frontend consumption

Follows R9 Backend Unification patterns:
 - Extends BaseService
 - Uses structured error handling (ValidationError, NotFoundError)
 - Integrates with existing theme_catalog_loader infrastructure
 - Provides telemetry integration points
"""
from __future__ import annotations

from typing import Dict, List, Optional, Any
from pathlib import Path
import logging
import yaml

from .base import BaseService, NotFoundError
from .theme_catalog_loader import load_index, slugify

try:
    from type_definitions_theme_catalog import ThemeEntry, PopularityBucket, ALLOWED_DECK_ARCHETYPES, DescriptionSource
except ImportError:  # pragma: no cover
    from code.type_definitions_theme_catalog import ThemeEntry, PopularityBucket, ALLOWED_DECK_ARCHETYPES, DescriptionSource

logger = logging.getLogger(__name__)

# Default heuristics path (can be overridden in __init__)
# Path calculation: from code/web/services/ → code/web/ → code/ → project root
DEFAULT_HEURISTICS_PATH = Path(__file__).resolve().parents[3] / 'config' / 'themes' / 'editorial_heuristics.yml'

# Legacy constants (will be loaded from heuristics file in M2, kept for backward compatibility)
WEIGHT_HAS_DESCRIPTION = 20
WEIGHT_HAS_EXAMPLE_COMMANDERS = 15
WEIGHT_HAS_EXAMPLE_CARDS = 15
WEIGHT_HAS_DECK_ARCHETYPE = 10
WEIGHT_HAS_POPULARITY_BUCKET = 10
WEIGHT_HAS_SYNERGY_COMMANDERS = 10
WEIGHT_DESCRIPTION_LENGTH_BONUS = 10
WEIGHT_MULTIPLE_EXAMPLE_COMMANDERS = 10
WEIGHT_MULTIPLE_EXAMPLE_CARDS = 10

QUALITY_EXCELLENT = 85
QUALITY_GOOD = 65
QUALITY_FAIR = 40

DEFAULT_POPULARITY_BOUNDARIES = [40, 100, 220, 500]

ARCHETYPE_KEYWORDS: Dict[str, List[str]] = {
    'Combo': ['combo', 'infinite', 'storm'],
    'Stax': ['stax', 'tax', 'lock', 'denial'],
    'Voltron': ['voltron', 'aura', 'equipment'],
    'Aggro': ['aggro', 'burn', 'fast', 'pressure', 'combat'],
    'Control': ['control', 'counter', 'removal', 'wipes'],
    'Midrange': ['midrange', 'value', 'flexible'],
    'Graveyard': ['graveyard', 'reanimate', 'dredge', 'recursion'],
    'Tokens': ['tokens', 'wide', 'go-wide'],
    'Counters': ['+1/+1', 'counters', 'proliferate'],
    'Ramp': ['ramp', 'big-mana', 'lands'],
    'Spells': ['spellslinger', 'spells-matter', 'instants', 'sorceries'],
    'Artifacts': ['artifacts', 'artifact-matters'],
    'Enchantments': ['enchantments', 'enchantress', 'constellation'],
    'Politics': ['group-hug', 'pillowfort', 'politics', 'monarch'],
    'Toolbox': ['toolbox', 'tutor', 'silver-bullet'],
}


class ThemeEditorialService(BaseService):
    """Service for theme editorial quality scoring and metadata management.
    
    Extends BaseService following R9 patterns. M2 enhancement: loads external heuristics.
    """
    
    def __init__(self, heuristics_path: Optional[Path] = None) -> None:
        """Initialize editorial service with optional heuristics override.
        
        Args:
            heuristics_path: Optional path to editorial_heuristics.yml (defaults to config/themes/)
        """
        super().__init__()
        self._heuristics_path = heuristics_path or DEFAULT_HEURISTICS_PATH
        self._heuristics_cache: Optional[Dict[str, Any]] = None
    
    def load_heuristics(self, force_reload: bool = False) -> Dict[str, Any]:
        """Load editorial heuristics from YAML file (cached).
        
        Args:
            force_reload: If True, bypass cache and reload from disk
            
        Returns:
            Dictionary with heuristics configuration
            
        Raises:
            NotFoundError: If heuristics file doesn't exist
            ValidationError: If heuristics file is invalid
        """
        if self._heuristics_cache and not force_reload:
            return self._heuristics_cache
        
        if not self._heuristics_path.exists():
            # Fallback to legacy behavior if heuristics file not found (cache the fallback)
            logger.warning(f"Heuristics file not found at {self._heuristics_path}, using legacy constants")
            self._heuristics_cache = {
                'quality_thresholds': {
                    'excellent_min_score': QUALITY_EXCELLENT,
                    'good_min_score': QUALITY_GOOD,
                    'fair_min_score': QUALITY_FAIR,
                    'manual_description_bonus': 10,
                    'rule_description_bonus': 5,
                    'generic_description_bonus': 0,
                },
                'generic_staple_cards': [],
                'archetype_keywords': ARCHETYPE_KEYWORDS,
            }
            return self._heuristics_cache
        
        try:
            with open(self._heuristics_path, 'r', encoding='utf-8') as f:
                self._heuristics_cache = yaml.safe_load(f)
            
            # Basic validation
            if not isinstance(self._heuristics_cache, dict):
                raise ValueError("Heuristics file must contain a YAML dictionary")
            
            required_keys = ['quality_thresholds', 'generic_staple_cards']
            for key in required_keys:
                if key not in self._heuristics_cache:
                    logger.warning(f"Heuristics missing required key: {key}")
            
            logger.info(f"Loaded editorial heuristics from {self._heuristics_path}")
            return self._heuristics_cache
            
        except Exception as e:
            logger.error(f"Failed to load heuristics: {e}")
            raise NotFoundError(f"Failed to load editorial heuristics: {e}")
    
    def get_generic_staple_cards(self) -> List[str]:
        """Get list of generic staple cards from heuristics.
        
        Returns:
            List of card names considered generic/staples
        """
        heuristics = self.load_heuristics()
        return heuristics.get('generic_staple_cards', [])
    
    def is_generic_card(self, card_name: str) -> bool:
        """Check if a card is considered a generic staple.
        
        Args:
            card_name: Card name to check
            
        Returns:
            True if card is in generic staples list
        """
        generic_cards = self.get_generic_staple_cards()
        return card_name in generic_cards
    
    def get_theme_metadata(self, theme_name: str) -> Dict[str, Any]:
        """Retrieve editorial metadata for a theme.
        
        Args:
            theme_name: Theme display name (e.g., "Aristocrats")
            
        Returns:
            Dictionary with editorial metadata including:
            - theme: Theme display name
            - description: Theme description
            - example_commanders: List of example commander names
            - example_cards: List of example card names
            - synergy_commanders: List of synergy commander entries
            - deck_archetype: Deck archetype classification
            - popularity_bucket: Popularity tier
            - editorial_quality: Quality lifecycle flag (draft|reviewed|final)
            - quality_score: Computed quality score (0-100)
            
        Raises:
            NotFoundError: If theme not found in catalog
        """
        slug = slugify(theme_name)
        index = load_index()
        
        if slug not in index.slug_to_entry:
            raise NotFoundError(f"Theme not found: {theme_name}")
        
        entry = index.slug_to_entry[slug]
        quality_score = self.calculate_quality_score(entry)
        
        return {
            'theme': entry.theme,
            'description': entry.description or '',
            'example_commanders': entry.example_commanders or [],
            'example_cards': entry.example_cards or [],
            'synergy_commanders': entry.synergy_commanders or [],
            'deck_archetype': entry.deck_archetype,
            'popularity_bucket': entry.popularity_bucket,
            'editorial_quality': entry.editorial_quality,
            'quality_score': quality_score,
            'synergies': entry.synergies or [],
            'primary_color': entry.primary_color,
            'secondary_color': entry.secondary_color,
        }
    
    def calculate_quality_score(self, theme_entry: ThemeEntry) -> int:
        """Calculate editorial quality score for a theme entry.
        
        M2 Enhancement: Uses external heuristics for thresholds and bonuses.
        
        Score is based on presence and quality of editorial fields:
        - Description (20 points base, +10 if > 50 chars, +bonus for source type)
        - Example commanders (15 points base, +10 if 3+)
        - Example cards (15 points base, +10 if 5+)
        - Deck archetype (10 points)
        - Popularity bucket (10 points)
        - Synergy commanders (10 points)
        
        Args:
            theme_entry: ThemeEntry Pydantic model instance
            
        Returns:
            Quality score (0-100)
        """
        heuristics = self.load_heuristics()
        thresholds = heuristics.get('quality_thresholds', {})
        
        score = 0
        
        # Description (20 base + 10 length bonus + source bonus)
        if theme_entry.description:
            score += WEIGHT_HAS_DESCRIPTION
            if len(theme_entry.description) > 50:
                score += WEIGHT_DESCRIPTION_LENGTH_BONUS
            # Bonus based on description source (from heuristics)
            if theme_entry.description_source:
                source_bonuses = {
                    'manual': thresholds.get('manual_description_bonus', 10),
                    'rule': thresholds.get('rule_description_bonus', 5),
                    'generic': thresholds.get('generic_description_bonus', 0),
                }
                score += source_bonuses.get(theme_entry.description_source, 0)
        
        # Example commanders
        if theme_entry.example_commanders:
            score += WEIGHT_HAS_EXAMPLE_COMMANDERS
            if len(theme_entry.example_commanders) >= 3:
                score += WEIGHT_MULTIPLE_EXAMPLE_COMMANDERS
        
        # Example cards (with generic card penalty - M2 enhancement)
        if theme_entry.example_cards:
            score += WEIGHT_HAS_EXAMPLE_CARDS
            if len(theme_entry.example_cards) >= 5:
                score += WEIGHT_MULTIPLE_EXAMPLE_CARDS
            
            # Penalize for too many generic staples (M2)
            generic_cards = self.get_generic_staple_cards()
            if generic_cards:
                generic_count = sum(1 for card in theme_entry.example_cards if card in generic_cards)
                generic_ratio = generic_count / max(1, len(theme_entry.example_cards))
                if generic_ratio > 0.5:  # More than 50% generic
                    score -= 5  # Small penalty
        
        # Deck archetype
        if theme_entry.deck_archetype:
            score += WEIGHT_HAS_DECK_ARCHETYPE
        
        # Popularity bucket
        if theme_entry.popularity_bucket:
            score += WEIGHT_HAS_POPULARITY_BUCKET
        
        # Synergy commanders
        if theme_entry.synergy_commanders:
            score += WEIGHT_HAS_SYNERGY_COMMANDERS
        
        return min(score, 100)  # Cap at 100
    
    def get_quality_tier(self, score: int) -> str:
        """Convert quality score to tier label.
        
        M2 Enhancement: Uses external heuristics for tier thresholds.
        
        Args:
            score: Quality score (0-100)
            
        Returns:
            Quality tier: 'Excellent', 'Good', 'Fair', or 'Poor'
        """
        heuristics = self.load_heuristics()
        thresholds = heuristics.get('quality_thresholds', {})
        
        excellent_min = thresholds.get('excellent_min_score', QUALITY_EXCELLENT)
        good_min = thresholds.get('good_min_score', QUALITY_GOOD)
        fair_min = thresholds.get('fair_min_score', QUALITY_FAIR)
        
        if score >= excellent_min:
            return 'Excellent'
        elif score >= good_min:
            return 'Good'
        elif score >= fair_min:
            return 'Fair'
        else:
            return 'Poor'
    
    def validate_editorial_fields(self, theme_entry: ThemeEntry) -> List[str]:
        """Validate editorial fields and return list of issues.
        
        Checks:
        - Deck archetype is in ALLOWED_DECK_ARCHETYPES
        - Popularity bucket is valid
        - Example commanders list is not empty
        - Example cards list is not empty
        - Description exists and is not generic fallback
        
        Args:
            theme_entry: ThemeEntry Pydantic model instance
            
        Returns:
            List of validation issue messages (empty if valid)
        """
        issues = []
        
        # Deck archetype validation
        if theme_entry.deck_archetype:
            if theme_entry.deck_archetype not in ALLOWED_DECK_ARCHETYPES:
                issues.append(f"Invalid deck_archetype: {theme_entry.deck_archetype}")
        else:
            issues.append("Missing deck_archetype")
        
        # Popularity bucket validation
        if not theme_entry.popularity_bucket:
            issues.append("Missing popularity_bucket")
        
        # Example commanders
        if not theme_entry.example_commanders:
            issues.append("Missing example_commanders")
        elif len(theme_entry.example_commanders) < 2:
            issues.append("Too few example_commanders (minimum 2 recommended)")
        
        # Example cards
        if not theme_entry.example_cards:
            issues.append("Missing example_cards")
        elif len(theme_entry.example_cards) < 3:
            issues.append("Too few example_cards (minimum 3 recommended)")
        
        # Description validation
        if not theme_entry.description:
            issues.append("Missing description")
        else:
            # Check for generic auto-generated descriptions
            desc = theme_entry.description
            if any(desc.startswith(prefix) for prefix in ['Accumulates ', 'Builds around ', 'Leverages ']):
                if 'Synergies like' not in desc:
                    issues.append("Description appears to be minimal fallback template")
            
            # Check description_source
            if not theme_entry.description_source:
                issues.append("Missing description_source (should be 'rule', 'generic', or 'manual')")
            elif theme_entry.description_source == 'generic':
                issues.append("Description source is 'generic' - consider upgrading to rule-based or manual")
        
        # Popularity pinning validation
        if theme_entry.popularity_pinned and not theme_entry.popularity_bucket:
            issues.append("popularity_pinned is True but popularity_bucket is missing")
        
        return issues
    
    def suggest_example_commanders(self, theme_name: str, limit: int = 5) -> List[str]:
        """Suggest example commanders for a theme based on synergies.
        
        This is a placeholder for future ML/analytics-based suggestions.
        Currently returns existing commanders or empty list.
        
        Args:
            theme_name: Theme display name
            limit: Maximum number of suggestions
            
        Returns:
            List of commander names (up to limit)
            
        Raises:
            NotFoundError: If theme not found
        """
        slug = slugify(theme_name)
        index = load_index()
        
        if slug not in index.slug_to_entry:
            raise NotFoundError(f"Theme not found: {theme_name}")
        
        entry = index.slug_to_entry[slug]
        commanders = entry.example_commanders or []
        
        # Future enhancement: Query commander catalog for synergy matches
        # For now, return existing commanders
        return commanders[:limit]
    
    def infer_deck_archetype(self, theme_name: str, synergies: Optional[List[str]] = None) -> Optional[str]:
        """Infer deck archetype from theme name and synergies.
        
        Uses keyword matching against ARCHETYPE_KEYWORDS.
        Returns first matching archetype or None.
        
        Args:
            theme_name: Theme display name
            synergies: Optional list of synergy theme names (defaults to theme's synergies)
            
        Returns:
            Deck archetype name from ALLOWED_DECK_ARCHETYPES or None
        """
        # Get synergies if not provided
        if synergies is None:
            slug = slugify(theme_name)
            index = load_index()
            if slug in index.slug_to_entry:
                entry = index.slug_to_entry[slug]
                synergies = entry.synergies or []
            else:
                synergies = []
        
        # Build search text (lowercase)
        search_text = f"{theme_name.lower()} {' '.join(s.lower() for s in synergies)}"
        
        # Match against archetype keywords (ordered by specificity)
        for archetype, keywords in ARCHETYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in search_text:
                    return archetype
        
        return None
    
    def calculate_popularity_bucket(
        self,
        commander_count: int,
        card_count: int,
        boundaries: Optional[List[int]] = None
    ) -> PopularityBucket:
        """Calculate popularity bucket from commander/card counts.
        
        Uses total frequency (commander_count + card_count) against thresholds.
        Default boundaries: [40, 100, 220, 500]
        
        Args:
            commander_count: Number of commanders with this theme
            card_count: Number of cards with this theme
            boundaries: Custom boundaries (4 values, ascending)
            
        Returns:
            PopularityBucket literal: 'Very Common', 'Common', 'Uncommon', 'Niche', or 'Rare'
        """
        if boundaries is None:
            boundaries = DEFAULT_POPULARITY_BOUNDARIES
        
        total_freq = commander_count + card_count
        
        if total_freq <= boundaries[0]:
            return 'Rare'
        elif total_freq <= boundaries[1]:
            return 'Niche'
        elif total_freq <= boundaries[2]:
            return 'Uncommon'
        elif total_freq <= boundaries[3]:
            return 'Common'
        else:
            return 'Very Common'
    
    def generate_description(
        self,
        theme_name: str,
        synergies: List[str],
        template: str = "Builds around {theme} leveraging synergies with {synergies}."
    ) -> str:
        """Generate a basic description for a theme.
        
        This is a simple template-based fallback.
        The build_theme_catalog.py script has more sophisticated generation.
        
        Args:
            theme_name: Theme display name
            synergies: List of synergy theme names
            template: Description template with {theme} and {synergies} placeholders
            
        Returns:
            Generated description string
        """
        synergy_list = synergies[:3]  # Top 3 synergies
        
        if len(synergy_list) == 0:
            synergy_text = "its core mechanics"
        elif len(synergy_list) == 1:
            synergy_text = synergy_list[0]
        elif len(synergy_list) == 2:
            synergy_text = f"{synergy_list[0]} and {synergy_list[1]}"
        else:
            synergy_text = f"{', '.join(synergy_list[:-1])}, and {synergy_list[-1]}"
        
        return template.format(theme=theme_name, synergies=synergy_text)
    
    def infer_description_source(self, description: str) -> DescriptionSource:
        """Infer description source from content patterns.
        
        Heuristics:
        - Contains "Synergies like" → likely 'rule' (from heuristic mapping)
        - Starts with generic patterns → 'generic' (fallback template)
        - Otherwise → assume 'manual' (human-written)
        
        Args:
            description: Description text to analyze
            
        Returns:
            Inferred DescriptionSource value
        """
        if not description:
            return 'generic'
        
        # Rule-based descriptions typically have synergy mentions
        if 'Synergies like' in description or 'synergies with' in description.lower():
            return 'rule'
        
        # Generic fallback patterns
        generic_patterns = ['Accumulates ', 'Builds around ', 'Leverages ']
        if any(description.startswith(pattern) for pattern in generic_patterns):
            return 'generic'
        
        # Assume manual otherwise
        return 'manual'
    
    # M3: Card Uniqueness and Duplication Analysis
    
    def calculate_global_card_frequency(self) -> Dict[str, int]:
        """Calculate how many themes each card appears in (M3).
        
        Analyzes all themes to build a frequency map of cards.
        
        Returns:
            Dict mapping card name to theme count
        """
        index = load_index()
        card_frequency: Dict[str, int] = {}
        
        for entry in index.slug_to_entry.values():
            if entry.example_cards:
                for card in entry.example_cards:
                    card_frequency[card] = card_frequency.get(card, 0) + 1
        
        return card_frequency
    
    def calculate_uniqueness_ratio(
        self,
        example_cards: List[str],
        global_card_freq: Optional[Dict[str, int]] = None,
        uniqueness_threshold: float = 0.25
    ) -> float:
        """Calculate uniqueness ratio for a theme's example cards (M3).
        
        Uniqueness = fraction of cards appearing in <X% of themes.
        
        Args:
            example_cards: List of card names for this theme
            global_card_freq: Optional pre-calculated card frequencies (will compute if None)
            uniqueness_threshold: Threshold for "unique" (default: 0.25 = card in <25% of themes)
            
        Returns:
            Ratio from 0.0 to 1.0 (higher = more unique cards)
        """
        if not example_cards:
            return 0.0
        
        if global_card_freq is None:
            global_card_freq = self.calculate_global_card_frequency()
        
        index = load_index()
        total_themes = len(index.slug_to_entry)
        
        if total_themes == 0:
            return 0.0
        
        unique_count = sum(
            1 for card in example_cards
            if (global_card_freq.get(card, 0) / total_themes) < uniqueness_threshold
        )
        
        return unique_count / len(example_cards)
    
    def calculate_duplication_ratio(
        self,
        example_cards: List[str],
        global_card_freq: Optional[Dict[str, int]] = None,
        duplication_threshold: float = 0.40
    ) -> float:
        """Calculate duplication ratio for a theme's example cards (M3).
        
        Duplication = fraction of cards appearing in >X% of themes.
        
        Args:
            example_cards: List of card names for this theme
            global_card_freq: Optional pre-calculated card frequencies (will compute if None)
            duplication_threshold: Threshold for "duplicated" (default: 0.40 = card in >40% of themes)
            
        Returns:
            Ratio from 0.0 to 1.0 (higher = more generic/duplicated cards)
        """
        if not example_cards:
            return 0.0
        
        if global_card_freq is None:
            global_card_freq = self.calculate_global_card_frequency()
        
        index = load_index()
        total_themes = len(index.slug_to_entry)
        
        if total_themes == 0:
            return 0.0
        
        duplicated_count = sum(
            1 for card in example_cards
            if (global_card_freq.get(card, 0) / total_themes) > duplication_threshold
        )
        
        return duplicated_count / len(example_cards)
    
    def calculate_enhanced_quality_score(
        self,
        theme_entry: ThemeEntry,
        global_card_freq: Optional[Dict[str, int]] = None
    ) -> tuple[str, float]:
        """Calculate enhanced editorial quality score with uniqueness (M3).
        
        Enhanced scoring algorithm:
        - Card count: 0-30 points (8+ cards = max)
        - Uniqueness ratio: 0-40 points (card in <25% of themes)
        - Description quality: 0-20 points (manual=20, rule=10, generic=0)
        - Manual curation: 0-10 points (has curated_synergies)
        
        Tiers:
        - Excellent: 75+ points (≥0.75)
        - Good: 60-74 points (0.60-0.74)
        - Fair: 40-59 points (0.40-0.59)
        - Poor: <40 points (<0.40)
        
        Args:
            theme_entry: ThemeEntry to score
            global_card_freq: Optional pre-calculated card frequencies
            
        Returns:
            Tuple of (tier_name, numeric_score) where score is 0.0-1.0
        """
        heuristics = self.load_heuristics()
        thresholds = heuristics.get('quality_thresholds', {})
        
        total_points = 0.0
        max_points = 100.0
        
        # 1. Example card count (0-30 points)
        card_count = len(theme_entry.example_cards) if theme_entry.example_cards else 0
        excellent_card_min = thresholds.get('excellent_card_min', 8)
        card_points = min(30.0, (card_count / excellent_card_min) * 30.0)
        total_points += card_points
        
        # 2. Uniqueness ratio (0-40 points) - M3 enhancement
        if theme_entry.example_cards:
            uniqueness_ratio = self.calculate_uniqueness_ratio(
                theme_entry.example_cards,
                global_card_freq
            )
            uniqueness_points = uniqueness_ratio * 40.0
            total_points += uniqueness_points
        
        # 3. Description quality (0-20 points)
        if theme_entry.description_source:
            desc_bonus = {
                'manual': thresholds.get('manual_description_bonus', 10),
                'rule': thresholds.get('rule_description_bonus', 5),
                'generic': thresholds.get('generic_description_bonus', 0),
            }.get(theme_entry.description_source, 0)
            total_points += desc_bonus
        
        # 4. Manual curation bonus (0-10 points) - checks for curated_synergies
        if hasattr(theme_entry, 'curated_synergies') and theme_entry.curated_synergies:
            total_points += 10.0
        
        # Normalize to 0.0-1.0
        normalized_score = total_points / max_points
        
        # Determine tier using heuristics thresholds
        excellent_min = thresholds.get('excellent_min_score', 75) / 100.0
        good_min = thresholds.get('good_min_score', 60) / 100.0
        fair_min = thresholds.get('fair_min_score', 40) / 100.0
        
        if normalized_score >= excellent_min:
            tier = 'Excellent'
        elif normalized_score >= good_min:
            tier = 'Good'
        elif normalized_score >= fair_min:
            tier = 'Fair'
        else:
            tier = 'Poor'
        
        return (tier, normalized_score)
    
    def get_catalog_statistics(self, use_enhanced_scoring: bool = False) -> Dict[str, Any]:
        """Get editorial quality statistics for entire catalog.
        
        M3 Enhancement: Optionally use enhanced quality scoring with uniqueness metrics.
        
        Args:
            use_enhanced_scoring: If True, use M3 enhanced scoring with uniqueness
        
        Returns:
            Dictionary with:
            - total_themes: Total number of themes
            - complete_editorials: Themes with all editorial fields
            - missing_descriptions: Count of missing descriptions
            - missing_examples: Count of missing example commanders/cards
            - quality_distribution: Dict of quality tiers and counts
            - average_quality_score: Mean quality score
            - description_source_distribution: Breakdown by source type
            - pinned_popularity_count: Themes with pinned popularity
            - [M3] average_uniqueness_ratio: Mean card uniqueness (if enhanced)
            - [M3] average_duplication_ratio: Mean card duplication (if enhanced)
        """
        index = load_index()
        total = len(index.slug_to_entry)
        
        # Pre-calculate global card frequency for M3 enhanced scoring
        global_card_freq = self.calculate_global_card_frequency() if use_enhanced_scoring else None
        
        complete = 0
        missing_descriptions = 0
        missing_examples = 0
        quality_scores = []
        quality_tiers = {'Excellent': 0, 'Good': 0, 'Fair': 0, 'Poor': 0}
        description_sources = {'manual': 0, 'rule': 0, 'generic': 0, 'unknown': 0}
        pinned_count = 0
        uniqueness_ratios = []  # M3
        duplication_ratios = []  # M3
        
        for entry in index.slug_to_entry.values():
            # Calculate quality score (M1 or M3 version)
            if use_enhanced_scoring:
                tier, score = self.calculate_enhanced_quality_score(entry, global_card_freq)
                quality_scores.append(score * 100)  # Convert to 0-100 scale
                quality_tiers[tier] += 1
                
                # M3: Calculate uniqueness and duplication metrics
                if entry.example_cards:
                    uniqueness = self.calculate_uniqueness_ratio(entry.example_cards, global_card_freq)
                    duplication = self.calculate_duplication_ratio(entry.example_cards, global_card_freq)
                    uniqueness_ratios.append(uniqueness)
                    duplication_ratios.append(duplication)
            else:
                score = self.calculate_quality_score(entry)
                quality_scores.append(score)
                tier = self.get_quality_tier(score)
                quality_tiers[tier] += 1
            
            # Check completeness
            has_all_fields = bool(
                entry.description and
                entry.example_commanders and
                entry.example_cards and
                entry.deck_archetype and
                entry.popularity_bucket
            )
            if has_all_fields:
                complete += 1
            
            if not entry.description:
                missing_descriptions += 1
            if not entry.example_commanders or not entry.example_cards:
                missing_examples += 1
            
            # Track description sources
            if entry.description_source:
                description_sources[entry.description_source] += 1
            else:
                description_sources['unknown'] += 1
            
            # Track pinned popularity
            if entry.popularity_pinned:
                pinned_count += 1
        
        avg_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        
        result = {
            'total_themes': total,
            'complete_editorials': complete,
            'missing_descriptions': missing_descriptions,
            'missing_examples': missing_examples,
            'quality_distribution': quality_tiers,
            'average_quality_score': round(avg_score, 2),
            'completeness_percentage': round((complete / total) * 100, 2) if total > 0 else 0,
            'description_source_distribution': description_sources,
            'pinned_popularity_count': pinned_count,
        }
        
        # M3: Add uniqueness metrics if using enhanced scoring
        if use_enhanced_scoring and uniqueness_ratios:
            result['average_uniqueness_ratio'] = round(sum(uniqueness_ratios) / len(uniqueness_ratios), 3)
            result['average_duplication_ratio'] = round(sum(duplication_ratios) / len(duplication_ratios), 3)
        
        return result


# Singleton instance for module-level access
_editorial_service: Optional[ThemeEditorialService] = None


def get_editorial_service() -> ThemeEditorialService:
    """Get singleton ThemeEditorialService instance.
    
    Returns:
        ThemeEditorialService instance
    """
    global _editorial_service
    if _editorial_service is None:
        _editorial_service = ThemeEditorialService()
    return _editorial_service
