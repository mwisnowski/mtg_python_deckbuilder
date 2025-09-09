"""
Unit tests for include/exclude utilities.

Tests the fuzzy matching, normalization, and validation functions
that support the must-include/must-exclude feature.
"""

import pytest
from typing import Set

from deck_builder.include_exclude_utils import (
    normalize_card_name,
    normalize_punctuation,
    fuzzy_match_card_name,
    validate_list_sizes,
    collapse_duplicates,
    parse_card_list_input,
    get_baseline_performance_metrics,
    FuzzyMatchResult,
    FUZZY_CONFIDENCE_THRESHOLD,
    MAX_INCLUDES,
    MAX_EXCLUDES
)


class TestNormalization:
    """Test card name normalization functions."""
    
    def test_normalize_card_name_basic(self):
        """Test basic name normalization."""
        assert normalize_card_name("Lightning Bolt") == "lightning bolt"
        assert normalize_card_name("  Sol Ring  ") == "sol ring"
        assert normalize_card_name("") == ""
        
    def test_normalize_card_name_unicode(self):
        """Test unicode character normalization."""
        # Curly apostrophe to straight
        assert normalize_card_name("Thassa's Oracle") == "thassa's oracle"
        # Test case from combo tag applier
        assert normalize_card_name("Thassa\u2019s Oracle") == "thassa's oracle"
        
    def test_normalize_card_name_arena_prefix(self):
        """Test Arena/Alchemy prefix removal."""
        assert normalize_card_name("A-Lightning Bolt") == "lightning bolt"
        assert normalize_card_name("A-") == "a-"  # Edge case: too short
        
    def test_normalize_punctuation_commas(self):
        """Test punctuation normalization for commas."""
        assert normalize_punctuation("Krenko, Mob Boss") == "krenko mob boss"
        assert normalize_punctuation("Krenko Mob Boss") == "krenko mob boss"
        # Should be equivalent for fuzzy matching
        assert (normalize_punctuation("Krenko, Mob Boss") == 
                normalize_punctuation("Krenko Mob Boss"))


class TestFuzzyMatching:
    """Test fuzzy card name matching."""
    
    @pytest.fixture
    def sample_card_names(self) -> Set[str]:
        """Sample card names for testing."""
        return {
            "Lightning Bolt",
            "Lightning Strike", 
            "Lightning Helix",
            "Krenko, Mob Boss",
            "Sol Ring",
            "Thassa's Oracle",
            "Demonic Consultation"
        }
    
    def test_exact_match(self, sample_card_names):
        """Test exact name matching."""
        result = fuzzy_match_card_name("Lightning Bolt", sample_card_names)
        assert result.matched_name == "Lightning Bolt"
        assert result.confidence == 1.0
        assert result.auto_accepted is True
        assert len(result.suggestions) == 0
        
    def test_exact_match_after_normalization(self, sample_card_names):
        """Test exact match after punctuation normalization."""
        result = fuzzy_match_card_name("Krenko Mob Boss", sample_card_names)
        assert result.matched_name == "Krenko, Mob Boss"
        assert result.confidence == 1.0
        assert result.auto_accepted is True
        
    def test_typo_suggestion(self, sample_card_names):
        """Test typo suggestions."""
        result = fuzzy_match_card_name("Lightnig Bolt", sample_card_names)
        assert "Lightning Bolt" in result.suggestions
        # Should have high confidence but maybe not auto-accepted depending on threshold
        assert result.confidence > 0.8
        
    def test_ambiguous_match(self, sample_card_names):
        """Test ambiguous input requiring confirmation."""
        result = fuzzy_match_card_name("Lightning", sample_card_names)
        # Should return multiple lightning-related suggestions
        lightning_suggestions = [s for s in result.suggestions if "Lightning" in s]
        assert len(lightning_suggestions) >= 2
        
    def test_no_match(self, sample_card_names):
        """Test input with no reasonable matches."""
        result = fuzzy_match_card_name("Completely Invalid Card", sample_card_names)
        assert result.matched_name is None
        assert result.confidence == 0.0
        assert result.auto_accepted is False
        
    def test_empty_input(self, sample_card_names):
        """Test empty input handling."""
        result = fuzzy_match_card_name("", sample_card_names)
        assert result.matched_name is None
        assert result.confidence == 0.0
        assert result.auto_accepted is False


class TestValidation:
    """Test validation functions."""
    
    def test_validate_list_sizes_valid(self):
        """Test validation with acceptable list sizes."""
        includes = ["Card A", "Card B"]  # Well under limit
        excludes = ["Card X", "Card Y", "Card Z"]  # Well under limit
        
        result = validate_list_sizes(includes, excludes)
        assert result['valid'] is True
        assert len(result['errors']) == 0
        assert result['counts']['includes'] == 2
        assert result['counts']['excludes'] == 3
        
    def test_validate_list_sizes_warnings(self):
        """Test warning thresholds."""
        includes = ["Card"] * 8  # 80% of 10 = 8, should trigger warning
        excludes = ["Card"] * 12  # 80% of 15 = 12, should trigger warning
        
        result = validate_list_sizes(includes, excludes)
        assert result['valid'] is True
        assert 'includes_approaching_limit' in result['warnings']
        assert 'excludes_approaching_limit' in result['warnings']
        
    def test_validate_list_sizes_errors(self):
        """Test size limit errors."""
        includes = ["Card"] * 15  # Over limit of 10
        excludes = ["Card"] * 20  # Over limit of 15
        
        result = validate_list_sizes(includes, excludes)
        assert result['valid'] is False
        assert len(result['errors']) == 2
        assert "Too many include cards" in result['errors'][0]
        assert "Too many exclude cards" in result['errors'][1]


