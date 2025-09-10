"""
Tests for exclude re-entry prevention (M2).

Tests that excluded cards cannot re-enter the deck through downstream
heuristics or additional card addition calls.
"""

import unittest
from unittest.mock import Mock
import pandas as pd
from typing import List

from deck_builder.builder import DeckBuilder


class TestExcludeReentryPrevention(unittest.TestCase):
    """Test that excluded cards cannot re-enter the deck."""

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
                'name': 'Counterspell',
                'type': 'Instant',
                'mana_cost': '{U}{U}',
                'manaValue': 2,
                'themeTags': ['counterspell'],
                'colorIdentity': ['U']
            },
            {
                'name': 'Llanowar Elves',
                'type': 'Creature — Elf Druid',
                'mana_cost': '{G}',
                'manaValue': 1,
                'themeTags': ['ramp', 'elves'],
                'colorIdentity': ['G'],
                'creatureTypes': ['Elf', 'Druid']
            }
        ])

    def _create_test_builder(self, exclude_cards: List[str] = None) -> DeckBuilder:
        """Create a DeckBuilder instance for testing."""
        builder = DeckBuilder(
            input_func=self.mock_input,
            output_func=self.mock_output,
            log_outputs=False,
            headless=True
        )
        
        # Set up basic configuration
        builder.color_identity = ['R', 'G', 'U']
        builder.color_identity_key = 'R, G, U'
        builder._combined_cards_df = self.test_cards_df.copy()
        builder._full_cards_df = self.test_cards_df.copy()
        
        # Set exclude cards
        builder.exclude_cards = exclude_cards or []
        
        return builder

    def test_exclude_prevents_direct_add_card(self):
        """Test that excluded cards are prevented from being added directly."""
        builder = self._create_test_builder(exclude_cards=['Lightning Bolt', 'Sol Ring'])
        
        # Try to add excluded cards directly
        builder.add_card('Lightning Bolt', card_type='Instant')
        builder.add_card('Sol Ring', card_type='Artifact')
        
        # Verify excluded cards were not added
        self.assertNotIn('Lightning Bolt', builder.card_library)
        self.assertNotIn('Sol Ring', builder.card_library)

    def test_exclude_allows_non_excluded_cards(self):
        """Test that non-excluded cards can still be added normally."""
        builder = self._create_test_builder(exclude_cards=['Lightning Bolt'])
        
        # Add a non-excluded card
        builder.add_card('Sol Ring', card_type='Artifact')
        builder.add_card('Counterspell', card_type='Instant')
        
        # Verify non-excluded cards were added
        self.assertIn('Sol Ring', builder.card_library)
        self.assertIn('Counterspell', builder.card_library)

    def test_exclude_prevention_with_fuzzy_matching(self):
        """Test that exclude prevention works with normalized card names."""
        # Test variations in card name formatting
        builder = self._create_test_builder(exclude_cards=['lightning bolt'])  # lowercase
        
        # Try to add with different casing/formatting
        builder.add_card('Lightning Bolt', card_type='Instant')  # proper case
        builder.add_card('LIGHTNING BOLT', card_type='Instant')  # uppercase
        
        # All should be prevented
        self.assertNotIn('Lightning Bolt', builder.card_library)
        self.assertNotIn('LIGHTNING BOLT', builder.card_library)

    def test_exclude_prevention_with_punctuation_variations(self):
        """Test exclude prevention with punctuation variations."""
        # Create test data with punctuation
        test_df = pd.DataFrame([
            {
                'name': 'Krenko, Mob Boss',
                'type': 'Legendary Creature — Goblin Warrior',
                'mana_cost': '{2}{R}{R}',
                'manaValue': 4,
                'themeTags': ['goblins'],
                'colorIdentity': ['R']
            }
        ])
        
        builder = self._create_test_builder(exclude_cards=['Krenko Mob Boss'])  # no comma
        builder._combined_cards_df = test_df
        builder._full_cards_df = test_df
        
        # Try to add with comma (should be prevented due to normalization)
        builder.add_card('Krenko, Mob Boss', card_type='Legendary Creature — Goblin Warrior')
        
        # Should be prevented
        self.assertNotIn('Krenko, Mob Boss', builder.card_library)

    def test_commander_exemption_from_exclude_prevention(self):
        """Test that commanders are exempted from exclude prevention."""
        builder = self._create_test_builder(exclude_cards=['Lightning Bolt'])
        
        # Add Lightning Bolt as commander (should be allowed)
        builder.add_card('Lightning Bolt', card_type='Instant', is_commander=True)
        
        # Should be added despite being in exclude list
        self.assertIn('Lightning Bolt', builder.card_library)
        self.assertTrue(builder.card_library['Lightning Bolt']['Commander'])

    def test_exclude_reentry_prevention_during_phases(self):
        """Test that excluded cards cannot re-enter during creature/spell phases."""
        builder = self._create_test_builder(exclude_cards=['Llanowar Elves'])
        
        # Simulate a creature addition phase trying to add excluded creature
        # This would typically happen through automated heuristics
        builder.add_card('Llanowar Elves', card_type='Creature — Elf Druid', added_by='creature_phase')
        
        # Should be prevented
        self.assertNotIn('Llanowar Elves', builder.card_library)

    def test_exclude_prevention_with_empty_exclude_list(self):
        """Test that exclude prevention handles empty exclude lists gracefully."""
        builder = self._create_test_builder(exclude_cards=[])
        
        # Should allow normal addition
        builder.add_card('Lightning Bolt', card_type='Instant')
        
        # Should be added normally
        self.assertIn('Lightning Bolt', builder.card_library)

    def test_exclude_prevention_with_none_exclude_list(self):
        """Test that exclude prevention handles None exclude lists gracefully."""
        builder = self._create_test_builder()
        builder.exclude_cards = None  # Explicitly set to None
        
        # Should allow normal addition
        builder.add_card('Lightning Bolt', card_type='Instant')
        
        # Should be added normally
        self.assertIn('Lightning Bolt', builder.card_library)

    def test_multiple_exclude_attempts_logged(self):
        """Test that multiple attempts to add excluded cards are properly logged."""
        builder = self._create_test_builder(exclude_cards=['Sol Ring'])
        
        # Track log calls by mocking the logger
        with self.assertLogs('deck_builder.builder', level='INFO') as log_context:
            # Try to add excluded card multiple times
            builder.add_card('Sol Ring', card_type='Artifact', added_by='test1')
            builder.add_card('Sol Ring', card_type='Artifact', added_by='test2')
            builder.add_card('Sol Ring', card_type='Artifact', added_by='test3')
        
        # Verify card was not added
        self.assertNotIn('Sol Ring', builder.card_library)
        
        # Verify logging occurred
        log_messages = [record.message for record in log_context.records]
        prevent_logs = [msg for msg in log_messages if 'EXCLUDE_REENTRY_PREVENTED' in msg]
        self.assertEqual(len(prevent_logs), 3)  # Should log each prevention

    def test_exclude_prevention_maintains_deck_integrity(self):
        """Test that exclude prevention doesn't interfere with normal deck building."""
        builder = self._create_test_builder(exclude_cards=['Lightning Bolt'])
        
        # Add a mix of cards, some excluded, some not
        cards_to_add = [
            ('Lightning Bolt', 'Instant'),  # excluded
            ('Sol Ring', 'Artifact'),      # allowed
            ('Counterspell', 'Instant'),   # allowed
            ('Lightning Bolt', 'Instant'), # excluded (retry)
            ('Llanowar Elves', 'Creature — Elf Druid')  # allowed
        ]
        
        for name, card_type in cards_to_add:
            builder.add_card(name, card_type=card_type)
        
        # Verify only non-excluded cards were added
        expected_cards = {'Sol Ring', 'Counterspell', 'Llanowar Elves'}
        actual_cards = set(builder.card_library.keys())
        
        self.assertEqual(actual_cards, expected_cards)
        self.assertNotIn('Lightning Bolt', actual_cards)

    def test_exclude_prevention_works_after_pool_filtering(self):
        """Test that exclude prevention works even after pool filtering removes cards."""
        builder = self._create_test_builder(exclude_cards=['Lightning Bolt'])
        
        # Simulate setup_dataframes filtering (M0.5 implementation)
        # The card should already be filtered from the pool, but prevention should still work
        original_df = builder._combined_cards_df.copy()
        
        # Remove Lightning Bolt from pool (simulating M0.5 filtering)
        builder._combined_cards_df = original_df[original_df['name'] != 'Lightning Bolt']
        
        # Try to add it anyway (simulating downstream heuristic attempting to add)
        builder.add_card('Lightning Bolt', card_type='Instant')
        
        # Should still be prevented
        self.assertNotIn('Lightning Bolt', builder.card_library)


if __name__ == '__main__':
    unittest.main()
