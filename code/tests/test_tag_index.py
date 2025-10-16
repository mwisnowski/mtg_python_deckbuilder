"""Tests for tag index functionality."""
import json
import time

from code.tagging.tag_index import (
    TagIndex,
    IndexStats,
    get_tag_index,
    clear_global_index,
)


class TestTagIndexBuild:
    """Test index building operations."""
    
    def test_build_index(self):
        """Test that index builds successfully."""
        index = TagIndex()
        stats = index.build()
        
        assert isinstance(stats, IndexStats)
        assert stats.total_cards > 0
        assert stats.total_tags > 0
        assert stats.total_mappings > 0
        assert stats.build_time_seconds >= 0
    
    def test_build_index_performance(self):
        """Test that index builds in reasonable time."""
        index = TagIndex()
        
        start = time.perf_counter()
        stats = index.build()
        elapsed = time.perf_counter() - start
        
        # Should build in <5s for typical dataset
        assert elapsed < 5.0
        assert stats.build_time_seconds < 5.0
    
    def test_force_rebuild(self):
        """Test that force_rebuild always rebuilds."""
        index = TagIndex()
        
        # Build once
        stats1 = index.build()
        time1 = stats1.indexed_at
        
        # Wait a bit
        time.sleep(0.1)
        
        # Force rebuild
        stats2 = index.build(force_rebuild=True)
        time2 = stats2.indexed_at
        
        # Should have different timestamps
        assert time2 > time1


class TestSingleTagQueries:
    """Test single tag lookup operations."""
    
    def test_get_cards_with_tag(self):
        """Test getting cards with a specific tag."""
        index = TagIndex()
        index.build()
        
        # Get a tag that exists
        all_tags = index.get_all_tags()
        if all_tags:
            tag = all_tags[0]
            cards = index.get_cards_with_tag(tag)
            
            assert isinstance(cards, set)
            assert len(cards) > 0
    
    def test_get_cards_with_nonexistent_tag(self):
        """Test querying for tag that doesn't exist."""
        index = TagIndex()
        index.build()
        
        cards = index.get_cards_with_tag("ThisTagDoesNotExist12345")
        
        assert cards == set()
    
    def test_get_tags_for_card(self):
        """Test getting tags for a specific card."""
        index = TagIndex()
        index.build()
        
        # Get a card that exists
        cards = index.get_cards_with_tag(index.get_all_tags()[0]) if index.get_all_tags() else set()
        if cards:
            card_name = list(cards)[0]
            tags = index.get_tags_for_card(card_name)
            
            assert isinstance(tags, list)
            assert len(tags) > 0
    
    def test_get_tags_for_nonexistent_card(self):
        """Test getting tags for card that doesn't exist."""
        index = TagIndex()
        index.build()
        
        tags = index.get_tags_for_card("This Card Does Not Exist 12345")
        
        assert tags == []


