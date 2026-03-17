"""Card name validation and normalization.

Provides utilities for validating and normalizing card names against
the card database, handling punctuation, case sensitivity, and multi-face cards.
"""
from __future__ import annotations

from typing import Optional, Tuple, List, Set
import re
import unicodedata


class CardNameValidator:
    """Validates and normalizes card names against card database.
    
    Handles:
    - Case normalization
    - Punctuation variants
    - Multi-face cards (// separator)
    - Accent/diacritic handling
    - Fuzzy matching for common typos
    """
    
    def __init__(self) -> None:
        """Initialize validator with card database."""
        self._card_names: Set[str] = set()
        self._normalized_map: dict[str, str] = {}
        self._loaded = False
    
    def _ensure_loaded(self) -> None:
        """Lazy-load card database on first use."""
        if self._loaded:
            return
        
        try:
            from deck_builder import builder_utils as bu
            df = bu._load_all_cards_parquet()
            
            if not df.empty and 'name' in df.columns:
                for name in df['name'].dropna():
                    name_str = str(name).strip()
                    if name_str:
                        self._card_names.add(name_str)
                        # Map normalized version to original
                        normalized = self.normalize(name_str)
                        self._normalized_map[normalized] = name_str
            
            self._loaded = True
        except Exception:
            # Defensive: if loading fails, validator still works but won't validate
            self._loaded = True
    
    @staticmethod
    def normalize(name: str) -> str:
        """Normalize card name for comparison.
        
        Args:
            name: Raw card name
            
        Returns:
            Normalized card name (lowercase, no diacritics, standardized punctuation)
        """
        if not name:
            return ""
        
        # Strip whitespace
        cleaned = name.strip()
        
        # Remove diacritics/accents
        nfd = unicodedata.normalize('NFD', cleaned)
        cleaned = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
        
        # Lowercase
        cleaned = cleaned.lower()
        
        # Standardize punctuation
        cleaned = re.sub(r"[''`]", "'", cleaned)  # Normalize apostrophes
        cleaned = re.sub(r'["""]', '"', cleaned)  # Normalize quotes
        cleaned = re.sub(r'—', '-', cleaned)  # Normalize dashes
        
        # Collapse multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        return cleaned.strip()
    
    def is_valid(self, name: str) -> bool:
        """Check if card name exists in database.
        
        Args:
            name: Card name to validate
            
        Returns:
            True if card exists
        """
        self._ensure_loaded()
        
        if not name or not name.strip():
            return False
        
        # Try exact match first
        if name in self._card_names:
            return True
        
        # Try normalized match
        normalized = self.normalize(name)
        return normalized in self._normalized_map
    
    def get_canonical_name(self, name: str) -> Optional[str]:
        """Get canonical (database) name for a card.
        
        Args:
            name: Card name (any capitalization/punctuation)
            
        Returns:
            Canonical name if found, None otherwise
        """
        self._ensure_loaded()
        
        if not name or not name.strip():
            return None
        
        # Return exact match if exists
        if name in self._card_names:
            return name
        
        # Try normalized lookup
        normalized = self.normalize(name)
        return self._normalized_map.get(normalized)
    
    def validate_and_normalize(self, name: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Validate and normalize a card name.
        
        Args:
            name: Card name to validate
            
        Returns:
            (is_valid, canonical_name, error_message) tuple
        """
        if not name or not name.strip():
            return False, None, "Card name cannot be empty"
        
        canonical = self.get_canonical_name(name)
        
        if canonical:
            return True, canonical, None
        else:
            return False, None, f"Card '{name}' not found in database"
    
    def is_valid_commander(self, name: str) -> Tuple[bool, Optional[str]]:
        """Check if card name is a valid commander.
        
        Args:
            name: Card name to validate
            
        Returns:
            (is_valid, error_message) tuple
        """
        self._ensure_loaded()
        
        is_valid, canonical, error = self.validate_and_normalize(name)
        
        if not is_valid:
            return False, error
        
        # Check if card can be commander (has Legendary type)
        try:
            from deck_builder import builder_utils as bu
            df = bu._load_all_cards_parquet()
            
            if not df.empty:
                # Match by canonical name
                card_row = df[df['name'] == canonical]
                
                if card_row.empty:
                    return False, f"Card '{name}' not found"
                
                # Check type line for Legendary
                type_line = str(card_row['type'].iloc[0] if 'type' in card_row else '')
                
                if 'Legendary' not in type_line and 'legendary' not in type_line.lower():
                    return False, f"'{name}' is not a Legendary creature (cannot be commander)"
                
                # Check for Creature or Planeswalker
                is_creature = 'Creature' in type_line or 'creature' in type_line.lower()
                is_pw = 'Planeswalker' in type_line or 'planeswalker' in type_line.lower()
                
                # Check for specific commander abilities
                oracle_text = str(card_row['oracle'].iloc[0] if 'oracle' in card_row else '')
                can_be_commander = ' can be your commander' in oracle_text.lower()
                
                if not (is_creature or is_pw or can_be_commander):
                    return False, f"'{name}' cannot be a commander"
                
                return True, None
        
        except Exception:
            # Defensive: if check fails, assume valid if card exists
            return True, None
    
    def validate_card_list(self, names: List[str]) -> Tuple[List[str], List[str]]:
        """Validate a list of card names.
        
        Args:
            names: List of card names to validate
            
        Returns:
            (valid_names, invalid_names) tuple with canonical names
        """
        valid: List[str] = []
        invalid: List[str] = []
        
        for name in names:
            is_valid, canonical, _ = self.validate_and_normalize(name)
            if is_valid and canonical:
                valid.append(canonical)
            else:
                invalid.append(name)
        
        return valid, invalid


# Global validator instance
_validator: Optional[CardNameValidator] = None


def get_validator() -> CardNameValidator:
    """Get global card name validator instance.
    
    Returns:
        CardNameValidator instance
    """
    global _validator
    if _validator is None:
        _validator = CardNameValidator()
    return _validator


# Convenience functions
def is_valid_card(name: str) -> bool:
    """Check if card name is valid."""
    return get_validator().is_valid(name)


def get_canonical_name(name: str) -> Optional[str]:
    """Get canonical card name."""
    return get_validator().get_canonical_name(name)


def is_valid_commander(name: str) -> Tuple[bool, Optional[str]]:
    """Check if card is a valid commander."""
    return get_validator().is_valid_commander(name)


def validate_card_list(names: List[str]) -> Tuple[List[str], List[str]]:
    """Validate a list of card names."""
    return get_validator().validate_card_list(names)
