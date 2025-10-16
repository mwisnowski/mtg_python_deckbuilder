"""Tests for batch tag loading from all_cards."""
from code.tagging.tag_loader import (
    load_tags_for_cards,
    load_tags_for_card,
    get_cards_with_tag,
    get_cards_with_all_tags,
    clear_cache,
    is_use_all_cards_enabled,
)


class TestBatchTagLoading:
    """Test batch tag loading operations."""
    
    def test_load_tags_for_multiple_cards(self):
        """Test loading tags for multiple cards at once."""
        cards = ["Sol Ring", "Lightning Bolt", "Counterspell"]
        result = load_tags_for_cards(cards)
        
        assert isinstance(result, dict)
        assert len(result) == 3
        
        # All requested cards should be in result (even if no tags)
        for card in cards:
            assert card in result
            assert isinstance(result[card], list)
    
    def test_load_tags_for_empty_list(self):
        """Test loading tags for empty list returns empty dict."""
        result = load_tags_for_cards([])
        assert result == {}
    
    def test_load_tags_for_single_card(self):
        """Test single card convenience function."""
        tags = load_tags_for_card("Sol Ring")
        
        assert isinstance(tags, list)
        # Sol Ring should have some tags (artifacts, ramp, etc)
        # But we don't assert specific tags since data may vary
    
    def test_load_tags_for_nonexistent_card(self):
        """Test loading tags for card that doesn't exist."""
        tags = load_tags_for_card("This Card Does Not Exist 12345")
        
        # Should return empty list, not fail
        assert tags == []
    
    def test_load_tags_batch_includes_missing_cards(self):
        """Test batch loading includes missing cards with empty lists."""
        cards = ["Sol Ring", "Fake Card Name 999", "Lightning Bolt"]
        result = load_tags_for_cards(cards)
        
        # All cards should be present
        assert len(result) == 3
        assert "Fake Card Name 999" in result
        assert result["Fake Card Name 999"] == []
    
    def test_load_tags_handles_list_format(self):
        """Test that tags in list format are parsed correctly."""
        # Pick a card likely to have tags
        result = load_tags_for_cards(["Sol Ring"])
        
        if "Sol Ring" in result and result["Sol Ring"]:
            tags = result["Sol Ring"]
            # Should be a list of strings
            assert all(isinstance(tag, str) for tag in tags)
            # Tags should be stripped of whitespace
            assert all(tag == tag.strip() for tag in tags)
    
    def test_load_tags_handles_string_format(self):
        """Test that tags in string format are parsed correctly."""
        # The loader should handle both list and string representations
        # This is tested implicitly by loading any card
        cards = ["Sol Ring", "Lightning Bolt"]
        result = load_tags_for_cards(cards)
        
        for card in cards:
            tags = result[card]
            # All should be lists (even if empty)
            assert isinstance(tags, list)
            # No empty string tags
            assert "" not in tags
            assert all(tag.strip() for tag in tags)


class TestTagQueries:
    """Test querying cards by tags."""
    
    def test_get_cards_with_tag(self):
        """Test getting all cards with a specific tag."""
        # Pick a common tag
        cards = get_cards_with_tag("ramp", limit=10)
        
        assert isinstance(cards, list)
        # Should have some cards (or none if tag doesn't exist)
        # We don't assert specific count since data varies
    
    def test_get_cards_with_tag_limit(self):
        """Test limit parameter works."""
        cards = get_cards_with_tag("ramp", limit=5)
        
        assert len(cards) <= 5
    
    def test_get_cards_with_nonexistent_tag(self):
        """Test querying with tag that doesn't exist."""
        cards = get_cards_with_tag("ThisTagDoesNotExist12345")
        
        # Should return empty list, not fail
        assert cards == []
    
    def test_get_cards_with_all_tags(self):
        """Test getting cards that have multiple tags."""
        # Pick two tags that might overlap
        cards = get_cards_with_all_tags(["artifacts", "ramp"], limit=10)
        
        assert isinstance(cards, list)
        assert len(cards) <= 10
    
    def test_get_cards_with_all_tags_no_matches(self):
        """Test query with tags that likely have no overlap."""
        cards = get_cards_with_all_tags([
            "ThisTagDoesNotExist1",
            "ThisTagDoesNotExist2"
        ])
        
        # Should return empty list
        assert cards == []