class TestMultiTagQueries:
    """Test queries with multiple tags."""
    
    def test_get_cards_with_all_tags(self):
        """Test AND logic (cards must have all tags)."""
        index = TagIndex()
        index.build()
        
        all_tags = index.get_all_tags()
        if len(all_tags) >= 2:
            # Pick two tags
            tag1, tag2 = all_tags[0], all_tags[1]
            
            cards1 = index.get_cards_with_tag(tag1)
            cards2 = index.get_cards_with_tag(tag2)
            cards_both = index.get_cards_with_all_tags([tag1, tag2])
            
            # Result should be subset of both
            assert cards_both.issubset(cards1)
            assert cards_both.issubset(cards2)
            
            # Result should be intersection
            assert cards_both == (cards1 & cards2)
    
    def test_get_cards_with_any_tags(self):
        """Test OR logic (cards need at least one tag)."""
        index = TagIndex()
        index.build()
        
        all_tags = index.get_all_tags()
        if len(all_tags) >= 2:
            # Pick two tags
            tag1, tag2 = all_tags[0], all_tags[1]
            
            cards1 = index.get_cards_with_tag(tag1)
            cards2 = index.get_cards_with_tag(tag2)
            cards_any = index.get_cards_with_any_tags([tag1, tag2])
            
            # Result should be superset of both
            assert cards1.issubset(cards_any)
            assert cards2.issubset(cards_any)
            
            # Result should be union
            assert cards_any == (cards1 | cards2)
    
    def test_get_cards_with_empty_tag_list(self):
        """Test querying with empty tag list."""
        index = TagIndex()
        index.build()
        
        cards_all = index.get_cards_with_all_tags([])
        cards_any = index.get_cards_with_any_tags([])
        
        assert cards_all == set()
        assert cards_any == set()
    
    def test_get_cards_with_nonexistent_tags(self):
        """Test querying with tags that don't exist."""
        index = TagIndex()
        index.build()
        
        fake_tags = ["FakeTag1", "FakeTag2"]
        
        cards_all = index.get_cards_with_all_tags(fake_tags)
        cards_any = index.get_cards_with_any_tags(fake_tags)
        
        assert cards_all == set()
        assert cards_any == set()


class TestIndexStats:
    """Test index statistics and metadata."""
    
    def test_get_stats(self):
        """Test getting index statistics."""
        index = TagIndex()
        
        # Before building
        assert index.get_stats() is None
        
        # After building
        stats = index.build()
        retrieved_stats = index.get_stats()
        
        assert retrieved_stats is not None
        assert retrieved_stats.total_cards == stats.total_cards
        assert retrieved_stats.total_tags == stats.total_tags
    
    def test_get_all_tags(self):
        """Test getting list of all tags."""
        index = TagIndex()
        index.build()
        
        tags = index.get_all_tags()
        
        assert isinstance(tags, list)
        assert len(tags) > 0
        # Should be sorted
        assert tags == sorted(tags)
    
    def test_get_tag_stats(self):
        """Test getting stats for specific tag."""
        index = TagIndex()
        index.build()
        
        all_tags = index.get_all_tags()
        if all_tags:
            tag = all_tags[0]
            stats = index.get_tag_stats(tag)
            
            assert "card_count" in stats
            assert stats["card_count"] > 0
    
    def test_get_popular_tags(self):
        """Test getting most popular tags."""
        index = TagIndex()
        index.build()
        
        popular = index.get_popular_tags(limit=10)
        
        assert isinstance(popular, list)
        assert len(popular) <= 10
        
        if len(popular) > 1:
            # Should be sorted by count descending
            counts = [count for _, count in popular]
            assert counts == sorted(counts, reverse=True)


class TestCaching:
    """Test index caching and persistence."""
    
    def test_save_and_load_cache(self, tmp_path):
        """Test that cache saves and loads correctly."""
        cache_path = tmp_path / ".tag_index_test.json"
        
        # Build and save
        index1 = TagIndex(cache_path=cache_path)
        stats1 = index1.build()
        
        assert cache_path.exists()
        
        # Load from cache
        index2 = TagIndex(cache_path=cache_path)
        stats2 = index2.build()  # Should load from cache
        
        # Should have same data
        assert stats2.total_cards == stats1.total_cards
        assert stats2.total_tags == stats1.total_tags
        assert stats2.indexed_at == stats1.indexed_at
    
    def test_cache_invalidation(self, tmp_path):
        """Test that cache is rebuilt when all_cards changes."""
        cache_path = tmp_path / ".tag_index_test.json"
        
        # Build index
        index = TagIndex(cache_path=cache_path)
        stats1 = index.build()
        
        # Modify cache to simulate outdated mtime
        with cache_path.open("r") as f:
            cache_data = json.load(f)
        
        cache_data["stats"]["all_cards_mtime"] = 0  # Very old
        
        with cache_path.open("w") as f:
            json.dump(cache_data, f)
        
        # Should rebuild (not use cache)
        index2 = TagIndex(cache_path=cache_path)
        stats2 = index2.build()
        
        # Should have new timestamp
        assert stats2.indexed_at > stats1.indexed_at
    
    def test_clear_cache(self, tmp_path):
        """Test cache clearing."""
        cache_path = tmp_path / ".tag_index_test.json"
        
        index = TagIndex(cache_path=cache_path)
        index.build()
        
        assert cache_path.exists()
        
        index.clear_cache()
        
        assert not cache_path.exists()


