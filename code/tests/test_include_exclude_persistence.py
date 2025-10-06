"""
Test JSON persistence functionality for include/exclude configuration.

Verifies that include/exclude configurations can be exported to JSON and then imported
back with full fidelity, supporting the persistence layer of the include/exclude system.
"""

import json
import hashlib
import tempfile
import os

import pytest

from headless_runner import _load_json_config
from deck_builder.builder import DeckBuilder


class TestJSONRoundTrip:
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


if __name__ == "__main__":
    pytest.main([__file__])
