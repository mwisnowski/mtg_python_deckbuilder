"""Price checking functionality for MTG Python Deckbuilder.
 
This module provides functionality to check card prices using the Scryfall API
through the scrython library. It includes caching and error handling for reliable
price lookups.
"""

from __future__ import annotations

# Standard library imports
import time
from functools import lru_cache
from typing import Dict, List, Optional, Tuple, Union

# Third-party imports
import scrython
from scrython.cards import Named as ScryfallCard

# Local imports
from exceptions import (
    PriceAPIError,
    PriceLimitError,
    PriceTimeoutError,
    PriceValidationError
)
from deck_builder.builder_constants import (
    BATCH_PRICE_CHECK_SIZE,
    DEFAULT_MAX_CARD_PRICE,
    DEFAULT_MAX_DECK_PRICE,
    DEFAULT_PRICE_DELAY,
    MAX_PRICE_CHECK_ATTEMPTS,
    PRICE_CACHE_SIZE,
    PRICE_CHECK_TIMEOUT,
    PRICE_TOLERANCE_MULTIPLIER
)
from type_definitions import PriceCache
import logging_util

# Create logger for this module
logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
logger.addHandler(logging_util.file_handler)
logger.addHandler(logging_util.stream_handler)

class PriceChecker:
    """Class for handling MTG card price checking and validation.
    
    This class provides functionality for checking card prices via the Scryfall API,
    validating prices against thresholds, and managing price caching.
    
    Attributes:
        price_cache (Dict[str, float]): Cache of card prices
        max_card_price (float): Maximum allowed price per card
        max_deck_price (float): Maximum allowed total deck price
        current_deck_price (float): Current total price of the deck
    """
    
    def __init__(
        self,
        max_card_price: float = DEFAULT_MAX_CARD_PRICE,
        max_deck_price: float = DEFAULT_MAX_DECK_PRICE
    ) -> None:
        """Initialize the PriceChecker.
        
        Args:
            max_card_price: Maximum allowed price per card
            max_deck_price: Maximum allowed total deck price
        """
        self.price_cache: PriceCache = {}
        self.max_card_price: float = max_card_price
        self.max_deck_price: float = max_deck_price
        self.current_deck_price: float = 0.0
    
    @lru_cache(maxsize=PRICE_CACHE_SIZE)
    def get_card_price(self, card_name: str, attempts: int = 0) -> float:
        """Get the price of a card with caching and retry logic.
        
        Args:
            card_name: Name of the card to check
            attempts: Current number of retry attempts
            
        Returns:
            Float price of the card in USD
            
        Raises:
            PriceAPIError: If price lookup fails after max attempts
            PriceTimeoutError: If request times out
            PriceValidationError: If received price data is invalid
        """
        # Check cache first
        if card_name in self.price_cache:
            return self.price_cache[card_name]
            
        try:
            # Add delay between API calls
            time.sleep(DEFAULT_PRICE_DELAY)
            
            # Make API request with type hints
            card: ScryfallCard = scrython.cards.Named(fuzzy=card_name, timeout=PRICE_CHECK_TIMEOUT)
            price: Optional[str] = card.prices('usd')
            
            # Handle None or empty string cases
            if price is None or price == "":
                return 0.0
            
            # Validate and cache price
            if isinstance(price, (int, float, str)):
                try:
                    # Convert string or numeric price to float
                    price_float = float(price)
                    self.price_cache[card_name] = price_float
                    return price_float
                except ValueError:
                    raise PriceValidationError(card_name, str(price))
            return 0.0
            
        except scrython.foundation.ScryfallError as e:
            if attempts < MAX_PRICE_CHECK_ATTEMPTS:
                logger.warning(f"Retrying price check for {card_name} (attempt {attempts + 1})")
                return self.get_card_price(card_name, attempts + 1)
            raise PriceAPIError(card_name, {"error": str(e)})
            
        except TimeoutError:
            raise PriceTimeoutError(card_name, PRICE_CHECK_TIMEOUT)
            
        except Exception as e:
            if attempts < MAX_PRICE_CHECK_ATTEMPTS:
                logger.warning(f"Unexpected error checking price for {card_name}, retrying")
                return self.get_card_price(card_name, attempts + 1)
            raise PriceAPIError(card_name, {"error": str(e)})
    
    def validate_card_price(self, card_name: str, price: float) -> bool | None:
        """Validate if a card's price is within allowed limits.
        
        Args:
            card_name: Name of the card to validate
            price: Price to validate
            
        Returns:
            True if price is valid, False otherwise
            
        Raises:
            PriceLimitError: If price exceeds maximum allowed
        """
        if price > self.max_card_price * PRICE_TOLERANCE_MULTIPLIER:
            raise PriceLimitError(card_name, price, self.max_card_price)
        return True
    
    def validate_deck_price(self) -> bool | None:
        """Validate if the current deck price is within allowed limits.
        
        Returns:
            True if deck price is valid, False otherwise
            
        Raises:
            PriceLimitError: If deck price exceeds maximum allowed
        """
        if self.current_deck_price > self.max_deck_price * PRICE_TOLERANCE_MULTIPLIER:
            raise PriceLimitError("deck", self.current_deck_price, self.max_deck_price)
        return True
    
    def batch_check_prices(self, card_names: List[str]) -> Dict[str, float]:
        """Check prices for multiple cards efficiently.
        
        Args:
            card_names: List of card names to check prices for
            
        Returns:
            Dictionary mapping card names to their prices
            
        Raises:
            PriceAPIError: If batch price lookup fails
        """
        results: Dict[str, float] = {}
        errors: List[Tuple[str, Exception]] = []
        
        # Process in batches
        for i in range(0, len(card_names), BATCH_PRICE_CHECK_SIZE):
            batch = card_names[i:i + BATCH_PRICE_CHECK_SIZE]
            
            for card_name in batch:
                try:
                    price = self.get_card_price(card_name)
                    results[card_name] = price
                except Exception as e:
                    errors.append((card_name, e))
                    logger.error(f"Error checking price for {card_name}: {e}")
        
        if errors:
            logger.warning(f"Failed to get prices for {len(errors)} cards")
            
        return results
    
    def update_deck_price(self, price: float) -> None:
        """Update the current deck price.
        
        Args:
            price: Price to add to current deck total
        """
        self.current_deck_price += price
        logger.debug(f"Updated deck price to ${self.current_deck_price:.2f}")
    
    def clear_cache(self) -> None:
        """Clear the price cache."""
        self.price_cache.clear()
        self.get_card_price.cache_clear()
        logger.info("Price cache cleared")