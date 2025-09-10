#!/usr/bin/env python3
"""
Check for banned cards in our popular/iconic card lists.
"""

from code.file_setup.setup_constants import BANNED_CARDS
from code.deck_builder.builder_constants import POPULAR_CARDS, ICONIC_CARDS

def check_banned_overlap():
    """Check which cards in our lists are banned in Commander."""
    
    # Convert banned cards to set for faster lookup
    banned_set = set(BANNED_CARDS)
    
    print("Checking for banned cards in our card priority lists...")
    print("=" * 60)
    
    # Check POPULAR_CARDS
    popular_banned = POPULAR_CARDS & banned_set
    print(f"POPULAR_CARDS ({len(POPULAR_CARDS)} total):")
    if popular_banned:
        print("❌ Found banned cards:")
        for card in sorted(popular_banned):
            print(f"  - {card}")
    else:
        print("✅ No banned cards found")
    print()
    
    # Check ICONIC_CARDS
    iconic_banned = ICONIC_CARDS & banned_set
    print(f"ICONIC_CARDS ({len(ICONIC_CARDS)} total):")
    if iconic_banned:
        print("❌ Found banned cards:")
        for card in sorted(iconic_banned):
            print(f"  - {card}")
    else:
        print("✅ No banned cards found")
    print()
    
    # Summary
    all_banned = popular_banned | iconic_banned
    if all_banned:
        print(f"SUMMARY: Found {len(all_banned)} banned cards that need to be removed:")
        for card in sorted(all_banned):
            print(f"  - {card}")
        return list(all_banned)
    else:
        print("✅ No banned cards found in either list!")
        return []

if __name__ == "__main__":
    banned_found = check_banned_overlap()