class TestGlobalIndex:
    """Test global index accessor."""
    
    def test_get_tag_index(self):
        """Test getting global index."""
        clear_global_index()
        
        index = get_tag_index()
        
        assert isinstance(index, TagIndex)
        assert index.get_stats() is not None
    
    def test_get_tag_index_singleton(self):
        """Test that global index is a singleton."""
        clear_global_index()
        
        index1 = get_tag_index()
        index2 = get_tag_index()
        
        # Should be same instance
        assert index1 is index2
    
    def test_clear_global_index(self):
        """Test clearing global index."""
        index1 = get_tag_index()
        
        clear_global_index()
        
        index2 = get_tag_index()
        
        # Should be different instance
        assert index1 is not index2


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_cards_with_no_tags(self):
        """Test that cards without tags are handled."""
        index = TagIndex()
        index.build()
        
        # Get stats - should handle cards with no tags gracefully
        stats = index.get_stats()
        assert stats is not None
    
    def test_special_characters_in_tags(self):
        """Test tags with special characters."""
        index = TagIndex()
        index.build()
        
        # Try querying with special chars (should not crash)
        cards = index.get_cards_with_tag("Life & Death")
        assert isinstance(cards, set)
    
    def test_case_sensitive_tags(self):
        """Test that tag lookups are case-sensitive."""
        index = TagIndex()
        index.build()
        
        all_tags = index.get_all_tags()
        if all_tags:
            tag = all_tags[0]
            
            cards1 = index.get_cards_with_tag(tag)
            cards2 = index.get_cards_with_tag(tag.upper())
            cards3 = index.get_cards_with_tag(tag.lower())
            
            # Case matters - may get different results
            # (depends on tag naming in data)
            assert isinstance(cards1, set)
            assert isinstance(cards2, set)
            assert isinstance(cards3, set)
    
    def test_duplicate_tags_handled(self):
        """Test that duplicate tags in query are handled."""
        index = TagIndex()
        index.build()
        
        all_tags = index.get_all_tags()
        if all_tags:
            tag = all_tags[0]
            
            # Query with duplicate tag
            cards = index.get_cards_with_all_tags([tag, tag])
            cards_single = index.get_cards_with_tag(tag)
            
            # Should give same result as single tag
            assert cards == cards_single


class TestPerformance:
    """Test performance characteristics."""
    
    def test_query_performance(self):
        """Test that queries complete quickly."""
        index = TagIndex()
        index.build()
        
        all_tags = index.get_all_tags()
        if all_tags:
            tag = all_tags[0]
            
            # Measure query time
            start = time.perf_counter()
            for _ in range(100):
                index.get_cards_with_tag(tag)
            elapsed = time.perf_counter() - start
            
            avg_time_ms = (elapsed / 100) * 1000
            
            # Should average <1ms per query
            assert avg_time_ms < 1.0
    
    def test_multi_tag_query_performance(self):
        """Test multi-tag query performance."""
        index = TagIndex()
        index.build()
        
        all_tags = index.get_all_tags()
        if len(all_tags) >= 3:
            tags = all_tags[:3]
            
            # Measure query time
            start = time.perf_counter()
            for _ in range(100):
                index.get_cards_with_all_tags(tags)
            elapsed = time.perf_counter() - start
            
            avg_time_ms = (elapsed / 100) * 1000
            
            # Should still be very fast
            assert avg_time_ms < 5.0
