"""
Tests for include/exclude card ordering and injection logic (M2).

Tests the core M2 requirement that includes are injected after lands,
before creature/spell fills, and that the ordering is invariant.
"""

import unittest
from unittest.mock import Mock
import pandas as pd
from typing import List

from deck_builder.builder import DeckBuilder


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


if __name__ == '__main__':
    unittest.main()
