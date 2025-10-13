"""
Tests for protection grant detection (M2).

Tests the ability to distinguish between cards that grant protection
and cards that have inherent protection.
"""

import pytest
from code.tagging.protection_grant_detection import (
    is_granting_protection,
    categorize_protection_card
)


class TestGrantDetection:
    """Test grant verb detection."""
    
    def test_gains_hexproof(self):
        """Cards with 'gains hexproof' should be detected as granting."""
        text = "Target creature gains hexproof until end of turn."
        assert is_granting_protection(text, "")
    
    def test_gives_indestructible(self):
        """Cards with 'gives indestructible' should be detected as granting."""
        text = "This creature gives target creature indestructible."
        assert is_granting_protection(text, "")
    
    def test_creatures_you_control_have(self):
        """Mass grant pattern should be detected."""
        text = "Creatures you control have hexproof."
        assert is_granting_protection(text, "")
    
    def test_equipped_creature_gets(self):
        """Equipment grant pattern should be detected."""
        text = "Equipped creature gets +2/+2 and has indestructible."
        assert is_granting_protection(text, "")


class TestInherentDetection:
    """Test inherent protection detection."""
    
    def test_creature_with_hexproof_keyword(self):
        """Creature with hexproof keyword should not be detected as granting."""
        text = "Hexproof (This creature can't be the target of spells or abilities.)"
        keywords = "Hexproof"
        assert not is_granting_protection(text, keywords)
    
    def test_indestructible_artifact(self):
        """Artifact with indestructible keyword should not be detected as granting."""
        text = "Indestructible"
        keywords = "Indestructible"
        assert not is_granting_protection(text, keywords)
    
    def test_ward_creature(self):
        """Creature with Ward should not be detected as granting (unless it grants to others)."""
        text = "Ward {2}"
        keywords = "Ward"
        assert not is_granting_protection(text, keywords)


class TestMixedCases:
    """Test cards that both grant and have protection."""
    
    def test_creature_with_self_grant(self):
        """Creature that grants itself protection should be detected."""
        text = "This creature gains indestructible until end of turn."
        keywords = ""
        assert is_granting_protection(text, keywords)
    
    def test_equipment_with_inherent_and_grant(self):
        """Equipment with indestructible that grants protection."""
        text = "Indestructible. Equipped creature has hexproof."
        keywords = "Indestructible"
        # Should be detected as granting because of "has hexproof"
        assert is_granting_protection(text, keywords)


class TestExclusions:
    """Test exclusion patterns."""
    
    def test_cant_have_hexproof(self):
        """Cards that prevent protection should not be tagged."""
        text = "Creatures your opponents control can't have hexproof."
        assert not is_granting_protection(text, "")
    
    def test_loses_indestructible(self):
        """Cards that remove protection should not be tagged."""
        text = "Target creature loses indestructible until end of turn."
        assert not is_granting_protection(text, "")


class TestEdgeCases:
    """Test edge cases and special patterns."""
    
    def test_protection_from_color(self):
        """Protection from [quality] in keywords without grant text."""
        text = "Protection from red"
        keywords = "Protection from red"
        assert not is_granting_protection(text, keywords)
    
    def test_empty_text(self):
        """Empty text should return False."""
        assert not is_granting_protection("", "")
    
    def test_none_text(self):
        """None text should return False."""
        assert not is_granting_protection(None, "")


class TestCategorization:
    """Test full card categorization."""
    
    def test_shell_shield_is_grant(self):
        """Shell Shield grants hexproof - should be Grant."""
        text = "Target creature gets +0/+3 and gains hexproof until end of turn."
        cat = categorize_protection_card("Shell Shield", text, "", "Instant")
        assert cat == "Grant"
    
    def test_geist_of_saint_traft_is_mixed(self):
        """Geist has hexproof and creates tokens - Mixed."""
        text = "Hexproof. Whenever this attacks, create a token."
        keywords = "Hexproof"
        cat = categorize_protection_card("Geist", text, keywords, "Creature")
        # Has hexproof keyword, so inherent
        assert cat in ("Inherent", "Mixed")
    
    def test_darksteel_brute_is_inherent(self):
        """Darksteel Brute has indestructible - should be Inherent."""
        text = "Indestructible"
        keywords = "Indestructible"
        cat = categorize_protection_card("Darksteel Brute", text, keywords, "Artifact")
        assert cat == "Inherent"
    
    def test_scion_of_oona_is_grant(self):
        """Scion of Oona grants shroud to other faeries - should be Grant."""
        text = "Other Faeries you control have shroud."
        keywords = "Flying, Flash"
        cat = categorize_protection_card("Scion of Oona", text, keywords, "Creature")
        assert cat == "Grant"


class TestRealWorldCards:
    """Test against actual card samples from baseline audit."""
    
    def test_bulwark_ox(self):
        """Bulwark Ox - grants hexproof and indestructible."""
        text = "Sacrifice: Creatures you control with counters gain hexproof and indestructible"
        assert is_granting_protection(text, "")
    
    def test_bloodsworn_squire(self):
        """Bloodsworn Squire - grants itself indestructible."""
        text = "This creature gains indestructible until end of turn"
        assert is_granting_protection(text, "")
    
    def test_kaldra_compleat(self):
        """Kaldra Compleat - equipment with indestructible that grants."""
        text = "Indestructible. Equipped creature gets +5/+5 and has indestructible"
        keywords = "Indestructible"
        assert is_granting_protection(text, keywords)
    
    def test_ward_sliver(self):
        """Ward Sliver - grants protection to all slivers."""
        text = "All Slivers have protection from the chosen color"
        assert is_granting_protection(text, "")
    
    def test_rebbec(self):
        """Rebbec - grants protection to artifacts."""
        text = "Artifacts you control have protection from each mana value"
        assert is_granting_protection(text, "")
