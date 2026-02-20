"""Comprehensive Export and Metadata Functionality Tests

This file consolidates tests from three source files:
1. test_export_commander_metadata.py - Commander metadata in exports
2. test_export_mdfc_annotations.py - MDFC annotations in exports  
3. test_metadata_partition.py - Metadata/theme tag partition functionality

Created: 2026-02-20
Consolidation Purpose: Centralize all export and metadata-related tests

Total Tests: 21 (4 commander metadata + 2 MDFC + 15 metadata partition)
"""
from __future__ import annotations

import csv
from pathlib import Path
import sys
import types

import pandas as pd
import pytest

from code.deck_builder.combined_commander import CombinedCommander, PartnerMode
from code.deck_builder.phases.phase6_reporting import ReportingMixin
from code.tagging import tag_utils
from code.tagging.tagger import _apply_metadata_partition


# ============================================================================
# SECTION 1: COMMANDER METADATA EXPORT TESTS
# Source: test_export_commander_metadata.py
# Tests for commander metadata in CSV, text exports, and summaries
# ============================================================================


class MetadataBuilder(ReportingMixin):
    def __init__(self) -> None:
        self.card_library = {
            "Halana, Kessig Ranger": {
                "Card Type": "Legendary Creature",
                "Count": 1,
                "Mana Cost": "{3}{G}",
                "Mana Value": "4",
                "Role": "Commander",
                "Tags": ["Partner"],
            },
            "Alena, Kessig Trapper": {
                "Card Type": "Legendary Creature",
                "Count": 1,
                "Mana Cost": "{4}{R}",
                "Mana Value": "5",
                "Role": "Commander",
                "Tags": ["Partner"],
            },
            "Gruul Signet": {
                "Card Type": "Artifact",
                "Count": 1,
                "Mana Cost": "{2}",
                "Mana Value": "2",
                "Role": "Ramp",
                "Tags": [],
            },
        }
        self.output_func = lambda *_args, **_kwargs: None
        self.combined_commander = CombinedCommander(
            primary_name="Halana, Kessig Ranger",
            secondary_name="Alena, Kessig Trapper",
            partner_mode=PartnerMode.PARTNER,
            color_identity=("G", "R"),
            theme_tags=("counters", "aggro"),
            raw_tags_primary=("counters",),
            raw_tags_secondary=("aggro",),
            warnings=(),
        )
        self.commander_name = "Halana, Kessig Ranger"
        self.secondary_commander = "Alena, Kessig Trapper"
        self.partner_mode = PartnerMode.PARTNER
        self.combined_color_identity = ("G", "R")
        self.color_identity = ["G", "R"]
        self.selected_tags = ["Counters", "Aggro"]
        self.primary_tag = "Counters"
        self.secondary_tag = "Aggro"
        self.tertiary_tag = None
        self.custom_export_base = "metadata_builder"


def _suppress_color_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = types.ModuleType("deck_builder.builder_utils")
    stub.compute_color_source_matrix = lambda *_args, **_kwargs: {}
    stub.multi_face_land_info = lambda *_args, **_kwargs: {}
    monkeypatch.setitem(sys.modules, "deck_builder.builder_utils", stub)


def test_csv_header_includes_commander_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _suppress_color_matrix(monkeypatch)
    builder = MetadataBuilder()
    csv_path = Path(builder.export_decklist_csv(directory=str(tmp_path), filename="deck.csv"))
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None
        assert reader.fieldnames[-1] == "Commanders: Halana, Kessig Ranger, Alena, Kessig Trapper"
        rows = list(reader)
    assert any(row["Name"] == "Gruul Signet" for row in rows)


def test_text_export_includes_commander_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _suppress_color_matrix(monkeypatch)
    builder = MetadataBuilder()
    text_path = Path(builder.export_decklist_text(directory=str(tmp_path), filename="deck.txt"))
    lines = text_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# Commanders: Halana, Kessig Ranger, Alena, Kessig Trapper"
    assert lines[1] == "# Partner Mode: partner"
    assert lines[2] == "# Colors: G, R"
    assert lines[4].startswith("1 Halana, Kessig Ranger")


def test_summary_contains_combined_commander_block(monkeypatch: pytest.MonkeyPatch) -> None:
    _suppress_color_matrix(monkeypatch)
    builder = MetadataBuilder()
    summary = builder.build_deck_summary()
    commander_block = summary["commander"]
    assert commander_block["names"] == [
        "Halana, Kessig Ranger",
        "Alena, Kessig Trapper",
    ]
    assert commander_block["partner_mode"] == "partner"
    assert commander_block["color_identity"] == ["G", "R"]
    combined = commander_block["combined"]
    assert combined["primary_name"] == "Halana, Kessig Ranger"
    assert combined["secondary_name"] == "Alena, Kessig Trapper"
    assert combined["partner_mode"] == "partner"
    assert combined["color_identity"] == ["G", "R"]


