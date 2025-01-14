"""Price checking functionality for MTG Python Deckbuilder.
 
This module provides functionality to check card prices using the Scryfall API
through the scrython library. It includes caching and error handling for reliable
price lookups.
"""
 
import time
from functools import lru_cache
from typing import Optional
 
import scrython
from scrython.cards import Named
 
from exceptions import PriceCheckError
from settings import PRICE_CHECK_CONFIG
 
@lru_cache(maxsize=PRICE_CHECK_CONFIG['cache_size'])
def check_price(card_name: str) -> float:
    """Retrieve the current price of a Magic: The Gathering card.
 
    Args:
        card_name: The name of the card to check.
 
    Returns:
        float: The current price of the card in USD.
 
    Raises:
        PriceCheckError: If there are any issues retrieving the price.
    """
    retries = 0
    last_error = None
 
    while retries < PRICE_CHECK_CONFIG['max_retries']:
        try:
            card = Named(fuzzy=card_name)
            price = card.prices('usd')
            print(price)
            
            if price is None:
                raise PriceCheckError(
                    "No price data available",
                    card_name,
                    "Card may be too new or not available in USD"
                )
            
            return float(price)
 
        except (scrython.ScryfallError, ValueError) as e:
            last_error = str(e)
            retries += 1
            if retries < PRICE_CHECK_CONFIG['max_retries']:
                time.sleep(0.1)  # Brief delay before retry
            continue
 
    raise PriceCheckError(
        "Failed to retrieve price after multiple attempts",
        card_name,
        f"Last error: {last_error}"
    )