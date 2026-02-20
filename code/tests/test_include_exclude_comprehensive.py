"""
Comprehensive tests for include/exclude card functionality.

This file consolidates tests from multiple source files:
- test_include_exclude_validation.py
- test_include_exclude_utils.py
- test_include_exclude_ordering.py
- test_include_exclude_persistence.py
- test_include_exclude_engine_integration.py

Tests cover: schema integration, validation utilities, fuzzy matching, ordering,
persistence (JSON import/export), engine integration, and strict enforcement.
"""

import pytest
import json
import tempfile
import hashlib
import os
import unittest
from unittest.mock import Mock
import pandas as pd
from typing import List, Set

from deck_builder.builder import DeckBuilder
from deck_builder.include_exclude_utils import (
    IncludeExcludeDiagnostics,
    validate_list_sizes,
    collapse_duplicates,
    parse_card_list_input,
    normalize_card_name,
    normalize_punctuation,
    fuzzy_match_card_name,
    get_baseline_performance_metrics,
    FuzzyMatchResult,
    FUZZY_CONFIDENCE_THRESHOLD,
    MAX_INCLUDES,
    MAX_EXCLUDES
)
from headless_runner import _load_json_config


# =============================================================================
# SECTION: Schema and Validation Tests
# Source: test_include_exclude_validation.py
# =============================================================================

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


# =============================================================================
# SECTION: Utility Function Tests
# Source: test_include_exclude_utils.py
# =============================================================================

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


# =============================================================================
# SECTION: Ordering and Injection Tests
# Source: test_include_exclude_ordering.py
# =============================================================================