# ============================================================================
# SECTION 2: MDFC ANNOTATION EXPORT TESTS
# Source: test_export_mdfc_annotations.py
# Tests for MDFC (Modal Double-Faced Card) annotations in CSV and text exports
# ============================================================================


class DummyBuilder(ReportingMixin):
    def __init__(self) -> None:
        self.card_library = {
            "Valakut Awakening // Valakut Stoneforge": {
                "Card Type": "Instant",
                "Count": 2,
                "Mana Cost": "{2}{R}",
                "Mana Value": "3",
                "Role": "",
                "Tags": [],
            },
            "Mountain": {
                "Card Type": "Land",
                "Count": 1,
                "Mana Cost": "",
                "Mana Value": "0",
                "Role": "",
                "Tags": [],
            },
        }
        self.color_identity = ["R"]
        self.output_func = lambda *_args, **_kwargs: None  # silence export logs
        self._full_cards_df = None
        self._combined_cards_df = None
        self.custom_export_base = "test_dfc_export"


@pytest.fixture()
def builder(monkeypatch: pytest.MonkeyPatch) -> DummyBuilder:
    matrix = {
        "Valakut Awakening // Valakut Stoneforge": {
            "R": 1,
            "_dfc_land": True,
            "_dfc_counts_as_extra": True,
        },
        "Mountain": {"R": 1},
    }

    def _fake_compute(card_library, *_args, **_kwargs):
        return matrix

    monkeypatch.setattr(
        "deck_builder.builder_utils.compute_color_source_matrix",
        _fake_compute,
    )
    return DummyBuilder()


def test_export_decklist_csv_includes_dfc_note(tmp_path: Path, builder: DummyBuilder) -> None:
    csv_path = Path(builder.export_decklist_csv(directory=str(tmp_path)))
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = {row["Name"]: row for row in reader}

    valakut_row = rows["Valakut Awakening // Valakut Stoneforge"]
    assert valakut_row["DFCNote"] == "MDFC: Adds extra land slot"

    mountain_row = rows["Mountain"]
    assert mountain_row["DFCNote"] == ""


def test_export_decklist_text_appends_dfc_annotation(tmp_path: Path, builder: DummyBuilder) -> None:
    text_path = Path(builder.export_decklist_text(directory=str(tmp_path)))
    lines = text_path.read_text(encoding="utf-8").splitlines()

    valakut_line = next(line for line in lines if line.startswith("2 Valakut Awakening"))
    assert "[MDFC: Adds extra land slot]" in valakut_line

    mountain_line = next(line for line in lines if line.strip().endswith("Mountain"))
    assert "MDFC" not in mountain_line


# ============================================================================
# SECTION 3: METADATA PARTITION TESTS
# Source: test_metadata_partition.py
# Tests for M3 metadata/theme tag partition functionality
# Covers: tag classification, column creation, feature flags, CSV compatibility
# ============================================================================


class TestTagClassification:
    """Tests for classify_tag function."""
    
    def test_prefix_based_metadata(self):
        """Metadata tags identified by prefix."""
        assert tag_utils.classify_tag("Applied: Cost Reduction") == "metadata"
        assert tag_utils.classify_tag("Bracket: Game Changer") == "metadata"
        assert tag_utils.classify_tag("Diagnostic: Test") == "metadata"
        assert tag_utils.classify_tag("Internal: Debug") == "metadata"
    
    def test_exact_match_metadata(self):
        """Metadata tags identified by exact match."""
        assert tag_utils.classify_tag("Bracket: Game Changer") == "metadata"
        assert tag_utils.classify_tag("Bracket: Staple") == "metadata"
    
    def test_kindred_protection_metadata(self):
        """Kindred protection tags are metadata."""
        assert tag_utils.classify_tag("Knights Gain Protection") == "metadata"
        assert tag_utils.classify_tag("Frogs Gain Protection") == "metadata"
        assert tag_utils.classify_tag("Zombies Gain Protection") == "metadata"
    
    def test_theme_classification(self):
        """Regular gameplay tags are themes."""
        assert tag_utils.classify_tag("Card Draw") == "theme"
        assert tag_utils.classify_tag("Spellslinger") == "theme"
        assert tag_utils.classify_tag("Tokens Matter") == "theme"
        assert tag_utils.classify_tag("Ramp") == "theme"
        assert tag_utils.classify_tag("Protection") == "theme"
    
    def test_edge_cases(self):
        """Edge cases in tag classification."""
        # Empty string
        assert tag_utils.classify_tag("") == "theme"
        
        # Similar but not exact matches
        assert tag_utils.classify_tag("Apply: Something") == "theme"  # Wrong prefix
        assert tag_utils.classify_tag("Knights Have Protection") == "theme"  # Not "Gain"
        
        # Case sensitivity
        assert tag_utils.classify_tag("applied: Cost Reduction") == "theme"  # Lowercase


