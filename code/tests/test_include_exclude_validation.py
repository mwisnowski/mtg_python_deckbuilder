"""
Unit tests for include/exclude card validation and processing functionality.

Tests schema integration, validation utilities, fuzzy matching, strict enforcement,
and JSON export behavior for the include/exclude card system.
"""

import pytest
import json
import tempfile
from deck_builder.builder import DeckBuilder
from deck_builder.include_exclude_utils import (
    IncludeExcludeDiagnostics,
    validate_list_sizes,
    collapse_duplicates,
    parse_card_list_input
)


class TestIncludeExcludeSchema:
    """Test that DeckBuilder properly supports include/exclude configuration."""
    
    def test_default_values(self):
        """Test that DeckBuilder has correct default values for include/exclude fields."""
        builder = DeckBuilder()
        
        assert builder.include_cards == []
        assert builder.exclude_cards == []
        assert builder.enforcement_mode == "warn"
        assert builder.allow_illegal is False
        assert builder.fuzzy_matching is True
        assert builder.include_exclude_diagnostics is None
    
    def test_field_assignment(self):
        """Test that include/exclude fields can be assigned."""
        builder = DeckBuilder()
        
        builder.include_cards = ["Sol Ring", "Lightning Bolt"]
        builder.exclude_cards = ["Chaos Orb", "Shaharazad"]
        builder.enforcement_mode = "strict"
        builder.allow_illegal = True
        builder.fuzzy_matching = False
        
        assert builder.include_cards == ["Sol Ring", "Lightning Bolt"]
        assert builder.exclude_cards == ["Chaos Orb", "Shaharazad"]
        assert builder.enforcement_mode == "strict"
        assert builder.allow_illegal is True
        assert builder.fuzzy_matching is False


class TestProcessIncludesExcludes:
    """Test the _process_includes_excludes method."""
    
    def test_basic_processing(self):
        """Test basic include/exclude processing."""
        builder = DeckBuilder()
        builder.include_cards = ["Sol Ring", "Lightning Bolt"]
        builder.exclude_cards = ["Chaos Orb"]
        
        # Mock output function to capture messages
        output_messages = []
        builder.output_func = lambda msg: output_messages.append(msg)
        
        diagnostics = builder._process_includes_excludes()
        
        assert isinstance(diagnostics, IncludeExcludeDiagnostics)
        assert builder.include_exclude_diagnostics is not None
    
    def test_duplicate_collapse(self):
        """Test that duplicates are properly collapsed."""
        builder = DeckBuilder()
        builder.include_cards = ["Sol Ring", "Sol Ring", "Lightning Bolt"]
        builder.exclude_cards = ["Chaos Orb", "Chaos Orb", "Chaos Orb"]
        
        output_messages = []
        builder.output_func = lambda msg: output_messages.append(msg)
        
        diagnostics = builder._process_includes_excludes()
        
        # After processing, duplicates should be removed
        assert builder.include_cards == ["Sol Ring", "Lightning Bolt"]
        assert builder.exclude_cards == ["Chaos Orb"]
        
        # Duplicates should be tracked in diagnostics
        assert diagnostics.duplicates_collapsed["Sol Ring"] == 2
        assert diagnostics.duplicates_collapsed["Chaos Orb"] == 3
    
    def test_exclude_overrides_include(self):
        """Test that exclude takes precedence over include."""
        builder = DeckBuilder()
        builder.include_cards = ["Sol Ring", "Lightning Bolt"]
        builder.exclude_cards = ["Sol Ring"]  # Sol Ring appears in both lists
        
        output_messages = []
        builder.output_func = lambda msg: output_messages.append(msg)
        
        diagnostics = builder._process_includes_excludes()
        
        # Sol Ring should be removed from includes due to exclude precedence
        assert "Sol Ring" not in builder.include_cards
        assert "Lightning Bolt" in builder.include_cards
        assert "Sol Ring" in diagnostics.excluded_removed