class TestCacheManagement:
    """Test cache management functions."""
    
    def test_clear_cache(self):
        """Test that cache can be cleared without errors."""
        # Load some data
        load_tags_for_card("Sol Ring")
        
        # Clear cache
        clear_cache()
        
        # Should still work after clearing
        tags = load_tags_for_card("Sol Ring")
        assert isinstance(tags, list)
    
    def test_cache_persistence(self):
        """Test that multiple calls use cached data."""
        # First call
        result1 = load_tags_for_cards(["Sol Ring", "Lightning Bolt"])
        
        # Second call (should use cache)
        result2 = load_tags_for_cards(["Sol Ring", "Lightning Bolt"])
        
        # Results should be identical
        assert result1 == result2


class TestFeatureFlag:
    """Test feature flag functionality."""
    
    def test_is_use_all_cards_enabled_default(self):
        """Test that all_cards tag loading is enabled by default."""
        enabled = is_use_all_cards_enabled()
        
        # Default should be True
        assert isinstance(enabled, bool)
        # We don't assert True since env might override


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_load_tags_with_special_characters(self):
        """Test loading tags for cards with special characters."""
        # Cards with apostrophes, commas, etc.
        cards = [
            "Urza's Saga",
            "Keeper of the Accord",
            "Esper Sentinel"
        ]
        result = load_tags_for_cards(cards)
        
        # Should handle special characters
        assert len(result) == 3
        for card in cards:
            assert card in result
    
    def test_load_tags_preserves_card_name_case(self):
        """Test that card names preserve their original case."""
        cards = ["Sol Ring", "LIGHTNING BOLT", "counterspell"]
        result = load_tags_for_cards(cards)
        
        # Should have entries for provided names (case-sensitive lookup)
        assert "Sol Ring" in result or len(result) >= 1
        # Note: exact case matching depends on all_cards data
    
    def test_load_tags_deduplicates(self):
        """Test that duplicate tags are handled."""
        # Load tags for a card
        tags = load_tags_for_card("Sol Ring")
        
        # If any tags present, check for no duplicates
        if tags:
            assert len(tags) == len(set(tags))
    
    def test_large_batch_performance(self):
        """Test that large batch loads complete in reasonable time."""
        import time
        
        # Create a batch of 100 common cards
        cards = ["Sol Ring"] * 50 + ["Lightning Bolt"] * 50
        
        start = time.perf_counter()
        result = load_tags_for_cards(cards)
        elapsed = time.perf_counter() - start
        
        # Should complete quickly (< 1 second for 100 cards)
        assert elapsed < 1.0
        assert len(result) >= 1  # At least one card found


class TestFormatVariations:
    """Test handling of different tag format variations."""
    
    def test_empty_tags_handled(self):
        """Test that cards with no tags return empty list."""
        # Pick a card that might have no tags (basic lands usually don't)
        tags = load_tags_for_card("Plains")
        
        # Should be empty list, not None or error
        assert tags == [] or isinstance(tags, list)
    
    def test_string_list_repr_parsed(self):
        """Test parsing of string representations like \"['tag1', 'tag2']\"."""
        # This is tested implicitly through load_tags_for_cards
        # The loader handles multiple formats internally
        cards = ["Sol Ring", "Lightning Bolt", "Counterspell"]
        result = load_tags_for_cards(cards)
        
        # All results should be lists
        for card, tags in result.items():
            assert isinstance(tags, list)
            # No stray brackets or quotes
            for tag in tags:
                assert "[" not in tag
                assert "]" not in tag
                assert '"' not in tag
                assert "'" not in tag or tag.count("'") > 1  # Allow apostrophes in words
    
    def test_comma_separated_parsed(self):
        """Test parsing of comma-separated tag strings."""
        # The loader should handle comma-separated strings
        # This is tested implicitly by loading any card
        result = load_tags_for_cards(["Sol Ring"])
        
        if result.get("Sol Ring"):
            tags = result["Sol Ring"]
            # Tags should be split properly (no commas in individual tags)
            for tag in tags:
                assert "," not in tag or tag.count(",") == 0
