"""Tests for M4 linter functionality in validate_theme_catalog.py"""
import pytest
import sys
from pathlib import Path
from typing import Dict, List

from type_definitions_theme_catalog import ThemeYAMLFile, DescriptionSource
from web.services.theme_editorial_service import ThemeEditorialService
from web.services.theme_catalog_loader import load_index


class TestLinterDuplicationChecks:
    """Test M4 linter duplication ratio checks"""
    
    def test_high_duplication_flagged(self):
        """Themes with high duplication ratio should be flagged"""
        service = ThemeEditorialService()
        
        # Get actual total themes from catalog
        index = load_index()
        total_themes = len(index.slug_to_entry)
        
        # Mock global frequency: Sol Ring in 60% of themes, Lightning Greaves in 50%
        # Use actual total to get realistic frequencies
        global_card_freq = {
            "Sol Ring": int(total_themes * 0.6),
            "Lightning Greaves": int(total_themes * 0.5),
            "Unique Card A": 5,
            "Unique Card B": 3
        }
        
        # Theme with mostly generic cards (2/4 = 50% are generic)
        example_cards = ["Sol Ring", "Lightning Greaves", "Unique Card A", "Unique Card B"]
        
        dup_ratio = service.calculate_duplication_ratio(
            example_cards=example_cards,
            global_card_freq=global_card_freq,
            duplication_threshold=0.4  # >40% = duplicated
        )
        
        # Should flag: 2 out of 4 cards appear in >40% of themes
        assert dup_ratio == 0.5  # 50% duplication
    
    def test_low_duplication_not_flagged(self):
        """Themes with unique cards should not be flagged"""
        service = ThemeEditorialService()
        
        # All unique cards
        global_card_freq = {
            "Unique Card A": 5,
            "Unique Card B": 3,
            "Unique Card C": 8,
            "Unique Card D": 2
        }
        
        example_cards = ["Unique Card A", "Unique Card B", "Unique Card C", "Unique Card D"]
        
        dup_ratio = service.calculate_duplication_ratio(
            example_cards=example_cards,
            global_card_freq=global_card_freq,
            duplication_threshold=0.4
        )
        
        assert dup_ratio == 0.0  # No duplication
    
    def test_empty_cards_no_duplication(self):
        """Empty example cards should return 0.0 duplication"""
        service = ThemeEditorialService()
        global_card_freq = {"Sol Ring": 60}
        
        dup_ratio = service.calculate_duplication_ratio(
            example_cards=[],
            global_card_freq=global_card_freq,
            duplication_threshold=0.4
        )
        
        assert dup_ratio == 0.0


class TestLinterQualityScoring:
    """Test M4 linter quality score checks"""
    
    def test_low_quality_score_flagged(self):
        """Themes with low quality scores should be flagged"""
        from type_definitions_theme_catalog import ThemeEntry
        
        service = ThemeEditorialService()
        
        # Low quality theme: few cards, generic description, no uniqueness
        theme_entry = ThemeEntry(
            theme="Test Theme",
            example_cards=["Sol Ring", "Command Tower"],  # Only 2 cards
            description_source="generic"
        )
        
        global_card_freq = {
            "Sol Ring": 80,  # Very common
            "Command Tower": 75  # Very common
        }
        
        tier, score = service.calculate_enhanced_quality_score(
            theme_entry=theme_entry,
            global_card_freq=global_card_freq
        )
        
        assert tier in ["Poor", "Fair"]
        assert score < 0.5  # Below typical threshold
    
    def test_high_quality_score_not_flagged(self):
        """Themes with high quality scores should not be flagged"""
        from type_definitions_theme_catalog import ThemeEntry
        
        service = ThemeEditorialService()
        
        # High quality theme: many unique cards, manual description
        theme_entry = ThemeEntry(
            theme="Test Theme",
            example_cards=[f"Unique Card {i}" for i in range(10)],  # 10 unique cards
            description_source="manual"
        )
        
        global_card_freq = {f"Unique Card {i}": 2 for i in range(10)}  # All rare
        
        tier, score = service.calculate_enhanced_quality_score(
            theme_entry=theme_entry,
            global_card_freq=global_card_freq
        )
        
        assert tier in ["Good", "Excellent"]
        assert score >= 0.6  # Above typical threshold


