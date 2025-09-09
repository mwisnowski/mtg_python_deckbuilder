"""
Integration test demonstrating M2 include/exclude engine integration.

Shows the complete flow: lands → includes → creatures/spells with 
proper exclusion and include injection.
"""

import unittest
from unittest.mock import Mock
import pandas as pd

from deck_builder.builder import DeckBuilder


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

    def test_include_over_ideal_tracking(self):
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


if __name__ == '__main__':
    unittest.main()