class TestDuplicateCollapse:
    """Test duplicate handling."""
    
    def test_collapse_duplicates_basic(self):
        """Test basic duplicate removal."""
        names = ["Lightning Bolt", "Sol Ring", "Lightning Bolt"]
        unique, duplicates = collapse_duplicates(names)
        
        assert len(unique) == 2
        assert "Lightning Bolt" in unique
        assert "Sol Ring" in unique
        assert duplicates["Lightning Bolt"] == 2
        
    def test_collapse_duplicates_case_insensitive(self):
        """Test case-insensitive duplicate detection."""
        names = ["Lightning Bolt", "LIGHTNING BOLT", "lightning bolt"]
        unique, duplicates = collapse_duplicates(names)
        
        assert len(unique) == 1
        assert duplicates[unique[0]] == 3
        
    def test_collapse_duplicates_empty(self):
        """Test empty input."""
        unique, duplicates = collapse_duplicates([])
        assert unique == []
        assert duplicates == {}
        
    def test_collapse_duplicates_whitespace(self):
        """Test whitespace handling."""
        names = ["Lightning Bolt", "  Lightning Bolt  ", "", "   "]
        unique, duplicates = collapse_duplicates(names)
        
        assert len(unique) == 1
        assert duplicates[unique[0]] == 2


class TestInputParsing:
    """Test input parsing functions."""
    
    def test_parse_card_list_newlines(self):
        """Test newline-separated input."""
        input_text = "Lightning Bolt\nSol Ring\nKrenko, Mob Boss"
        result = parse_card_list_input(input_text)
        
        assert len(result) == 3
        assert "Lightning Bolt" in result
        assert "Sol Ring" in result
        assert "Krenko, Mob Boss" in result
        
    def test_parse_card_list_commas(self):
        """Test comma-separated input (no newlines)."""
        input_text = "Lightning Bolt, Sol Ring, Thassa's Oracle"
        result = parse_card_list_input(input_text)
        
        assert len(result) == 3
        assert "Lightning Bolt" in result
        assert "Sol Ring" in result
        assert "Thassa's Oracle" in result
        
    def test_parse_card_list_commas_in_names(self):
        """Test that commas in card names are preserved when using newlines."""
        input_text = "Krenko, Mob Boss\nFinneas, Ace Archer"
        result = parse_card_list_input(input_text)
        
        assert len(result) == 2
        assert "Krenko, Mob Boss" in result
        assert "Finneas, Ace Archer" in result
        
    def test_parse_card_list_mixed(self):
        """Test that newlines take precedence over commas."""
        # When both separators present, newlines take precedence
        input_text = "Lightning Bolt\nKrenko, Mob Boss\nThassa's Oracle"
        result = parse_card_list_input(input_text)
        
        assert len(result) == 3
        assert "Lightning Bolt" in result
        assert "Krenko, Mob Boss" in result  # Comma preserved in name
        assert "Thassa's Oracle" in result
        
    def test_parse_card_list_empty(self):
        """Test empty input."""
        assert parse_card_list_input("") == []
        assert parse_card_list_input("   ") == []
        assert parse_card_list_input("\n\n\n") == []
        assert parse_card_list_input("   ,   ,   ") == []


class TestPerformance:
    """Test performance measurement functions."""
    
    def test_baseline_performance_metrics(self):
        """Test baseline performance measurement."""
        metrics = get_baseline_performance_metrics()
        
        assert 'normalization_time_ms' in metrics
        assert 'operations_count' in metrics
        assert 'timestamp' in metrics
        
        # Should be reasonably fast
        assert metrics['normalization_time_ms'] < 1000  # Less than 1 second
        assert metrics['operations_count'] > 0


class TestFeatureFlagIntegration:
    """Test feature flag integration."""
    
    def test_constants_defined(self):
        """Test that required constants are properly defined."""
        assert isinstance(FUZZY_CONFIDENCE_THRESHOLD, float)
        assert 0.0 <= FUZZY_CONFIDENCE_THRESHOLD <= 1.0
        
        assert isinstance(MAX_INCLUDES, int)
        assert MAX_INCLUDES > 0
        
        assert isinstance(MAX_EXCLUDES, int)
        assert MAX_EXCLUDES > 0
        
    def test_fuzzy_match_result_structure(self):
        """Test FuzzyMatchResult dataclass structure."""
        result = FuzzyMatchResult(
            input_name="test",
            matched_name="Test Card",
            confidence=0.95,
            suggestions=["Test Card", "Other Card"],
            auto_accepted=True
        )
        
        assert result.input_name == "test"
        assert result.matched_name == "Test Card"
        assert result.confidence == 0.95
        assert len(result.suggestions) == 2
        assert result.auto_accepted is True
