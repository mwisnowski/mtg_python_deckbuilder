"""Card-centric tagging approach for performance comparison.

This module implements a single-pass tagging strategy where we iterate
through each card once and apply all applicable tags, rather than
iterating through all cards for each tag type.

Performance hypothesis: Single-pass should be faster due to:
- Better cache locality (sequential card access)
- Fewer DataFrame iterations
- Less memory thrashing

Trade-offs:
- All tagging logic in one place (harder to maintain)
- More complex per-card logic
- Less modular than tag-centric approach

M3: Created for Parquet migration performance testing.
"""

from __future__ import annotations

import re
from typing import List, Set

import pandas as pd

from logging_util import get_logger

logger = get_logger(__name__)


class CardCentricTagger:
    """Single-pass card tagger that applies all tags to each card sequentially."""
    
    def __init__(self):
        """Initialize tagger with compiled regex patterns for performance."""
        # Pre-compile common regex patterns
        self.ramp_pattern = re.compile(
            r'add .*mana|search.*land|ramp|cultivate|kodama|explosive vegetation',
            re.IGNORECASE
        )
        self.draw_pattern = re.compile(
            r'draw.*card|card draw|divination|ancestral|opt|cantrip',
            re.IGNORECASE
        )
        self.removal_pattern = re.compile(
            r'destroy|exile|counter|return.*hand|bounce|murder|wrath|swords',
            re.IGNORECASE
        )
        self.token_pattern = re.compile(
            r'create.*token|token.*creature|populate|embalm',
            re.IGNORECASE
        )
        # Add more patterns as needed
        
    def tag_single_card(self, row: pd.Series) -> List[str]:
        """Apply all applicable tags to a single card.
        
        Args:
            row: pandas Series representing a card
            
        Returns:
            List of tags that apply to this card
        """
        tags: Set[str] = set()
        
        # Extract common fields
        text = str(row.get('text', '')).lower()
        type_line = str(row.get('type', '')).lower()
        keywords = row.get('keywords', [])
        if isinstance(keywords, str):
            keywords = [keywords]
        mana_value = row.get('manaValue', 0)
        
        # === FOUNDATIONAL TAGS ===
        
        # Card types
        if 'creature' in type_line:
            tags.add('Creature')
        if 'instant' in type_line:
            tags.add('Instant')
        if 'sorcery' in type_line:
            tags.add('Sorcery')
        if 'artifact' in type_line:
            tags.add('Artifact')
        if 'enchantment' in type_line:
            tags.add('Enchantment')
        if 'planeswalker' in type_line:
            tags.add('Planeswalker')
        if 'land' in type_line:
            tags.add('Land')
        
        # === MECHANICAL TAGS ===
        
        # Ramp
        if self.ramp_pattern.search(text):
            tags.add('Ramp')
            
        # Card draw
        if self.draw_pattern.search(text):
            tags.add('Card Draw')
            
        # Removal
        if self.removal_pattern.search(text):
            tags.add('Removal')
            tags.add('Interaction')
            
        # Tokens
        if self.token_pattern.search(text):
            tags.add('Tokens')
        
        # Keywords
        if keywords:
            for kw in keywords:
                kw_lower = str(kw).lower()
                if 'flash' in kw_lower:
                    tags.add('Flash')
                if 'haste' in kw_lower:
                    tags.add('Haste')
                if 'flying' in kw_lower:
                    tags.add('Flying')
                # Add more keyword mappings
        
        # === STRATEGIC TAGS ===
        
        # Voltron (equipment, auras on creatures)
        if 'equipment' in type_line or 'equip' in text:
            tags.add('Voltron')
            tags.add('Equipment')
        
        if 'aura' in type_line and 'enchant creature' in text:
            tags.add('Voltron')
            tags.add('Auras')
        
        # Spellslinger (cares about instants/sorceries)
        if 'instant' in text and 'sorcery' in text:
            tags.add('Spellslinger')
        
        # Graveyard matters
        if any(word in text for word in ['graveyard', 'flashback', 'unearth', 'delve', 'escape']):
            tags.add('Graveyard')
        
        # === ARCHETYPE TAGS ===
        
        # Combo pieces (based on specific card text patterns)
        if 'infinite' in text or 'any number' in text:
            tags.add('Combo')
        
        # === MV-BASED TAGS ===
        
        if mana_value <= 2:
            tags.add('Low MV')
        elif mana_value >= 6:
            tags.add('High MV')
        
        return sorted(list(tags))
    
    def tag_all_cards(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply tags to all cards in a single pass.
        
        Args:
            df: DataFrame containing card data
            
        Returns:
            DataFrame with themeTags column populated
        """
        logger.info(f"Starting card-centric tagging for {len(df)} cards")
        
        # Initialize themeTags column if not exists
        if 'themeTags' not in df.columns:
            df['themeTags'] = None
        
        # Single pass through all cards
        tag_counts = {}
        for idx in df.index:
            row = df.loc[idx]
            tags = self.tag_single_card(row)
            df.at[idx, 'themeTags'] = tags
            
            # Track tag frequency
            for tag in tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        logger.info(f"Tagged {len(df)} cards with {len(tag_counts)} unique tags")
        logger.info(f"Top 10 tags: {sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]}")
        
        return df


def tag_all_cards_single_pass(df: pd.DataFrame) -> pd.DataFrame:
    """Convenience function for single-pass tagging.
    
    Args:
        df: DataFrame containing card data
        
    Returns:
        DataFrame with themeTags populated
    """
    tagger = CardCentricTagger()
    return tagger.tag_all_cards(df)