class TestMetadataPartition:
    """Tests for _apply_metadata_partition function."""
    
    def test_basic_partition(self, monkeypatch):
        """Basic partition splits tags correctly."""
        monkeypatch.setenv('TAG_METADATA_SPLIT', '1')
        
        df = pd.DataFrame({
            'name': ['Card A', 'Card B'],
            'themeTags': [
                ['Card Draw', 'Applied: Cost Reduction'],
                ['Spellslinger', 'Bracket: Game Changer', 'Tokens Matter']
            ]
        })
        
        df_out, diag = _apply_metadata_partition(df)
        
        # Check theme tags
        assert df_out.loc[0, 'themeTags'] == ['Card Draw']
        assert df_out.loc[1, 'themeTags'] == ['Spellslinger', 'Tokens Matter']
        
        # Check metadata tags
        assert df_out.loc[0, 'metadataTags'] == ['Applied: Cost Reduction']
        assert df_out.loc[1, 'metadataTags'] == ['Bracket: Game Changer']
        
        # Check diagnostics
        assert diag['enabled'] is True
        assert diag['rows_with_tags'] == 2
        assert diag['metadata_tags_moved'] == 2
        assert diag['theme_tags_kept'] == 3
    
    def test_empty_tags(self, monkeypatch):
        """Handles empty tag lists."""
        monkeypatch.setenv('TAG_METADATA_SPLIT', '1')
        
        df = pd.DataFrame({
            'name': ['Card A', 'Card B'],
            'themeTags': [[], ['Card Draw']]
        })
        
        df_out, diag = _apply_metadata_partition(df)
        
        assert df_out.loc[0, 'themeTags'] == []
        assert df_out.loc[0, 'metadataTags'] == []
        assert df_out.loc[1, 'themeTags'] == ['Card Draw']
        assert df_out.loc[1, 'metadataTags'] == []
        
        assert diag['rows_with_tags'] == 1
    
    def test_all_metadata_tags(self, monkeypatch):
        """Handles rows with only metadata tags."""
        monkeypatch.setenv('TAG_METADATA_SPLIT', '1')
        
        df = pd.DataFrame({
            'name': ['Card A'],
            'themeTags': [['Applied: Cost Reduction', 'Bracket: Game Changer']]
        })
        
        df_out, diag = _apply_metadata_partition(df)
        
        assert df_out.loc[0, 'themeTags'] == []
        assert df_out.loc[0, 'metadataTags'] == ['Applied: Cost Reduction', 'Bracket: Game Changer']
        
        assert diag['metadata_tags_moved'] == 2
        assert diag['theme_tags_kept'] == 0
    
    def test_all_theme_tags(self, monkeypatch):
        """Handles rows with only theme tags."""
        monkeypatch.setenv('TAG_METADATA_SPLIT', '1')
        
        df = pd.DataFrame({
            'name': ['Card A'],
            'themeTags': [['Card Draw', 'Ramp', 'Spellslinger']]
        })
        
        df_out, diag = _apply_metadata_partition(df)
        
        assert df_out.loc[0, 'themeTags'] == ['Card Draw', 'Ramp', 'Spellslinger']
        assert df_out.loc[0, 'metadataTags'] == []
        
        assert diag['metadata_tags_moved'] == 0
        assert diag['theme_tags_kept'] == 3
    
    def test_feature_flag_disabled(self, monkeypatch):
        """Feature flag disables partition."""
        monkeypatch.setenv('TAG_METADATA_SPLIT', '0')
        
        df = pd.DataFrame({
            'name': ['Card A'],
            'themeTags': [['Card Draw', 'Applied: Cost Reduction']]
        })
        
        df_out, diag = _apply_metadata_partition(df)
        
        # Should not create metadataTags column
        assert 'metadataTags' not in df_out.columns
        
        # Should not modify themeTags
        assert df_out.loc[0, 'themeTags'] == ['Card Draw', 'Applied: Cost Reduction']
        
        # Should indicate disabled
        assert diag['enabled'] is False
    
    def test_missing_theme_tags_column(self, monkeypatch):
        """Handles missing themeTags column gracefully."""
        monkeypatch.setenv('TAG_METADATA_SPLIT', '1')
        
        df = pd.DataFrame({
            'name': ['Card A'],
            'other_column': ['value']
        })
        
        df_out, diag = _apply_metadata_partition(df)
        
        # Should return unchanged
        assert 'themeTags' not in df_out.columns
        assert 'metadataTags' not in df_out.columns
        
        # Should indicate error
        assert diag['enabled'] is True
        assert 'error' in diag
    
    def test_non_list_tags(self, monkeypatch):
        """Handles non-list values in themeTags."""
        monkeypatch.setenv('TAG_METADATA_SPLIT', '1')
        
        df = pd.DataFrame({
            'name': ['Card A', 'Card B', 'Card C'],
            'themeTags': [['Card Draw'], None, 'not a list']
        })
        
        df_out, diag = _apply_metadata_partition(df)
        
        # Only first row should be processed
        assert df_out.loc[0, 'themeTags'] == ['Card Draw']
        assert df_out.loc[0, 'metadataTags'] == []
        
        assert diag['rows_with_tags'] == 1
    
    def test_kindred_protection_partition(self, monkeypatch):
        """Kindred protection tags are moved to metadata."""
        monkeypatch.setenv('TAG_METADATA_SPLIT', '1')
        
        df = pd.DataFrame({
            'name': ['Card A'],
            'themeTags': [['Protection', 'Knights Gain Protection', 'Card Draw']]
        })
        
        df_out, diag = _apply_metadata_partition(df)
        
        assert 'Protection' in df_out.loc[0, 'themeTags']
        assert 'Card Draw' in df_out.loc[0, 'themeTags']
        assert 'Knights Gain Protection' in df_out.loc[0, 'metadataTags']
    
    def test_diagnostics_structure(self, monkeypatch):
        """Diagnostics contain expected fields."""
        monkeypatch.setenv('TAG_METADATA_SPLIT', '1')
        
        df = pd.DataFrame({
            'name': ['Card A'],
            'themeTags': [['Card Draw', 'Applied: Cost Reduction']]
        })
        
        df_out, diag = _apply_metadata_partition(df)
        
        # Check required diagnostic fields
        assert 'enabled' in diag
        assert 'total_rows' in diag
        assert 'rows_with_tags' in diag
        assert 'metadata_tags_moved' in diag
        assert 'theme_tags_kept' in diag
        assert 'unique_metadata_tags' in diag
        assert 'unique_theme_tags' in diag
        assert 'most_common_metadata' in diag
        assert 'most_common_themes' in diag
        
        # Check types
        assert isinstance(diag['most_common_metadata'], list)
        assert isinstance(diag['most_common_themes'], list)


