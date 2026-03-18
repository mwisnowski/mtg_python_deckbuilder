"""Tests for validation framework (models, validators, card names)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from code.web.validation.models import (
    BuildRequest,
    CommanderSearchRequest,
    ThemeValidationRequest,
    OwnedCardsImportRequest,
    BatchBuildRequest,
    CardReplacementRequest,
    PowerBracket,
    OwnedMode,
    CommanderPartnerType,
)
from code.web.validation.card_names import CardNameValidator
from code.web.validation.validators import (
    ThemeValidator,
    PowerBracketValidator,
    ColorIdentityValidator,
)
from code.web.validation.messages import ValidationMessages, MSG


class TestBuildRequest:
    """Test BuildRequest Pydantic model."""
    
    def test_minimal_valid_request(self):
        """Test minimal valid build request."""
        req = BuildRequest(commander="Atraxa, Praetors' Voice")
        
        assert req.commander == "Atraxa, Praetors' Voice"
        assert req.themes == []
        assert req.power_bracket == PowerBracket.BRACKET_2
        assert req.owned_mode == OwnedMode.OFF
    
    def test_full_valid_request(self):
        """Test fully populated build request."""
        req = BuildRequest(
            commander="Kess, Dissident Mage",
            themes=["Spellslinger", "Graveyard"],
            power_bracket=PowerBracket.BRACKET_3,
            owned_mode=OwnedMode.PREFER,
            must_include=["Counterspell", "Lightning Bolt"],
            must_exclude=["Armageddon"]
        )
        
        assert req.commander == "Kess, Dissident Mage"
        assert len(req.themes) == 2
        assert req.power_bracket == PowerBracket.BRACKET_3
        assert len(req.must_include) == 2
    
    def test_commander_whitespace_stripped(self):
        """Test commander name whitespace is stripped."""
        req = BuildRequest(commander="  Atraxa  ")
        assert req.commander == "Atraxa"
    
    def test_commander_empty_fails(self):
        """Test empty commander name fails validation."""
        with pytest.raises(ValidationError):
            BuildRequest(commander="")
        
        with pytest.raises(ValidationError):
            BuildRequest(commander="   ")
    
    def test_themes_deduplicated(self):
        """Test themes are deduplicated case-insensitively."""
        req = BuildRequest(
            commander="Test",
            themes=["Spellslinger", "spellslinger", "SPELLSLINGER", "Tokens"]
        )
        
        assert len(req.themes) == 2
        assert "Spellslinger" in req.themes
        assert "Tokens" in req.themes
    
    def test_partner_validation_requires_name(self):
        """Test partner mode requires partner name."""
        with pytest.raises(ValidationError, match="Partner mode requires partner_name"):
            BuildRequest(
                commander="Kydele, Chosen of Kruphix",
                partner_mode=CommanderPartnerType.PARTNER
            )
    
    def test_partner_valid_with_name(self):
        """Test partner mode valid with name."""
        req = BuildRequest(
            commander="Kydele, Chosen of Kruphix",
            partner_mode=CommanderPartnerType.PARTNER,
            partner_name="Thrasios, Triton Hero"
        )
        
        assert req.partner_mode == CommanderPartnerType.PARTNER
        assert req.partner_name == "Thrasios, Triton Hero"
    
    def test_background_requires_name(self):
        """Test background mode requires background name."""
        with pytest.raises(ValidationError, match="Background mode requires background_name"):
            BuildRequest(
                commander="Erinis, Gloom Stalker",
                partner_mode=CommanderPartnerType.BACKGROUND
            )
    
    def test_custom_theme_requires_both(self):
        """Test custom theme requires both name and tags."""
        with pytest.raises(ValidationError, match="Custom theme requires both name and tags"):
            BuildRequest(
                commander="Test",
                custom_theme_name="My Theme"
            )
        
        with pytest.raises(ValidationError, match="Custom theme tags require theme name"):
            BuildRequest(
                commander="Test",
                custom_theme_tags=["Tag1", "Tag2"]
            )


class TestCommanderSearchRequest:
    """Test CommanderSearchRequest model."""
    
    def test_valid_search(self):
        """Test valid search request."""
        req = CommanderSearchRequest(query="Atraxa")
        assert req.query == "Atraxa"
        assert req.limit == 10
    
    def test_custom_limit(self):
        """Test custom limit."""
        req = CommanderSearchRequest(query="Test", limit=25)
        assert req.limit == 25
    
    def test_empty_query_fails(self):
        """Test empty query fails."""
        with pytest.raises(ValidationError):
            CommanderSearchRequest(query="")
    
    def test_limit_bounds(self):
        """Test limit must be within bounds."""
        with pytest.raises(ValidationError):
            CommanderSearchRequest(query="Test", limit=0)
        
        with pytest.raises(ValidationError):
            CommanderSearchRequest(query="Test", limit=101)


class TestCardNameValidator:
    """Test card name validation and normalization."""
    
    def test_normalize_lowercase(self):
        """Test normalization converts to lowercase."""
        assert CardNameValidator.normalize("Atraxa, Praetors' Voice") == "atraxa, praetors' voice"
    
    def test_normalize_removes_diacritics(self):
        """Test normalization removes diacritics."""
        assert CardNameValidator.normalize("Dánitha Capashen") == "danitha capashen"
        assert CardNameValidator.normalize("Gisela, the Broken Blade") == "gisela, the broken blade"
    
    def test_normalize_standardizes_apostrophes(self):
        """Test normalization standardizes apostrophes."""
        assert CardNameValidator.normalize("Atraxa, Praetors' Voice") == CardNameValidator.normalize("Atraxa, Praetors' Voice")
        assert CardNameValidator.normalize("Atraxa, Praetors` Voice") == CardNameValidator.normalize("Atraxa, Praetors' Voice")
    
    def test_normalize_collapses_whitespace(self):
        """Test normalization collapses whitespace."""
        assert CardNameValidator.normalize("Test   Card") == "test card"
        assert CardNameValidator.normalize("  Test  ") == "test"
    
    def test_validator_caches_normalization(self):
        """Test validator caches normalized lookups."""
        validator = CardNameValidator()
        validator._card_names = {"Atraxa, Praetors' Voice"}
        validator._normalized_map = {
            "atraxa, praetors' voice": "Atraxa, Praetors' Voice"
        }
        validator._loaded = True
        
        # Should find exact match
        assert validator.is_valid("Atraxa, Praetors' Voice")


class TestThemeValidator:
    """Test theme validation."""
    
    def test_validate_themes_separates_valid_invalid(self):
        """Test validation separates valid from invalid themes."""
        validator = ThemeValidator()
        validator._themes = {"Spellslinger", "spellslinger", "Tokens", "tokens"}
        validator._loaded = True
        
        valid, invalid = validator.validate_themes(["Spellslinger", "Invalid", "Tokens"])
        
        assert "Spellslinger" in valid
        assert "Tokens" in valid
        assert "Invalid" in invalid


class TestPowerBracketValidator:
    """Test power bracket validation."""
    
    def test_valid_brackets(self):
        """Test valid bracket values (1-4)."""
        assert PowerBracketValidator.is_valid_bracket(1)
        assert PowerBracketValidator.is_valid_bracket(2)
        assert PowerBracketValidator.is_valid_bracket(3)
        assert PowerBracketValidator.is_valid_bracket(4)
    
    def test_invalid_brackets(self):
        """Test invalid bracket values."""
        assert not PowerBracketValidator.is_valid_bracket(0)
        assert not PowerBracketValidator.is_valid_bracket(5)
        assert not PowerBracketValidator.is_valid_bracket(-1)


class TestColorIdentityValidator:
    """Test color identity validation."""
    
    def test_parse_comma_separated(self):
        """Test parsing comma-separated colors."""
        colors = ColorIdentityValidator.parse_colors("W,U,B")
        assert colors == {"W", "U", "B"}
    
    def test_parse_concatenated(self):
        """Test parsing concatenated colors."""
        colors = ColorIdentityValidator.parse_colors("WUB")
        assert colors == {"W", "U", "B"}
    
    def test_parse_empty(self):
        """Test parsing empty string."""
        colors = ColorIdentityValidator.parse_colors("")
        assert colors == set()
    
    def test_colorless_subset_any(self):
        """Test colorless cards valid in any deck."""
        validator = ColorIdentityValidator()
        assert validator.is_subset({"C"}, {"W", "U"})
        assert validator.is_subset(set(), {"R", "G"})
    
    def test_subset_validation(self):
        """Test subset validation."""
        validator = ColorIdentityValidator()
        
        # Valid: card colors subset of commander
        assert validator.is_subset({"W", "U"}, {"W", "U", "B"})
        
        # Invalid: card has colors not in commander
        assert not validator.is_subset({"W", "U", "B"}, {"W", "U"})


class TestValidationMessages:
    """Test validation message formatting."""
    
    def test_format_commander_invalid(self):
        """Test commander invalid message formatting."""
        msg = MSG.format_commander_invalid("Test Commander")
        assert "Test Commander" in msg
        assert "not found" in msg
    
    def test_format_themes_invalid(self):
        """Test multiple invalid themes formatting."""
        msg = MSG.format_themes_invalid(["Theme1", "Theme2"])
        assert "Theme1" in msg
        assert "Theme2" in msg
    
    def test_format_bracket_exceeded(self):
        """Test bracket exceeded message formatting."""
        msg = MSG.format_bracket_exceeded("Mana Crypt", 4, 2)
        assert "Mana Crypt" in msg
        assert "4" in msg
        assert "2" in msg
    
    def test_format_color_mismatch(self):
        """Test color mismatch message formatting."""
        msg = MSG.format_color_mismatch("Card", "WUB", "WU")
        assert "Card" in msg
        assert "WUB" in msg
        assert "WU" in msg


class TestBatchBuildRequest:
    """Test batch build request validation."""
    
    def test_valid_batch(self):
        """Test valid batch request."""
        base = BuildRequest(commander="Test")
        req = BatchBuildRequest(base_config=base, count=5)
        
        assert req.count == 5
        assert req.base_config.commander == "Test"
    
    def test_count_limit(self):
        """Test batch count limit."""
        base = BuildRequest(commander="Test")
        
        with pytest.raises(ValidationError):
            BatchBuildRequest(base_config=base, count=11)


class TestCardReplacementRequest:
    """Test card replacement request validation."""
    
    def test_valid_replacement(self):
        """Test valid replacement request."""
        req = CardReplacementRequest(card_name="Sol Ring", reason="Too powerful")
        
        assert req.card_name == "Sol Ring"
        assert req.reason == "Too powerful"
    
    def test_whitespace_stripped(self):
        """Test whitespace is stripped."""
        req = CardReplacementRequest(card_name="  Sol Ring  ")
        assert req.card_name == "Sol Ring"
    
    def test_empty_name_fails(self):
        """Test empty card name fails."""
        with pytest.raises(ValidationError):
            CardReplacementRequest(card_name="")


class TestOwnedCardsImportRequest:
    """Test owned cards import validation."""
    
    def test_valid_import(self):
        """Test valid import request."""
        req = OwnedCardsImportRequest(format_type="csv", content="Name\nSol Ring\n")
        
        assert req.format_type == "csv"
        assert "Sol Ring" in req.content
    
    def test_invalid_format(self):
        """Test invalid format fails."""
        with pytest.raises(ValidationError):
            OwnedCardsImportRequest(format_type="invalid", content="test")
    
    def test_empty_content_fails(self):
        """Test empty content fails."""
        with pytest.raises(ValidationError):
            OwnedCardsImportRequest(format_type="csv", content="")