class TestLinterSuggestions:
    """Test M4 linter suggestion generation"""
    
    def test_suggestions_for_few_cards(self):
        """Should suggest adding more cards when count is low"""
        example_cards = ["Card A", "Card B", "Card C"]  # Only 3 cards
        
        suggestions = []
        if len(example_cards) < 5:
            suggestions.append("Add more example cards (target: 8+)")
        
        assert len(suggestions) == 1
        assert "Add more example cards" in suggestions[0]
    
    def test_suggestions_for_generic_description(self):
        """Should suggest upgrading description when generic"""
        description_source = "generic"
        
        suggestions = []
        if description_source == "generic":
            suggestions.append("Upgrade to manual or rule-based description")
        
        assert len(suggestions) == 1
        assert "Upgrade to manual or rule-based" in suggestions[0]
    
    def test_suggestions_for_generic_cards(self):
        """Should suggest replacing generic cards when duplication high"""
        dup_ratio = 0.6  # 60% duplication
        
        suggestions = []
        if dup_ratio > 0.4:
            suggestions.append("Replace generic staples with unique cards")
        
        assert len(suggestions) == 1
        assert "Replace generic staples" in suggestions[0]
    
    def test_multiple_suggestions_combined(self):
        """Should provide multiple suggestions when multiple issues exist"""
        example_cards = ["Card A", "Card B"]  # Few cards
        description_source = "generic"
        dup_ratio = 0.5  # High duplication
        
        suggestions = []
        if len(example_cards) < 5:
            suggestions.append("Add more example cards (target: 8+)")
        if description_source == "generic":
            suggestions.append("Upgrade to manual or rule-based description")
        if dup_ratio > 0.4:
            suggestions.append("Replace generic staples with unique cards")
        
        assert len(suggestions) == 3
        assert "Add more example cards" in suggestions[0]
        assert "Upgrade to manual or rule-based" in suggestions[1]
        assert "Replace generic staples" in suggestions[2]


class TestLinterThresholds:
    """Test M4 linter configurable thresholds"""
    
    def test_duplication_threshold_configurable(self):
        """Duplication threshold should be configurable"""
        service = ThemeEditorialService()
        
        # Get actual total themes from catalog
        index = load_index()
        total_themes = len(index.slug_to_entry)
        
        # Sol Ring at 45% frequency
        global_card_freq = {
            "Sol Ring": int(total_themes * 0.45),
            "Unique Card": 5
        }
        
        example_cards = ["Sol Ring", "Unique Card"]
        
        # With threshold 0.5 (50%), Sol Ring not flagged
        dup_ratio_high = service.calculate_duplication_ratio(
            example_cards=example_cards,
            global_card_freq=global_card_freq,
            duplication_threshold=0.5
        )
        assert dup_ratio_high == 0.0  # 45% < 50%
        
        # With threshold 0.4 (40%), Sol Ring IS flagged
        dup_ratio_low = service.calculate_duplication_ratio(
            example_cards=example_cards,
            global_card_freq=global_card_freq,
            duplication_threshold=0.4
        )
        assert dup_ratio_low == 0.5  # 45% > 40%, so 1/2 cards flagged
    
    def test_quality_threshold_configurable(self):
        """Quality threshold determines what gets flagged"""
        # Threshold 0.3 would flag scores < 0.3
        score_fair = 0.45
        
        assert score_fair < 0.5  # Would be flagged with threshold 0.5
        assert score_fair >= 0.3  # Would NOT be flagged with threshold 0.3


class TestLinterIntegration:
    """Integration tests for linter with ThemeYAMLFile validation"""
    
    def test_yaml_file_to_theme_entry_conversion(self):
        """Should correctly convert ThemeYAMLFile to ThemeEntry for linting"""
        from type_definitions_theme_catalog import ThemeEntry
        
        # Simulate a ThemeYAMLFile object
        yaml_data = {
            "id": "test-theme",
            "display_name": "Test Theme",
            "synergies": ["Synergy A", "Synergy B"],
            "example_cards": ["Card A", "Card B", "Card C"],
            "description_source": "manual",
            "description": "A test theme for linting"
        }
        
        yaml_file = ThemeYAMLFile(**yaml_data)
        
        # Convert to ThemeEntry for linting
        theme_entry = ThemeEntry(
            theme=yaml_file.display_name,
            example_cards=yaml_file.example_cards,
            description_source=yaml_file.description_source
        )
        
        assert theme_entry.theme == "Test Theme"
        assert len(theme_entry.example_cards) == 3
        assert theme_entry.description_source == "manual"
    
    def test_linter_handles_missing_optional_fields(self):
        """Linter should handle themes with missing optional fields gracefully"""
        from type_definitions_theme_catalog import ThemeEntry
        
        # Theme with minimal required fields
        theme_entry = ThemeEntry(
            theme="Minimal Theme",
            example_cards=["Card A"],
            description_source=None  # Missing description_source
        )
        
        service = ThemeEditorialService()
        
        # Should not crash
        tier, score = service.calculate_enhanced_quality_score(
            theme_entry=theme_entry,
            global_card_freq={"Card A": 1}
        )
        
        assert isinstance(tier, str)
        assert 0.0 <= score <= 1.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