class TestIncludeExcludeOrdering(unittest.TestCase):
    """Test ordering invariants and include injection logic."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock input/output functions to avoid interactive prompts
        self.mock_input = Mock(return_value="")
        self.mock_output = Mock()
        
        # Create test card data
        self.test_cards_df = pd.DataFrame([
            {
                'name': 'Lightning Bolt',
                'type': 'Instant',
                'mana_cost': '{R}',
                'manaValue': 1,
                'themeTags': ['burn'],
                'colorIdentity': ['R']
            },
            {
                'name': 'Sol Ring',
                'type': 'Artifact',
                'mana_cost': '{1}',
                'manaValue': 1,
                'themeTags': ['ramp'],
                'colorIdentity': []
            },
            {
                'name': 'Llanowar Elves',
                'type': 'Creature — Elf Druid',
                'mana_cost': '{G}',
                'manaValue': 1,
                'themeTags': ['ramp', 'elves'],
                'colorIdentity': ['G'],
                'creatureTypes': ['Elf', 'Druid']
            },
            {
                'name': 'Forest',
                'type': 'Basic Land — Forest',
                'mana_cost': '',
                'manaValue': 0,
                'themeTags': [],
                'colorIdentity': ['G']
            },
            {
                'name': 'Command Tower',
                'type': 'Land',
                'mana_cost': '',
                'manaValue': 0,
                'themeTags': [],
                'colorIdentity': []
            }
        ])

    def _create_test_builder(self, include_cards: List[str] = None, exclude_cards: List[str] = None) -> DeckBuilder:
        """Create a DeckBuilder instance for testing."""
        builder = DeckBuilder(
            input_func=self.mock_input,
            output_func=self.mock_output,
            log_outputs=False,
            headless=True
        )
        
        # Set up basic configuration
        builder.color_identity = ['R', 'G']
        builder.color_identity_key = 'R, G'
        builder._combined_cards_df = self.test_cards_df.copy()
        builder._full_cards_df = self.test_cards_df.copy()
        
        # Set include/exclude cards
        builder.include_cards = include_cards or []
        builder.exclude_cards = exclude_cards or []
        
        # Set ideal counts to small values for testing
        builder.ideal_counts = {
            'lands': 5,
            'creatures': 3,
            'ramp': 2,
            'removal': 1,
            'wipes': 1,
            'card_advantage': 1,
            'protection': 1
        }
        
        return builder

    def test_include_injection_happens_after_lands(self):
        """Test that includes are injected after lands are added."""
        builder = self._create_test_builder(include_cards=['Sol Ring', 'Lightning Bolt'])
        
        # Track the order of additions by patching add_card
        original_add_card = builder.add_card
        addition_order = []
        
        def track_add_card(card_name, **kwargs):
            addition_order.append({
                'name': card_name,
                'type': kwargs.get('card_type', ''),
                'added_by': kwargs.get('added_by', 'normal'),
                'role': kwargs.get('role', 'normal')
            })
            return original_add_card(card_name, **kwargs)
        
        builder.add_card = track_add_card
        
        # Mock the land building to add some lands
        def mock_run_land_steps():
            builder.add_card('Forest', card_type='Basic Land — Forest', added_by='land_phase')
            builder.add_card('Command Tower', card_type='Land', added_by='land_phase')
        
        builder._run_land_build_steps = mock_run_land_steps
        
        # Mock creature/spell phases to add some creatures/spells
        def mock_add_creatures():
            builder.add_card('Llanowar Elves', card_type='Creature — Elf Druid', added_by='creature_phase')
        
        def mock_add_spells():
            pass  # Lightning Bolt should already be added by includes
        
        builder.add_creatures_phase = mock_add_creatures
        builder.add_spells_phase = mock_add_spells
        
        # Run the injection process
        builder._inject_includes_after_lands()
        
        # Verify includes were added with correct metadata
        self.assertIn('Sol Ring', builder.card_library)
        self.assertIn('Lightning Bolt', builder.card_library)
        
        # Verify role marking
        self.assertEqual(builder.card_library['Sol Ring']['Role'], 'include')
        self.assertEqual(builder.card_library['Sol Ring']['AddedBy'], 'include_injection')
        self.assertEqual(builder.card_library['Lightning Bolt']['Role'], 'include')
        
        # Verify diagnostics
        self.assertIsNotNone(builder.include_exclude_diagnostics)
        include_added = builder.include_exclude_diagnostics.get('include_added', [])
        self.assertIn('Sol Ring', include_added)
        self.assertIn('Lightning Bolt', include_added)

    def test_ordering_invariant_lands_includes_rest(self):
        """Test the ordering invariant: lands -> includes -> creatures/spells."""
        builder = self._create_test_builder(include_cards=['Sol Ring'])
        
        # Track addition order with timestamps
        addition_log = []
        original_add_card = builder.add_card
        
        def log_add_card(card_name, **kwargs):
            phase = kwargs.get('added_by', 'unknown')
            addition_log.append((card_name, phase))
            return original_add_card(card_name, **kwargs)
        
        builder.add_card = log_add_card
        
        # Simulate the complete build process with phase tracking
        # 1. Lands phase
        builder.add_card('Forest', card_type='Basic Land — Forest', added_by='lands')
        
        # 2. Include injection phase
        builder._inject_includes_after_lands()
        
        # 3. Creatures phase  
        builder.add_card('Llanowar Elves', card_type='Creature — Elf Druid', added_by='creatures')
        
        # Verify ordering: lands -> includes -> creatures
        land_indices = [i for i, (name, phase) in enumerate(addition_log) if phase == 'lands']
        include_indices = [i for i, (name, phase) in enumerate(addition_log) if phase == 'include_injection']
        creature_indices = [i for i, (name, phase) in enumerate(addition_log) if phase == 'creatures']
        
        # Verify all lands come before all includes
        if land_indices and include_indices:
            self.assertLess(max(land_indices), min(include_indices), 
                          "All lands should be added before includes")
        
        # Verify all includes come before all creatures
        if include_indices and creature_indices:
            self.assertLess(max(include_indices), min(creature_indices),
                          "All includes should be added before creatures")

    def test_include_over_ideal_tracking(self):
        """Test that includes going over ideal counts are properly tracked."""
        builder = self._create_test_builder(include_cards=['Sol Ring', 'Lightning Bolt'])
        
        # Set very low ideal counts to trigger over-ideal
        builder.ideal_counts['creatures'] = 0  # Force any creature include to be over-ideal
        
        # Add a creature first to reach the limit
        builder.add_card('Llanowar Elves', card_type='Creature — Elf Druid')
        
        # Now inject includes - should detect over-ideal condition  
        builder._inject_includes_after_lands()
        
        # Verify over-ideal tracking
        self.assertIsNotNone(builder.include_exclude_diagnostics)
        over_ideal = builder.include_exclude_diagnostics.get('include_over_ideal', {})
        
        # Should track artifacts/instants appropriately based on categorization
        self.assertIsInstance(over_ideal, dict)

    def test_include_injection_skips_already_present_cards(self):
        """Test that include injection skips cards already in the library."""
        builder = self._create_test_builder(include_cards=['Sol Ring', 'Lightning Bolt'])
        
        # Pre-add one of the include cards
        builder.add_card('Sol Ring', card_type='Artifact')
        
        # Inject includes
        builder._inject_includes_after_lands()
        
        # Verify only the new card was added
        include_added = builder.include_exclude_diagnostics.get('include_added', [])
        self.assertEqual(len(include_added), 1)
        self.assertIn('Lightning Bolt', include_added)
        self.assertNotIn('Sol Ring', include_added)  # Should be skipped
        
        # Verify Sol Ring count didn't change (still 1)
        self.assertEqual(builder.card_library['Sol Ring']['Count'], 1)

    def test_include_injection_with_empty_include_list(self):
        """Test that include injection handles empty include lists gracefully."""
        builder = self._create_test_builder(include_cards=[])
        
        # Should complete without error
        builder._inject_includes_after_lands()
        
        # Should not create diagnostics for empty list
        if builder.include_exclude_diagnostics:
            include_added = builder.include_exclude_diagnostics.get('include_added', [])
            self.assertEqual(len(include_added), 0)

    def test_categorization_for_limits(self):
        """Test card categorization for ideal count tracking."""
        builder = self._create_test_builder()
        
        # Test various card type categorizations
        test_cases = [
            ('Creature — Human Wizard', 'creatures'),
            ('Instant', 'spells'),
            ('Sorcery', 'spells'),
            ('Artifact', 'spells'),
            ('Enchantment', 'spells'),
            ('Planeswalker', 'spells'),
            ('Land', 'lands'),
            ('Basic Land — Forest', 'lands'),
            ('Unknown Type', 'other'),
            ('', None)
        ]
        
        for card_type, expected_category in test_cases:
            with self.subTest(card_type=card_type):
                result = builder._categorize_card_for_limits(card_type)
                self.assertEqual(result, expected_category)

    def test_count_cards_in_category(self):
        """Test counting cards by category in the library."""
        builder = self._create_test_builder()
        
        # Add cards of different types
        builder.add_card('Lightning Bolt', card_type='Instant')
        builder.add_card('Llanowar Elves', card_type='Creature — Elf Druid')
        builder.add_card('Sol Ring', card_type='Artifact')
        builder.add_card('Forest', card_type='Basic Land — Forest')
        builder.add_card('Island', card_type='Basic Land — Island')  # Add multiple basics
        
        # Test category counts
        self.assertEqual(builder._count_cards_in_category('spells'), 2)  # Lightning Bolt + Sol Ring
        self.assertEqual(builder._count_cards_in_category('creatures'), 1)  # Llanowar Elves
        self.assertEqual(builder._count_cards_in_category('lands'), 2)  # Forest + Island
        self.assertEqual(builder._count_cards_in_category('other'), 0)  # None added
        self.assertEqual(builder._count_cards_in_category('nonexistent'), 0)  # Invalid category


# =============================================================================
# SECTION: Persistence Tests
# Source: test_include_exclude_persistence.py
# =============================================================================

class TestJSONPersistence:
    """Test complete JSON export/import round-trip for include/exclude config."""
    
    def test_complete_round_trip(self):
        """Test that a complete config can be exported and re-imported correctly."""
        # Create initial configuration
        original_config = {
            "commander": "Aang, Airbending Master",
            "primary_tag": "Exile Matters",
            "secondary_tag": "Airbending", 
            "tertiary_tag": "Token Creation",
            "bracket_level": 4,
            "use_multi_theme": True,
            "add_lands": True,
            "add_creatures": True,
            "add_non_creature_spells": True,
            "fetch_count": 3,
            "ideal_counts": {
                "ramp": 8,
                "lands": 35,
                "basic_lands": 15,
                "creatures": 25,
                "removal": 10,
                "wipes": 2,
                "card_advantage": 10,
                "protection": 8
            },
            "include_cards": ["Sol Ring", "Lightning Bolt", "Counterspell"],
            "exclude_cards": ["Chaos Orb", "Shahrazad", "Time Walk"],
            "enforcement_mode": "strict",
            "allow_illegal": True,
            "fuzzy_matching": False,
            "secondary_commander": "Alena, Kessig Trapper",
            "background": None,
            "enable_partner_mechanics": True,
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Write initial config
            config_path = os.path.join(temp_dir, "test_config.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(original_config, f, indent=2)
            
            # Load config using headless runner logic
            loaded_config = _load_json_config(config_path)
            
            # Verify all include/exclude fields are preserved
            assert loaded_config["include_cards"] == ["Sol Ring", "Lightning Bolt", "Counterspell"]
            assert loaded_config["exclude_cards"] == ["Chaos Orb", "Shahrazad", "Time Walk"]
            assert loaded_config["enforcement_mode"] == "strict"
            assert loaded_config["allow_illegal"] is True
            assert loaded_config["fuzzy_matching"] is False
            assert loaded_config["secondary_commander"] == "Alena, Kessig Trapper"
            assert loaded_config["background"] is None
            assert loaded_config["enable_partner_mechanics"] is True
            
            # Create a DeckBuilder with this config and export again
            builder = DeckBuilder()
            builder.commander_name = loaded_config["commander"]
            builder.include_cards = loaded_config["include_cards"]
            builder.exclude_cards = loaded_config["exclude_cards"]
            builder.enforcement_mode = loaded_config["enforcement_mode"]
            builder.allow_illegal = loaded_config["allow_illegal"]
            builder.fuzzy_matching = loaded_config["fuzzy_matching"]
            builder.bracket_level = loaded_config["bracket_level"]
            builder.partner_feature_enabled = loaded_config["enable_partner_mechanics"]
            builder.partner_mode = "partner"
            builder.secondary_commander = loaded_config["secondary_commander"]
            builder.requested_secondary_commander = loaded_config["secondary_commander"]
            
            # Export the configuration
            exported_path = builder.export_run_config_json(directory=temp_dir, suppress_output=True)
            
            # Load the exported config
            with open(exported_path, 'r', encoding='utf-8') as f:
                re_exported_config = json.load(f)
            
            # Verify round-trip fidelity for include/exclude fields
            assert re_exported_config["include_cards"] == ["Sol Ring", "Lightning Bolt", "Counterspell"]
            assert re_exported_config["exclude_cards"] == ["Chaos Orb", "Shahrazad", "Time Walk"]
            assert re_exported_config["enforcement_mode"] == "strict"
            assert re_exported_config["allow_illegal"] is True
            assert re_exported_config["fuzzy_matching"] is False
            assert re_exported_config["additional_themes"] == []
            assert re_exported_config["theme_match_mode"] == "permissive"
            assert re_exported_config["theme_catalog_version"] is None
            assert re_exported_config["userThemes"] == []
            assert re_exported_config["themeCatalogVersion"] is None
            assert re_exported_config["secondary_commander"] == "Alena, Kessig Trapper"
            assert re_exported_config["background"] is None
            assert re_exported_config["enable_partner_mechanics"] is True
    
    def test_empty_lists_round_trip(self):
        """Test that empty include/exclude lists are handled correctly."""
        builder = DeckBuilder()
        builder.commander_name = "Test Commander"
        builder.include_cards = []
        builder.exclude_cards = []
        builder.enforcement_mode = "warn"
        builder.allow_illegal = False
        builder.fuzzy_matching = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Export configuration
            exported_path = builder.export_run_config_json(directory=temp_dir, suppress_output=True)
            
            # Load the exported config
            with open(exported_path, 'r', encoding='utf-8') as f:
                exported_config = json.load(f)
            
            # Verify empty lists are preserved (not None)
            assert exported_config["include_cards"] == []
            assert exported_config["exclude_cards"] == []
            assert exported_config["enforcement_mode"] == "warn"
            assert exported_config["allow_illegal"] is False
            assert exported_config["fuzzy_matching"] is True
            assert exported_config["userThemes"] == []
            assert exported_config["themeCatalogVersion"] is None
            assert exported_config["secondary_commander"] is None
            assert exported_config["background"] is None
            assert exported_config["enable_partner_mechanics"] is False
    
    def test_default_values_export(self):
        """Test that default values are exported correctly."""
        builder = DeckBuilder()
        # Only set commander, leave everything else as defaults
        builder.commander_name = "Test Commander"
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Export configuration
            exported_path = builder.export_run_config_json(directory=temp_dir, suppress_output=True)
            
            # Load the exported config
            with open(exported_path, 'r', encoding='utf-8') as f:
                exported_config = json.load(f)
            
            # Verify default values are exported
            assert exported_config["include_cards"] == []
            assert exported_config["exclude_cards"] == []
            assert exported_config["enforcement_mode"] == "warn"
            assert exported_config["allow_illegal"] is False
            assert exported_config["fuzzy_matching"] is True
            assert exported_config["additional_themes"] == []
            assert exported_config["theme_match_mode"] == "permissive"
            assert exported_config["theme_catalog_version"] is None
            assert exported_config["secondary_commander"] is None
            assert exported_config["background"] is None
            assert exported_config["enable_partner_mechanics"] is False
    
    def test_backward_compatibility_no_include_exclude_fields(self):
        """Test that configs without include/exclude fields still work."""
        legacy_config = {
            "commander": "Legacy Commander",
            "primary_tag": "Legacy Tag",
            "bracket_level": 3,
            "ideal_counts": {
                "ramp": 8,
                "lands": 35
            }
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Write legacy config (no include/exclude fields)
            config_path = os.path.join(temp_dir, "legacy_config.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(legacy_config, f, indent=2)
            
            # Load config using headless runner logic
            loaded_config = _load_json_config(config_path)
            
            # Verify legacy fields are preserved
            assert loaded_config["commander"] == "Legacy Commander"
            assert loaded_config["primary_tag"] == "Legacy Tag"
            assert loaded_config["bracket_level"] == 3
            
            # Verify include/exclude fields are not present (will use defaults)
            assert "include_cards" not in loaded_config
            assert "exclude_cards" not in loaded_config
            assert "enforcement_mode" not in loaded_config
            assert "allow_illegal" not in loaded_config
            assert "fuzzy_matching" not in loaded_config
            assert "additional_themes" not in loaded_config
            assert "theme_match_mode" not in loaded_config
            assert "theme_catalog_version" not in loaded_config
            assert "userThemes" not in loaded_config
            assert "themeCatalogVersion" not in loaded_config

    def test_export_backward_compatibility_hash(self):
        """Ensure exports without user themes remain hash-compatible with legacy payload."""
        builder = DeckBuilder()
        builder.commander_name = "Test Commander"
        builder.include_cards = ["Sol Ring"]
        builder.exclude_cards = []
        builder.enforcement_mode = "warn"
        builder.allow_illegal = False
        builder.fuzzy_matching = True

        with tempfile.TemporaryDirectory() as temp_dir:
            exported_path = builder.export_run_config_json(directory=temp_dir, suppress_output=True)

            with open(exported_path, 'r', encoding='utf-8') as f:
                exported_config = json.load(f)

        legacy_expected = {
            "commander": "Test Commander",
            "primary_tag": None,
            "secondary_tag": None,
            "tertiary_tag": None,
            "bracket_level": None,
            "tag_mode": "AND",
            "use_multi_theme": True,
            "add_lands": True,
            "add_creatures": True,
            "add_non_creature_spells": True,
            "prefer_combos": False,
            "combo_target_count": None,
            "combo_balance": None,
            "include_cards": ["Sol Ring"],
            "exclude_cards": [],
            "enforcement_mode": "warn",
            "allow_illegal": False,
            "fuzzy_matching": True,
            "additional_themes": [],
            "theme_match_mode": "permissive",
            "theme_catalog_version": None,
            "fetch_count": None,
            "ideal_counts": {},
        }

        sanitized_payload = {k: exported_config.get(k) for k in legacy_expected.keys()}

        assert sanitized_payload == legacy_expected
        assert exported_config["userThemes"] == []
        assert exported_config["themeCatalogVersion"] is None

        legacy_hash = hashlib.sha256(json.dumps(legacy_expected, sort_keys=True).encode("utf-8")).hexdigest()
        sanitized_hash = hashlib.sha256(json.dumps(sanitized_payload, sort_keys=True).encode("utf-8")).hexdigest()
        assert sanitized_hash == legacy_hash

    def test_export_background_fields(self):
        """Test export with background commander fields."""
        builder = DeckBuilder()
        builder.commander_name = "Test Commander"
        builder.partner_feature_enabled = True
        builder.partner_mode = "background"
        builder.secondary_commander = "Scion of Halaster"
        builder.requested_background = "Scion of Halaster"

        with tempfile.TemporaryDirectory() as temp_dir:
            exported_path = builder.export_run_config_json(directory=temp_dir, suppress_output=True)

            with open(exported_path, 'r', encoding='utf-8') as f:
                exported_config = json.load(f)

        assert exported_config["enable_partner_mechanics"] is True
        assert exported_config["background"] == "Scion of Halaster"
        assert exported_config["secondary_commander"] is None


# =============================================================================
# SECTION: Engine Integration Tests
# Source: test_include_exclude_engine_integration.py
# =============================================================================

class TestM2Integration(unittest.TestCase):
    """Integration test for M2 include/exclude engine integration."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_input = Mock(return_value="")
        self.mock_output = Mock()
        
        # Create comprehensive test card data
        self.test_cards_df = pd.DataFrame([
            # Lands
            {'name': 'Forest', 'type': 'Basic Land — Forest', 'mana_cost': '', 'manaValue': 0, 'themeTags': [], 'colorIdentity': ['G']},
            {'name': 'Command Tower', 'type': 'Land', 'mana_cost': '', 'manaValue': 0, 'themeTags': [], 'colorIdentity': []},
            {'name': 'Sol Ring', 'type': 'Artifact', 'mana_cost': '{1}', 'manaValue': 1, 'themeTags': ['ramp'], 'colorIdentity': []},
            
            # Creatures
            {'name': 'Llanowar Elves', 'type': 'Creature — Elf Druid', 'mana_cost': '{G}', 'manaValue': 1, 'themeTags': ['ramp', 'elves'], 'colorIdentity': ['G']},
            {'name': 'Elvish Mystic', 'type': 'Creature — Elf Druid', 'mana_cost': '{G}', 'manaValue': 1, 'themeTags': ['ramp', 'elves'], 'colorIdentity': ['G']},
            {'name': 'Fyndhorn Elves', 'type': 'Creature — Elf Druid', 'mana_cost': '{G}', 'manaValue': 1, 'themeTags': ['ramp', 'elves'], 'colorIdentity': ['G']},
            
            # Spells
            {'name': 'Lightning Bolt', 'type': 'Instant', 'mana_cost': '{R}', 'manaValue': 1, 'themeTags': ['burn'], 'colorIdentity': ['R']},
            {'name': 'Counterspell', 'type': 'Instant', 'mana_cost': '{U}{U}', 'manaValue': 2, 'themeTags': ['counterspell'], 'colorIdentity': ['U']},
            {'name': 'Rampant Growth', 'type': 'Sorcery', 'mana_cost': '{1}{G}', 'manaValue': 2, 'themeTags': ['ramp'], 'colorIdentity': ['G']},
        ])

    def test_complete_m2_workflow(self):
        """Test the complete M2 workflow with includes, excludes, and proper ordering."""
        # Create builder with include/exclude configuration
        builder = DeckBuilder(
            input_func=self.mock_input,
            output_func=self.mock_output,
            log_outputs=False,
            headless=True
        )
        
        # Configure include/exclude lists
        builder.include_cards = ['Sol Ring', 'Lightning Bolt']  # Must include these
        builder.exclude_cards = ['Counterspell', 'Fyndhorn Elves']  # Must exclude these
        
        # Set up card pool
        builder.color_identity = ['R', 'G', 'U']
        builder._combined_cards_df = self.test_cards_df.copy()
        builder._full_cards_df = self.test_cards_df.copy()
        
        # Set small ideal counts for testing
        builder.ideal_counts = {
            'lands': 3,
            'creatures': 2,
            'spells': 2
        }
        
        # Track addition sequence
        addition_sequence = []
        original_add_card = builder.add_card
        
        def track_additions(card_name, **kwargs):
            addition_sequence.append({
                'name': card_name,
                'phase': kwargs.get('added_by', 'unknown'),
                'role': kwargs.get('role', 'normal')
            })
            return original_add_card(card_name, **kwargs)
        
        builder.add_card = track_additions
        
        # Simulate deck building phases
        
        # 1. Land phase
        builder.add_card('Forest', card_type='Basic Land — Forest', added_by='lands')
        builder.add_card('Command Tower', card_type='Land', added_by='lands')
        
        # 2. Include injection (M2)
        builder._inject_includes_after_lands()
        
        # 3. Creature phase
        builder.add_card('Llanowar Elves', card_type='Creature — Elf Druid', added_by='creatures')
        
        # 4. Try to add excluded cards (should be prevented)
        builder.add_card('Counterspell', card_type='Instant', added_by='spells')  # Should be blocked
        builder.add_card('Fyndhorn Elves', card_type='Creature — Elf Druid', added_by='creatures')  # Should be blocked
        
        # 5. Add allowed spell
        builder.add_card('Rampant Growth', card_type='Sorcery', added_by='spells')
        
        # Verify results
        
        # Check that includes were added
        self.assertIn('Sol Ring', builder.card_library)
        self.assertIn('Lightning Bolt', builder.card_library)
        
        # Check that includes have correct metadata
        self.assertEqual(builder.card_library['Sol Ring']['Role'], 'include')
        self.assertEqual(builder.card_library['Sol Ring']['AddedBy'], 'include_injection')
        self.assertEqual(builder.card_library['Lightning Bolt']['Role'], 'include')
        
        # Check that excludes were not added
        self.assertNotIn('Counterspell', builder.card_library)
        self.assertNotIn('Fyndhorn Elves', builder.card_library)
        
        # Check that normal cards were added
        self.assertIn('Forest', builder.card_library)
        self.assertIn('Command Tower', builder.card_library)
        self.assertIn('Llanowar Elves', builder.card_library)
        self.assertIn('Rampant Growth', builder.card_library)
        
        # Verify ordering: lands → includes → creatures/spells
        # Get indices in sequence
        land_indices = [i for i, entry in enumerate(addition_sequence) if entry['phase'] == 'lands']
        include_indices = [i for i, entry in enumerate(addition_sequence) if entry['phase'] == 'include_injection']
        creature_indices = [i for i, entry in enumerate(addition_sequence) if entry['phase'] == 'creatures']
        
        # Verify ordering
        if land_indices and include_indices:
            self.assertLess(max(land_indices), min(include_indices), "Lands should come before includes")
        if include_indices and creature_indices:
            self.assertLess(max(include_indices), min(creature_indices), "Includes should come before creatures")
        
        # Verify diagnostics
        self.assertIsNotNone(builder.include_exclude_diagnostics)
        include_added = builder.include_exclude_diagnostics.get('include_added', [])
        self.assertEqual(set(include_added), {'Sol Ring', 'Lightning Bolt'})
        
        # Verify final deck composition
        expected_final_cards = {
            'Forest', 'Command Tower',  # lands
            'Sol Ring', 'Lightning Bolt',  # includes
            'Llanowar Elves',  # creatures
            'Rampant Growth'  # spells
        }
        self.assertEqual(set(builder.card_library.keys()), expected_final_cards)

    def test_include_over_ideal_tracking_from_engine(self):
        """Test that includes going over ideal counts are properly tracked."""
        builder = DeckBuilder(
            input_func=self.mock_input,
            output_func=self.mock_output,
            log_outputs=False,
            headless=True
        )
        
        # Configure to force over-ideal situation
        builder.include_cards = ['Sol Ring', 'Lightning Bolt']  # 2 includes
        builder.exclude_cards = []
        
        builder.color_identity = ['R', 'G']
        builder._combined_cards_df = self.test_cards_df.copy()
        builder._full_cards_df = self.test_cards_df.copy()
        
        # Set very low ideal counts to trigger over-ideal
        builder.ideal_counts = {
            'spells': 1  # Only 1 spell allowed, but we're including 2
        }
        
        # Inject includes
        builder._inject_includes_after_lands()
        
        # Verify over-ideal tracking
        self.assertIsNotNone(builder.include_exclude_diagnostics)
        over_ideal = builder.include_exclude_diagnostics.get('include_over_ideal', {})
        
        # Both Sol Ring and Lightning Bolt are categorized as 'spells'
        self.assertIn('spells', over_ideal)
        # At least one should be tracked as over-ideal
        self.assertTrue(len(over_ideal['spells']) > 0)


if __name__ == "__main__":
    pytest.main([__file__])