class TestValidationUtilities:
    """Test the validation utility functions."""
    
    def test_list_size_validation_valid(self):
        """Test list size validation with valid sizes."""
        includes = ["Card A", "Card B"]
        excludes = ["Card X", "Card Y", "Card Z"]
        
        result = validate_list_sizes(includes, excludes)
        
        assert result['valid'] is True
        assert len(result['errors']) == 0
        assert result['counts']['includes'] == 2
        assert result['counts']['excludes'] == 3
    
    def test_list_size_validation_approaching_limit(self):
        """Test list size validation warnings when approaching limits."""
        includes = ["Card"] * 8  # 80% of 10 = 8
        excludes = ["Card"] * 12  # 80% of 15 = 12
        
        result = validate_list_sizes(includes, excludes)
        
        assert result['valid'] is True  # Still valid, just warnings
        assert 'includes_approaching_limit' in result['warnings']
        assert 'excludes_approaching_limit' in result['warnings']
    
    def test_list_size_validation_over_limit(self):
        """Test list size validation errors when over limits."""
        includes = ["Card"] * 15  # Over limit of 10
        excludes = ["Card"] * 20  # Over limit of 15
        
        result = validate_list_sizes(includes, excludes)
        
        assert result['valid'] is False
        assert len(result['errors']) == 2
        assert "Too many include cards" in result['errors'][0]
        assert "Too many exclude cards" in result['errors'][1]
    
    def test_collapse_duplicates(self):
        """Test duplicate collapse functionality."""
        card_names = ["Sol Ring", "Lightning Bolt", "Sol Ring", "Counterspell", "Lightning Bolt", "Lightning Bolt"]
        
        unique_names, duplicates = collapse_duplicates(card_names)
        
        assert len(unique_names) == 3
        assert "Sol Ring" in unique_names
        assert "Lightning Bolt" in unique_names
        assert "Counterspell" in unique_names
        
        assert duplicates["Sol Ring"] == 2
        assert duplicates["Lightning Bolt"] == 3
        assert "Counterspell" not in duplicates  # Only appeared once
    
    def test_parse_card_list_input_newlines(self):
        """Test parsing card list input with newlines."""
        input_text = "Sol Ring\nLightning Bolt\nCounterspell"
        
        result = parse_card_list_input(input_text)
        
        assert result == ["Sol Ring", "Lightning Bolt", "Counterspell"]
    
    def test_parse_card_list_input_commas(self):
        """Test parsing card list input with commas (when no newlines)."""
        input_text = "Sol Ring, Lightning Bolt, Counterspell"
        
        result = parse_card_list_input(input_text)
        
        assert result == ["Sol Ring", "Lightning Bolt", "Counterspell"]
    
    def test_parse_card_list_input_mixed_prefers_newlines(self):
        """Test that newlines take precedence over commas to avoid splitting names with commas."""
        input_text = "Sol Ring\nKrenko, Mob Boss\nLightning Bolt"
        
        result = parse_card_list_input(input_text)
        
        # Should not split "Krenko, Mob Boss" because newlines are present
        assert result == ["Sol Ring", "Krenko, Mob Boss", "Lightning Bolt"]


class TestStrictEnforcement:
    """Test strict enforcement functionality."""
    
    def test_strict_enforcement_with_missing_includes(self):
        """Test that strict mode raises error when includes are missing."""
        builder = DeckBuilder()
        builder.enforcement_mode = "strict"
        builder.include_exclude_diagnostics = {
            'missing_includes': ['Missing Card'],
            'ignored_color_identity': [],
            'illegal_dropped': [],
            'illegal_allowed': [],
            'excluded_removed': [],
            'duplicates_collapsed': {},
            'include_added': [],
            'include_over_ideal': {},
            'fuzzy_corrections': {},
            'confirmation_needed': [],
            'list_size_warnings': {}
        }
        
        with pytest.raises(RuntimeError, match="Strict mode: Failed to include required cards: Missing Card"):
            builder._enforce_includes_strict()
    
    def test_strict_enforcement_with_no_missing_includes(self):
        """Test that strict mode passes when all includes are present."""
        builder = DeckBuilder()
        builder.enforcement_mode = "strict"
        builder.include_exclude_diagnostics = {
            'missing_includes': [],
            'ignored_color_identity': [],
            'illegal_dropped': [],
            'illegal_allowed': [],
            'excluded_removed': [],
            'duplicates_collapsed': {},
            'include_added': ['Sol Ring'],
            'include_over_ideal': {},
            'fuzzy_corrections': {},
            'confirmation_needed': [],
            'list_size_warnings': {}
        }
        
        # Should not raise any exception
        builder._enforce_includes_strict()
    
    def test_warn_mode_does_not_enforce(self):
        """Test that warn mode does not raise errors."""
        builder = DeckBuilder()
        builder.enforcement_mode = "warn"
        builder.include_exclude_diagnostics = {
            'missing_includes': ['Missing Card'],
        }
        
        # Should not raise any exception
        builder._enforce_includes_strict()


class TestJSONRoundTrip:
    """Test JSON export/import round-trip functionality."""
    
    def test_json_export_includes_new_fields(self):
        """Test that JSON export includes include/exclude fields."""
        builder = DeckBuilder()
        builder.include_cards = ["Sol Ring", "Lightning Bolt"]
        builder.exclude_cards = ["Chaos Orb"]
        builder.enforcement_mode = "strict"
        builder.allow_illegal = True
        builder.fuzzy_matching = False
        
        # Create temporary directory for export
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = builder.export_run_config_json(directory=temp_dir, suppress_output=True)
            
            # Read the exported JSON
            with open(json_path, 'r', encoding='utf-8') as f:
                exported_data = json.load(f)
            
            # Verify include/exclude fields are present
            assert exported_data['include_cards'] == ["Sol Ring", "Lightning Bolt"]
            assert exported_data['exclude_cards'] == ["Chaos Orb"]
            assert exported_data['enforcement_mode'] == "strict"
            assert exported_data['allow_illegal'] is True
            assert exported_data['fuzzy_matching'] is False
            assert exported_data['userThemes'] == []
            assert exported_data['themeCatalogVersion'] is None


if __name__ == "__main__":
    pytest.main([__file__])
