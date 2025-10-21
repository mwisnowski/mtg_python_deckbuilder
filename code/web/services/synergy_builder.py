"""
Synergy Builder - Analyzes multiple deck builds and creates optimized "best-of" deck.

Takes multiple builds of the same configuration and identifies cards that appear
frequently across builds, scoring them for synergy based on:
- Frequency of appearance (higher = more consistent with strategy)
- EDHREC rank (lower rank = more popular/powerful)
- Theme tag matches (more matching tags = better fit)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from collections import Counter
from code.logging_util import get_logger
from code.deck_builder import builder_utils as bu
import pandas as pd
import os

logger = get_logger(__name__)


@dataclass
class ScoredCard:
    """A card with its synergy score and metadata."""
    name: str
    frequency: float  # 0.0-1.0, percentage of builds containing this card
    appearance_count: int  # Number of builds this card appears in
    synergy_score: float  # 0-100+ calculated score
    category: str  # Card type category (Creature, Land, etc.)
    role: str = ""  # Card role from tagging
    tags: List[str] = field(default_factory=list)  # Theme tags
    edhrec_rank: Optional[int] = None  # EDHREC rank if available
    count: int = 1  # Number of copies (usually 1 for Commander)
    type_line: str = ""  # Full type line (e.g., "Creature — Rabbit Scout")


@dataclass
class CardPool:
    """Aggregated pool of cards from multiple builds."""
    cards: Dict[str, ScoredCard]  # card_name -> ScoredCard
    total_builds: int
    config: Dict[str, Any]  # Original build configuration
    themes: List[str]  # Theme tags from config
    
    def get_by_category(self, category: str) -> List[ScoredCard]:
        """Get all cards in a specific category."""
        return [card for card in self.cards.values() if card.category == category]
    
    def get_top_cards(self, limit: int = 100) -> List[ScoredCard]:
        """Get top N cards by synergy score."""
        return sorted(self.cards.values(), key=lambda c: c.synergy_score, reverse=True)[:limit]
    
    def get_high_frequency_cards(self, min_frequency: float = 0.8) -> List[ScoredCard]:
        """Get cards appearing in at least min_frequency of builds."""
        return [card for card in self.cards.values() if card.frequency >= min_frequency]


class SynergyAnalyzer:
    """Analyzes multiple builds and scores cards for synergy."""
    
    # Scoring weights
    FREQUENCY_WEIGHT = 0.5
    EDHREC_WEIGHT = 0.25
    THEME_WEIGHT = 0.25
    HIGH_FREQUENCY_BONUS = 1.1  # 10% bonus for cards in 80%+ builds
    
    def __init__(self):
        """Initialize synergy analyzer."""
        self._type_line_cache: Dict[str, str] = {}
    
    def _load_type_lines(self) -> Dict[str, str]:
        """
        Load card type lines from parquet for all cards.
        
        Returns:
            Dict mapping card name (lowercase) to type_line
        """
        if self._type_line_cache:
            return self._type_line_cache
        
        try:
            parquet_path = os.path.join("card_files", "processed", "all_cards.parquet")
            if not os.path.exists(parquet_path):
                logger.warning(f"[Synergy] Card parquet not found at {parquet_path}")
                return {}
            
            df = pd.read_parquet(parquet_path)
            
            # Try 'type' first, then 'type_line'
            type_col = None
            if 'type' in df.columns:
                type_col = 'type'
            elif 'type_line' in df.columns:
                type_col = 'type_line'
            
            if not type_col or 'name' not in df.columns:
                logger.warning(f"[Synergy] Card parquet missing required columns. Available: {list(df.columns)}")
                return {}
            
            # Build mapping: lowercase name -> type_line
            for _, row in df.iterrows():
                name = str(row.get('name', '')).strip()
                type_line = str(row.get(type_col, '')).strip()
                if name and type_line:
                    self._type_line_cache[name.lower()] = type_line
            
            logger.info(f"[Synergy] Loaded type lines for {len(self._type_line_cache)} cards from parquet")
            return self._type_line_cache
            
        except Exception as e:
            logger.warning(f"[Synergy] Error loading type lines from parquet: {e}")
            return {}
    
    def analyze_builds(self, builds: List[Dict[str, Any]], config: Dict[str, Any]) -> CardPool:
        """
        Aggregate all cards from builds and calculate appearance frequencies.
        
        Args:
            builds: List of build results from BuildCache
            config: Original deck configuration
            
        Returns:
            CardPool with all unique cards and their frequencies
        """
        logger.info(f"[Synergy] Analyzing {len(builds)} builds for synergy")
        
        if not builds:
            raise ValueError("Cannot analyze synergy with no builds")
        
        total_builds = len(builds)
        themes = config.get("tags", [])
        
        # Load type lines from card CSV
        type_line_map = self._load_type_lines()
        
        # Count card appearances and cumulative counts across all builds
        card_appearances: Counter = Counter()  # card_name -> number of builds containing it
        card_total_counts: Counter = Counter()  # card_name -> sum of counts across all builds
        card_metadata: Dict[str, Dict[str, Any]] = {}
        
        for build in builds:
            result = build.get("result", {})
            summary = result.get("summary", {})
            
            if not isinstance(summary, dict):
                logger.warning("[Synergy] Build missing summary, skipping")
                continue
            
            type_breakdown = summary.get("type_breakdown", {})
            if not isinstance(type_breakdown, dict):
                continue
            
            type_cards = type_breakdown.get("cards", {})
            if not isinstance(type_cards, dict):
                continue
            
            # Collect unique cards from this build
            unique_cards_in_build = set()
            
            for category, card_list in type_cards.items():
                if not isinstance(card_list, list):
                    continue
                
                for card in card_list:
                    if not isinstance(card, dict):
                        continue
                    
                    card_name = card.get("name")
                    if not card_name:
                        continue
                    
                    card_count = card.get("count", 1)
                    unique_cards_in_build.add(card_name)
                    
                    # Track cumulative count across all builds (for multi-copy cards like basics)
                    card_total_counts[card_name] += card_count
                    
                    # Store metadata (first occurrence)
                    if card_name not in card_metadata:
                        # Get type_line from parquet, fallback to card data (which won't have it from summary)
                        type_line = type_line_map.get(card_name.lower(), "")
                        if not type_line:
                            type_line = card.get("type", card.get("type_line", ""))
                        
                        # Debug: Log first few cards
                        if len(card_metadata) < 3:
                            logger.info(f"[Synergy Debug] Card: {card_name}, Type line: {type_line}, From map: {card_name.lower() in type_line_map}")
                        
                        card_metadata[card_name] = {
                            "category": category,
                            "role": card.get("role", ""),
                            "tags": card.get("tags", []),
                            "type_line": type_line
                        }
            
            # Increment appearance count for each unique card in this build
            for card_name in unique_cards_in_build:
                card_appearances[card_name] += 1
        
        # Create ScoredCard objects with frequencies and average counts
        scored_cards: Dict[str, ScoredCard] = {}
        
        for card_name, appearance_count in card_appearances.items():
            frequency = appearance_count / total_builds
            metadata = card_metadata.get(card_name, {})
            
            scored_card = ScoredCard(
                name=card_name,
                frequency=frequency,
                appearance_count=appearance_count,
                synergy_score=0.0,  # Will be calculated next
                category=metadata.get("category", "Unknown"),
                role=metadata.get("role", ""),
                tags=metadata.get("tags", []),
                count=1,  # Default to 1 copy per card in synergy deck (basics override this later)
                type_line=metadata.get("type_line", "")
            )
            
            # Debug: Log first few scored cards
            if len(scored_cards) < 3:
                logger.info(f"[Synergy Debug] ScoredCard: {scored_card.name}, type_line='{scored_card.type_line}', count={scored_card.count}, in_map={card_name.lower() in type_line_map}")
            
            # Calculate synergy score
            scored_card.synergy_score = self.score_card(scored_card, themes)
            
            scored_cards[card_name] = scored_card
        
        logger.info(f"[Synergy] Analyzed {len(scored_cards)} unique cards from {total_builds} builds")
        
        return CardPool(
            cards=scored_cards,
            total_builds=total_builds,
            config=config,
            themes=themes
        )
    
    def score_card(self, card: ScoredCard, themes: List[str]) -> float:
        """
        Calculate synergy score for a card.
        
        Score = frequency_weight * frequency * 100 +
                edhrec_weight * (1 - rank/max_rank) * 100 +
                theme_weight * (matching_tags / total_tags) * 100
        
        Args:
            card: ScoredCard to score
            themes: Theme tags from config
            
        Returns:
            Synergy score (0-100+)
        """
        # Frequency component (0-100)
        frequency_score = card.frequency * 100
        
        # EDHREC component (placeholder - would need EDHREC data)
        # For now, assume no EDHREC data available
        edhrec_score = 50.0  # Neutral score
        
        # Theme component (0-100)
        theme_score = 0.0
        if themes and card.tags:
            theme_set = set(themes)
            card_tag_set = set(card.tags)
            matching_tags = len(theme_set & card_tag_set)
            theme_score = (matching_tags / len(themes)) * 100 if themes else 0.0
        
        # Calculate weighted score
        score = (
            self.FREQUENCY_WEIGHT * frequency_score +
            self.EDHREC_WEIGHT * edhrec_score +
            self.THEME_WEIGHT * theme_score
        )
        
        # Bonus for high-frequency cards (appear in 80%+ builds)
        if card.frequency >= 0.8:
            score *= self.HIGH_FREQUENCY_BONUS
        
        return round(score, 2)


class SynergyDeckBuilder:
    """Builds an optimized deck from a synergy-scored card pool."""
    
    def __init__(self, analyzer: Optional[SynergyAnalyzer] = None):
        """
        Initialize synergy deck builder.
        
        Args:
            analyzer: SynergyAnalyzer instance (creates new if None)
        """
        self.analyzer = analyzer or SynergyAnalyzer()
    
    def _allocate_basic_lands(
        self,
        selected_cards: List[ScoredCard],
        by_category: Dict[str, List[ScoredCard]],
        pool: CardPool,
        ideals: Optional[Dict[str, int]]
    ) -> List[ScoredCard]:
        """
        Allocate basic lands based on color identity and remaining land slots.
        
        Separates basic lands from nonbasics, then allocates basics based on:
        1. Total lands target from ideals
        2. Color identity from config
        3. Current nonbasic land count
        
        Args:
            selected_cards: Currently selected cards (may include basics from pool)
            by_category: Cards grouped by category
            pool: Card pool with configuration
            ideals: Ideal card counts
            
        Returns:
            Updated list of selected cards with properly allocated basics
        """
        if not ideals:
            return selected_cards  # No ideals, keep as-is
        
        # Get basic land names
        basic_names = bu.basic_land_names()
        
        # Separate basics from nonbasics
        nonbasic_cards = [c for c in selected_cards if c.name not in basic_names]
        
        # Calculate how many basics we need
        # Note: For nonbasics, count=1 per card (singleton rule), so count == number of unique cards
        target_lands = ideals.get("lands", 35)
        nonbasic_lands = [c for c in nonbasic_cards if c.category == "Land"]
        current_nonbasic_count = len(nonbasic_lands)
        
        # If we have too many nonbasics, trim them
        if current_nonbasic_count > target_lands:
            logger.info(f"[Synergy] Too many nonbasics ({current_nonbasic_count}), trimming to {target_lands}")
            # Keep the highest scoring nonbasics
            sorted_nonbasic_lands = sorted(nonbasic_lands, key=lambda c: c.synergy_score, reverse=True)
            trimmed_nonbasic_lands = sorted_nonbasic_lands[:target_lands]
            # Update nonbasic_cards to exclude trimmed lands
            other_nonbasics = [c for c in nonbasic_cards if c.category != "Land"]
            nonbasic_cards = other_nonbasics + trimmed_nonbasic_lands
            return nonbasic_cards  # No room for basics
        
        needed_basics = max(0, target_lands - current_nonbasic_count)
        
        if needed_basics == 0:
            logger.info("[Synergy] No basic lands needed (nonbasics exactly fill target)")
            return nonbasic_cards
        
        logger.info(f"[Synergy] Need {needed_basics} basics to fill {target_lands} land target (have {current_nonbasic_count} nonbasics)")
        
        # Get color identity from config
        color_identity = pool.config.get("colors", [])
        if not color_identity:
            logger.warning(f"[Synergy] No color identity in config (keys: {list(pool.config.keys())}), skipping basic land allocation")
            return nonbasic_cards
        
        # Map colors to basic land names
        from code.deck_builder import builder_constants as bc
        basic_map = getattr(bc, 'BASIC_LAND_MAPPING', {
            'W': 'Plains', 'U': 'Island', 'B': 'Swamp', 'R': 'Mountain', 'G': 'Forest'
        })
        
        # Allocate basics evenly across colors
        allocation: Dict[str, int] = {}
        colors = [c.upper() for c in color_identity if c.upper() in basic_map]
        
        if not colors:
            logger.warning(f"[Synergy] No valid colors found in identity: {color_identity}")
            return nonbasic_cards
        
        # Distribute basics evenly, with remainder going to first colors
        n = len(colors)
        base = needed_basics // n
        rem = needed_basics % n
        
        for idx, color in enumerate(sorted(colors)):  # sorted for deterministic allocation
            count = base + (1 if idx < rem else 0)
            land_name = basic_map.get(color)
            if land_name:
                allocation[land_name] = count
        
        # Create ScoredCard objects for basics
        basic_cards = []
        for land_name, count in allocation.items():
            # Try to get type_line from cache first (most reliable)
            type_line = self.analyzer._type_line_cache.get(land_name.lower(), "")
            if not type_line:
                # Fallback: construct from land name
                type_line = f"Basic Land — {land_name[:-1] if land_name.endswith('s') else land_name}"
            
            # Try to get existing scored data from pool, else create minimal entry
            if land_name in pool.cards:
                existing = pool.cards[land_name]
                basic_card = ScoredCard(
                    name=land_name,
                    frequency=existing.frequency,
                    appearance_count=existing.appearance_count,
                    synergy_score=existing.synergy_score,
                    category="Land",
                    role="basic",
                    tags=[],
                    count=count,
                    type_line=type_line  # Use looked-up type_line
                )
            else:
                # Not in pool (common for basics), create minimal entry
                basic_card = ScoredCard(
                    name=land_name,
                    frequency=1.0,  # Assume high frequency for basics
                    appearance_count=pool.total_builds,
                    synergy_score=50.0,  # Neutral score
                    category="Land",
                    role="basic",
                    tags=[],
                    count=count,
                    type_line=type_line
                )
            basic_cards.append(basic_card)
        
        # Update by_category to replace old basics with new allocation
        land_category = by_category.get("Land", [])
        land_category = [c for c in land_category if c.name not in basic_names]  # Remove old basics
        land_category.extend(basic_cards)  # Add new basics
        by_category["Land"] = land_category
        
        # Combine and return
        result = nonbasic_cards + basic_cards
        logger.info(f"[Synergy] Allocated {needed_basics} basic lands across {len(colors)} colors: {allocation}")
        return result
    
    def build_deck(
        self,
        pool: CardPool,
        ideals: Optional[Dict[str, int]] = None,
        target_size: int = 99  # Commander + 99 cards = 100
    ) -> Dict[str, Any]:
        """
        Build an optimized deck from the card pool, respecting ideal counts.
        
        Selects highest-scoring cards by category to meet ideal distributions.
        
        Args:
            pool: CardPool with scored cards
            ideals: Target card counts by category (e.g., {"Creature": 25, "Land": 35})
            target_size: Total number of cards to include (default 99, excluding commander)
            
        Returns:
            Dict with deck list and metadata
        """
        logger.info(f"[Synergy] Building deck from pool of {len(pool.cards)} cards")
        
        # Map category names to ideal keys (case-insensitive matching)
        category_mapping = {
            "Creature": "creatures",
            "Land": "lands",
            "Artifact": "artifacts",
            "Enchantment": "enchantments",
            "Instant": "instants",
            "Sorcery": "sorceries",
            "Planeswalker": "planeswalkers",
            "Battle": "battles"
        }
        
        selected_cards: List[ScoredCard] = []
        by_category: Dict[str, List[ScoredCard]] = {}
        
        if ideals:
            # Build by category to meet ideals (±2 tolerance)
            logger.info(f"[Synergy] Using ideals: {ideals}")
            
            # Get basic land names for filtering
            basic_names = bu.basic_land_names()
            
            for category in ["Land", "Creature", "Artifact", "Enchantment", "Instant", "Sorcery", "Planeswalker", "Battle"]:
                ideal_key = category_mapping.get(category, category.lower())
                target_count = ideals.get(ideal_key, 0)
                
                if target_count == 0:
                    continue
                
                # Get all cards in this category sorted by score
                all_category_cards = pool.get_by_category(category)
                
                # For lands: only select nonbasics (basics allocated separately based on color identity)
                if category == "Land":
                    # Filter out basics
                    nonbasic_lands = [c for c in all_category_cards if c.name not in basic_names]
                    category_cards = sorted(
                        nonbasic_lands,
                        key=lambda c: c.synergy_score,
                        reverse=True
                    )
                    # Reserve space for basics - typically want 15-20 basics minimum
                    # So select fewer nonbasics to leave room
                    min_basics_estimate = 15  # Reasonable minimum for most decks
                    max_nonbasics = max(0, target_count - min_basics_estimate)
                    selected = category_cards[:max_nonbasics]
                    logger.info(f"[Synergy]   Land: selected {len(selected)} nonbasics (max {max_nonbasics}, leaving room for basics)")
                else:
                    category_cards = sorted(
                        all_category_cards,
                        key=lambda c: c.synergy_score,
                        reverse=True
                    )
                    # Select top cards up to target count
                    selected = category_cards[:target_count]
                
                selected_cards.extend(selected)
                by_category[category] = selected
                
                logger.info(
                    f"[Synergy]   {category}: selected {len(selected)}/{target_count} "
                    f"(pool had {len(category_cards)} available)"
                )
            
            # Calculate how many basics we'll need before filling remaining slots
            target_lands = ideals.get("lands", 35)
            current_land_count = len(by_category.get("Land", []))
            estimated_basics = max(0, target_lands - current_land_count)
            
            # Fill remaining slots with highest-scoring cards from any category (except Land)
            # But reserve space for basic lands that will be added later
            remaining_slots = target_size - len(selected_cards) - estimated_basics
            if remaining_slots > 0:
                selected_names = {c.name for c in selected_cards}
                # Exclude Land category from filler to avoid over-selecting lands
                remaining_pool = [
                    c for c in pool.get_top_cards(limit=len(pool.cards)) 
                    if c.name not in selected_names and c.category != "Land"
                ]
                filler_cards = remaining_pool[:remaining_slots]
                selected_cards.extend(filler_cards)
                
                # Add filler cards to by_category
                for card in filler_cards:
                    by_category.setdefault(card.category, []).append(card)
                
                logger.info(f"[Synergy]   Filled {len(filler_cards)} remaining slots (reserved {estimated_basics} for basics)")
        else:
            # No ideals provided - fall back to top-scoring cards
            logger.info("[Synergy] No ideals provided, selecting top-scoring cards")
            sorted_cards = pool.get_top_cards(limit=len(pool.cards))
            selected_cards = sorted_cards[:target_size]
            
            # Group by category for summary
            for card in selected_cards:
                by_category.setdefault(card.category, []).append(card)
        
        # Add basic lands after nonbasics are selected
        selected_cards = self._allocate_basic_lands(selected_cards, by_category, pool, ideals)
        
        # Calculate stats (accounting for multi-copy cards)
        unique_cards = len(selected_cards)
        total_cards = sum(c.count for c in selected_cards)  # Actual card count including duplicates
        
        # Debug: Check for cards with unexpected counts
        cards_with_count = [(c.name, c.count) for c in selected_cards if c.count != 1]
        if cards_with_count:
            logger.info(f"[Synergy Debug] Cards with count != 1: {cards_with_count[:10]}")
        
        avg_frequency = sum(c.frequency for c in selected_cards) / unique_cards if unique_cards else 0
        avg_score = sum(c.synergy_score for c in selected_cards) / unique_cards if unique_cards else 0
        high_freq_count = len([c for c in selected_cards if c.frequency >= 0.8])
        
        logger.info(
            f"[Synergy] Built deck: {total_cards} cards ({unique_cards} unique), "
            f"avg frequency={avg_frequency:.2f}, avg score={avg_score:.2f}, "
            f"high-frequency cards={high_freq_count}"
        )
        
        return {
            "cards": selected_cards,
            "by_category": by_category,
            "total_cards": total_cards,  # Actual count including duplicates
            "unique_cards": unique_cards,  # Unique card types
            "avg_frequency": round(avg_frequency, 3),
            "avg_score": round(avg_score, 2),
            "high_frequency_count": high_freq_count,
            "commander": pool.config.get("commander"),
            "themes": pool.themes
        }


# Global analyzer instance
_analyzer = SynergyAnalyzer()
_builder = SynergyDeckBuilder(_analyzer)


def analyze_and_build_synergy_deck(
    builds: List[Dict[str, Any]],
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Convenience function to analyze builds and create synergy deck in one call.
    
    Args:
        builds: List of build results
        config: Original deck configuration (includes ideals)
        
    Returns:
        Synergy deck result dict
    """
    pool = _analyzer.analyze_builds(builds, config)
    ideals = config.get("ideals", {})
    deck = _builder.build_deck(pool, ideals=ideals)
    return deck
