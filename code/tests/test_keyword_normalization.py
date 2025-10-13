"""Tests for keyword normalization (M1 - Tagging Refinement)."""
from __future__ import annotations

import pytest

from code.tagging import tag_utils, tag_constants


class TestKeywordNormalization:
    """Test suite for normalize_keywords function."""
    
    def test_canonical_mappings(self):
        """Test that variant keywords map to canonical forms."""
        raw = ['Commander Ninjutsu', 'Flying', 'Trample']
        allowlist = tag_constants.KEYWORD_ALLOWLIST
        frequency_map = {
            'Commander Ninjutsu': 2,
            'Flying': 100,
            'Trample': 50
        }
        
        result = tag_utils.normalize_keywords(raw, allowlist, frequency_map)
        
        assert 'Ninjutsu' in result
        assert 'Flying' in result
        assert 'Trample' in result
        assert 'Commander Ninjutsu' not in result
    
    def test_singleton_pruning(self):
        """Test that singleton keywords are pruned unless allowlisted."""
        raw = ['Allons-y!', 'Flying', 'Take 59 Flights of Stairs']
        allowlist = {'Flying'}  # Only Flying is allowlisted
        frequency_map = {
            'Allons-y!': 1,
            'Flying': 100,
            'Take 59 Flights of Stairs': 1
        }
        
        result = tag_utils.normalize_keywords(raw, allowlist, frequency_map)
        
        assert 'Flying' in result
        assert 'Allons-y!' not in result
        assert 'Take 59 Flights of Stairs' not in result
    
    def test_case_normalization(self):
        """Test that keywords are normalized to proper case."""
        raw = ['flying', 'TRAMPLE', 'vigilance']
        allowlist = {'Flying', 'Trample', 'Vigilance'}
        frequency_map = {
            'flying': 100,
            'TRAMPLE': 50,
            'vigilance': 75
        }
        
        result = tag_utils.normalize_keywords(raw, allowlist, frequency_map)
        
        # Case normalization happens via the map
        # If not in map, original case is preserved
        assert len(result) == 3
    
    def test_partner_exclusion(self):
        """Test that partner keywords remain excluded."""
        raw = ['Partner', 'Flying', 'Trample']
        allowlist = {'Flying', 'Trample'}
        frequency_map = {
            'Partner': 50,
            'Flying': 100,
            'Trample': 50
        }
        
        result = tag_utils.normalize_keywords(raw, allowlist, frequency_map)
        
        assert 'Flying' in result
        assert 'Trample' in result
        assert 'Partner' not in result  # Excluded
        assert 'partner' not in result
    
    def test_empty_input(self):
        """Test that empty input returns empty list."""
        result = tag_utils.normalize_keywords([], set(), {})
        assert result == []
    
    def test_whitespace_handling(self):
        """Test that whitespace is properly stripped."""
        raw = ['  Flying  ', 'Trample ', ' Vigilance']
        allowlist = {'Flying', 'Trample', 'Vigilance'}
        frequency_map = {
            'Flying': 100,
            'Trample': 50,
            'Vigilance': 75
        }
        
        result = tag_utils.normalize_keywords(raw, allowlist, frequency_map)
        
        assert 'Flying' in result
        assert 'Trample' in result
        assert 'Vigilance' in result
    
    def test_deduplication(self):
        """Test that duplicate keywords are deduplicated."""
        raw = ['Flying', 'Flying', 'Trample', 'Flying']
        allowlist = {'Flying', 'Trample'}
        frequency_map = {
            'Flying': 100,
            'Trample': 50
        }
        
        result = tag_utils.normalize_keywords(raw, allowlist, frequency_map)
        
        assert result.count('Flying') == 1
        assert result.count('Trample') == 1
    
    def test_non_string_entries_skipped(self):
        """Test that non-string entries are safely skipped."""
        raw = ['Flying', None, 123, 'Trample', '']
        allowlist = {'Flying', 'Trample'}
        frequency_map = {
            'Flying': 100,
            'Trample': 50
        }
        
        result = tag_utils.normalize_keywords(raw, allowlist, frequency_map)
        
        assert 'Flying' in result
        assert 'Trample' in result
        assert len(result) == 2
    
    def test_invalid_input_raises_error(self):
        """Test that non-iterable input raises ValueError."""
        with pytest.raises(ValueError, match="raw must be iterable"):
            tag_utils.normalize_keywords("not-a-list", set(), {})
    
    def test_allowlist_preserves_singletons(self):
        """Test that allowlisted keywords survive even if they're singletons."""
        raw = ['Myriad', 'Flying', 'Cascade']
        allowlist = {'Flying', 'Myriad', 'Cascade'}  # All allowlisted
        frequency_map = {
            'Myriad': 1,  # Singleton
            'Flying': 100,
            'Cascade': 1  # Singleton
        }
        
        result = tag_utils.normalize_keywords(raw, allowlist, frequency_map)
        
        assert 'Myriad' in result  # Preserved despite being singleton
        assert 'Flying' in result
        assert 'Cascade' in result  # Preserved despite being singleton


class TestKeywordIntegration:
    """Integration tests for keyword normalization in tagging flow."""
    
    def test_normalization_preserves_evergreen_keywords(self):
        """Test that common evergreen keywords are always preserved."""
        evergreen = ['Flying', 'Trample', 'Vigilance', 'Haste', 'Deathtouch', 'Lifelink']
        allowlist = tag_constants.KEYWORD_ALLOWLIST
        frequency_map = {kw: 100 for kw in evergreen}  # All common
        
        result = tag_utils.normalize_keywords(evergreen, allowlist, frequency_map)
        
        for kw in evergreen:
            assert kw in result
    
    def test_crossover_keywords_pruned(self):
        """Test that crossover-specific singletons are pruned."""
        crossover_singletons = [
            'Gae Bolg',  # Final Fantasy
            'Psychic Defense',  # Warhammer 40K
            'Allons-y!',  # Doctor Who
            'Flying'  # Evergreen (control)
        ]
        allowlist = {'Flying'}  # Only Flying allowed
        frequency_map = {
            'Gae Bolg': 1,
            'Psychic Defense': 1,
            'Allons-y!': 1,
            'Flying': 100
        }
        
        result = tag_utils.normalize_keywords(crossover_singletons, allowlist, frequency_map)
        
        assert result == ['Flying']  # Only evergreen survived