class TestCSVCompatibility:
    """Tests for CSV read/write with new schema."""
    
    def test_csv_roundtrip_with_metadata(self, tmp_path, monkeypatch):
        """CSV roundtrip preserves both columns."""
        monkeypatch.setenv('TAG_METADATA_SPLIT', '1')
        
        csv_path = tmp_path / "test_cards.csv"
        
        # Create initial dataframe
        df = pd.DataFrame({
            'name': ['Card A'],
            'themeTags': [['Card Draw', 'Ramp']],
            'metadataTags': [['Applied: Cost Reduction']]
        })
        
        # Write to CSV
        df.to_csv(csv_path, index=False)
        
        # Read back
        df_read = pd.read_csv(
            csv_path,
            converters={'themeTags': pd.eval, 'metadataTags': pd.eval}
        )
        
        # Verify data preserved
        assert df_read.loc[0, 'themeTags'] == ['Card Draw', 'Ramp']
        assert df_read.loc[0, 'metadataTags'] == ['Applied: Cost Reduction']
    
    def test_csv_backward_compatible(self, tmp_path, monkeypatch):
        """Can read old CSVs without metadataTags."""
        monkeypatch.setenv('TAG_METADATA_SPLIT', '1')
        
        csv_path = tmp_path / "old_cards.csv"
        
        # Create old-style CSV without metadataTags
        df = pd.DataFrame({
            'name': ['Card A'],
            'themeTags': [['Card Draw', 'Applied: Cost Reduction']]
        })
        df.to_csv(csv_path, index=False)
        
        # Read back
        df_read = pd.read_csv(csv_path, converters={'themeTags': pd.eval})
        
        # Should read successfully
        assert 'themeTags' in df_read.columns
        assert 'metadataTags' not in df_read.columns
        assert df_read.loc[0, 'themeTags'] == ['Card Draw', 'Applied: Cost Reduction']
        
        # Apply partition
        df_partitioned, _ = _apply_metadata_partition(df_read)
        
        # Should now have both columns
        assert 'themeTags' in df_partitioned.columns
        assert 'metadataTags' in df_partitioned.columns
        assert df_partitioned.loc[0, 'themeTags'] == ['Card Draw']
        assert df_partitioned.loc[0, 'metadataTags'] == ['Applied: Cost Reduction']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
