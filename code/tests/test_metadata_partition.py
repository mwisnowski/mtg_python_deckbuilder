"""Tests for M3 metadata/theme tag partition functionality.

Tests cover:
- Tag classification (metadata vs theme)
- Column creation and data migration  
- Feature flag behavior
- Compatibility with missing columns
- CSV read/write with new schema
"""
import pandas as pd
import pytest
from code.tagging import tag_utils
from code.tagging.tagger import _apply_metadata_partition


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
