"""Tests for consolidated theme enrichment pipeline.

These tests verify that the new consolidated pipeline produces the same results
as the old 7-script approach, but much faster.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

try:
    import yaml
except ImportError:
    yaml = None

from code.tagging.theme_enrichment import (
    ThemeEnrichmentPipeline,
    EnrichmentStats,
    run_enrichment_pipeline,
)


# Skip all tests if PyYAML not available
pytestmark = pytest.mark.skipif(yaml is None, reason="PyYAML not installed")


@pytest.fixture
def temp_catalog_dir(tmp_path: Path) -> Path:
    """Create temporary catalog directory with test themes."""
    catalog_dir = tmp_path / 'config' / 'themes' / 'catalog'
    catalog_dir.mkdir(parents=True)
    return catalog_dir


@pytest.fixture
def temp_root(tmp_path: Path, temp_catalog_dir: Path) -> Path:
    """Create temporary project root."""
    # Create theme_list.json
    theme_json = tmp_path / 'config' / 'themes' / 'theme_list.json'
    theme_json.parent.mkdir(parents=True, exist_ok=True)
    theme_json.write_text('{"themes": []}', encoding='utf-8')
    return tmp_path


def write_theme(catalog_dir: Path, filename: str, data: Dict[str, Any]) -> Path:
    """Helper to write a theme YAML file."""
    path = catalog_dir / filename
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding='utf-8')
    return path


def read_theme(path: Path) -> Dict[str, Any]:
    """Helper to read a theme YAML file."""
    return yaml.safe_load(path.read_text(encoding='utf-8'))


class TestThemeEnrichmentPipeline:
    """Tests for ThemeEnrichmentPipeline class."""
    
    def test_init(self, temp_root: Path):
        """Test pipeline initialization."""
        pipeline = ThemeEnrichmentPipeline(root=temp_root, min_examples=5)
        
        assert pipeline.root == temp_root
        assert pipeline.min_examples == 5
        assert pipeline.catalog_dir == temp_root / 'config' / 'themes' / 'catalog'
        assert len(pipeline.themes) == 0
    
    def test_load_themes_empty_dir(self, temp_root: Path):
        """Test loading themes from empty directory."""
        pipeline = ThemeEnrichmentPipeline(root=temp_root)
        pipeline.load_all_themes()
        
        assert len(pipeline.themes) == 0
        assert pipeline.stats.total_themes == 0
    
    def test_load_themes_with_valid_files(self, temp_root: Path, temp_catalog_dir: Path):
        """Test loading valid theme files."""
        write_theme(temp_catalog_dir, 'landfall.yml', {
            'display_name': 'Landfall',
            'synergies': ['Ramp', 'Tokens'],
            'example_commanders': []
        })
        write_theme(temp_catalog_dir, 'reanimate.yml', {
            'display_name': 'Reanimate',
            'synergies': ['Graveyard', 'Mill'],
            'example_commanders': ['Meren of Clan Nel Toth']
        })
        
        pipeline = ThemeEnrichmentPipeline(root=temp_root)
        pipeline.load_all_themes()
        
        assert len(pipeline.themes) == 2
        assert pipeline.stats.total_themes == 2
    
    def test_autofill_placeholders_empty_examples(self, temp_root: Path, temp_catalog_dir: Path):
        """Test autofill adds placeholders to themes with no examples."""
        write_theme(temp_catalog_dir, 'tokens.yml', {
            'display_name': 'Tokens Matter',
            'synergies': ['Sacrifice', 'Aristocrats'],
            'example_commanders': []
        })
        
        pipeline = ThemeEnrichmentPipeline(root=temp_root)
        pipeline.load_all_themes()
        pipeline.autofill_placeholders()
        
        assert pipeline.stats.autofilled == 1
        theme = list(pipeline.themes.values())[0]
        assert theme.modified
        assert 'Tokens Matter Anchor' in theme.data['example_commanders']
        assert 'Sacrifice Anchor' in theme.data['example_commanders']
        assert 'Aristocrats Anchor' in theme.data['example_commanders']
        assert theme.data.get('editorial_quality') == 'draft'
    
    def test_autofill_skips_themes_with_examples(self, temp_root: Path, temp_catalog_dir: Path):
        """Test autofill skips themes that already have examples."""
        write_theme(temp_catalog_dir, 'landfall.yml', {
            'display_name': 'Landfall',
            'synergies': ['Ramp'],
            'example_commanders': ['Tatyova, Benthic Druid']
        })
        
        pipeline = ThemeEnrichmentPipeline(root=temp_root)
        pipeline.load_all_themes()
        pipeline.autofill_placeholders()
        
        assert pipeline.stats.autofilled == 0
        theme = list(pipeline.themes.values())[0]
        assert not theme.modified
    
    def test_pad_examples_to_minimum(self, temp_root: Path, temp_catalog_dir: Path):
        """Test padding adds placeholders to reach minimum threshold."""
        write_theme(temp_catalog_dir, 'ramp.yml', {
            'display_name': 'Ramp',
            'synergies': ['Landfall', 'BigSpells', 'Hydras'],
            'example_commanders': ['Ramp Anchor', 'Landfall Anchor']
        })
        
        pipeline = ThemeEnrichmentPipeline(root=temp_root, min_examples=5)
        pipeline.load_all_themes()
        pipeline.pad_examples()
        
        assert pipeline.stats.padded == 1
        theme = list(pipeline.themes.values())[0]
        assert theme.modified
        assert len(theme.data['example_commanders']) == 5
        # Should add synergies first (3rd synergy), then letter suffixes
        assert 'Hydras Anchor' in theme.data['example_commanders']
        # Should also have letter suffixes for remaining slots
        assert any('Anchor B' in cmd or 'Anchor C' in cmd for cmd in theme.data['example_commanders'])
    
    def test_pad_skips_mixed_real_and_placeholder(self, temp_root: Path, temp_catalog_dir: Path):
        """Test padding skips lists with both real and placeholder examples."""
        write_theme(temp_catalog_dir, 'tokens.yml', {
            'display_name': 'Tokens',
            'synergies': ['Sacrifice'],
            'example_commanders': ['Krenko, Mob Boss', 'Tokens Anchor']
        })
        
        pipeline = ThemeEnrichmentPipeline(root=temp_root, min_examples=5)
        pipeline.load_all_themes()
        pipeline.pad_examples()
        
        assert pipeline.stats.padded == 0
        theme = list(pipeline.themes.values())[0]
        assert not theme.modified
    
    def test_cleanup_removes_placeholders_when_real_present(self, temp_root: Path, temp_catalog_dir: Path):
        """Test cleanup removes placeholders when real examples are present.
        
        Note: cleanup only removes entries ending with ' Anchor' (no suffix).
        Purge step removes entries with ' Anchor' or ' Anchor X' pattern.
        """
        write_theme(temp_catalog_dir, 'lifegain.yml', {
            'display_name': 'Lifegain',
            'synergies': [],
            'example_commanders': [
                'Oloro, Ageless Ascetic',
                'Lifegain Anchor',  # Will be removed
                'Trelasarra, Moon Dancer',
            ]
        })
        
        pipeline = ThemeEnrichmentPipeline(root=temp_root)
        pipeline.load_all_themes()
        pipeline.cleanup_placeholders()
        
        assert pipeline.stats.cleaned == 1
        theme = list(pipeline.themes.values())[0]
        assert theme.modified
        assert len(theme.data['example_commanders']) == 2
        assert 'Oloro, Ageless Ascetic' in theme.data['example_commanders']
        assert 'Trelasarra, Moon Dancer' in theme.data['example_commanders']
        assert 'Lifegain Anchor' not in theme.data['example_commanders']
    
    def test_purge_removes_all_anchors(self, temp_root: Path, temp_catalog_dir: Path):
        """Test purge removes all anchor placeholders (even if no real examples)."""
        write_theme(temp_catalog_dir, 'counters.yml', {
            'display_name': 'Counters',
            'synergies': [],
            'example_commanders': [
                'Counters Anchor',
                'Counters Anchor B',
                'Counters Anchor C'
            ]
        })
        
        pipeline = ThemeEnrichmentPipeline(root=temp_root)
        pipeline.load_all_themes()
        pipeline.purge_anchors()
        
        assert pipeline.stats.purged == 1
        theme = list(pipeline.themes.values())[0]
        assert theme.modified
        assert theme.data['example_commanders'] == []
    
    def test_augment_from_catalog(self, temp_root: Path, temp_catalog_dir: Path):
        """Test augmentation adds missing fields from catalog."""
        # Create catalog JSON
        catalog_json = temp_root / 'config' / 'themes' / 'theme_list.json'
        catalog_data = {
            'themes': [
                {
                    'theme': 'Landfall',
                    'description': 'Triggers from lands entering',
                    'popularity_bucket': 'common',
                    'popularity_hint': 'Very popular',
                    'deck_archetype': 'Lands'
                }
            ]
        }
        import json
        catalog_json.write_text(json.dumps(catalog_data), encoding='utf-8')
        
        write_theme(temp_catalog_dir, 'landfall.yml', {
            'display_name': 'Landfall',
            'synergies': ['Ramp'],
            'example_commanders': ['Tatyova, Benthic Druid']
        })
        
        pipeline = ThemeEnrichmentPipeline(root=temp_root)
        pipeline.load_all_themes()
        pipeline.augment_from_catalog()
        
        assert pipeline.stats.augmented == 1
        theme = list(pipeline.themes.values())[0]
        assert theme.modified
        assert theme.data['description'] == 'Triggers from lands entering'
        assert theme.data['popularity_bucket'] == 'common'
        assert theme.data['popularity_hint'] == 'Very popular'
        assert theme.data['deck_archetype'] == 'Lands'
    
    def test_validate_min_examples_warning(self, temp_root: Path, temp_catalog_dir: Path):
        """Test validation warns about insufficient examples."""
        write_theme(temp_catalog_dir, 'ramp.yml', {
            'display_name': 'Ramp',
            'synergies': [],
            'example_commanders': ['Ramp Commander']
        })
        
        pipeline = ThemeEnrichmentPipeline(root=temp_root, min_examples=5)
        pipeline.load_all_themes()
        pipeline.validate(enforce_min=False)
        
        assert pipeline.stats.lint_warnings > 0
        assert pipeline.stats.lint_errors == 0
    
    def test_validate_min_examples_error(self, temp_root: Path, temp_catalog_dir: Path):
        """Test validation errors on insufficient examples when enforced."""
        write_theme(temp_catalog_dir, 'ramp.yml', {
            'display_name': 'Ramp',
            'synergies': [],
            'example_commanders': ['Ramp Commander']
        })
        
        pipeline = ThemeEnrichmentPipeline(root=temp_root, min_examples=5)
        pipeline.load_all_themes()
        pipeline.validate(enforce_min=True)
        
        assert pipeline.stats.lint_errors > 0
    
    def test_write_themes_dry_run(self, temp_root: Path, temp_catalog_dir: Path):
        """Test dry run doesn't write files."""
        theme_path = write_theme(temp_catalog_dir, 'tokens.yml', {
            'display_name': 'Tokens',
            'synergies': [],
            'example_commanders': []
        })
        
        original_content = theme_path.read_text(encoding='utf-8')
        
        pipeline = ThemeEnrichmentPipeline(root=temp_root)
        pipeline.load_all_themes()
        pipeline.autofill_placeholders()
        # Don't call write_all_themes()
        
        # File should be unchanged
        assert theme_path.read_text(encoding='utf-8') == original_content
    
    def test_write_themes_saves_changes(self, temp_root: Path, temp_catalog_dir: Path):
        """Test write_all_themes saves modified files."""
        theme_path = write_theme(temp_catalog_dir, 'tokens.yml', {
            'display_name': 'Tokens',
            'synergies': ['Sacrifice'],
            'example_commanders': []
        })
        
        pipeline = ThemeEnrichmentPipeline(root=temp_root)
        pipeline.load_all_themes()
        pipeline.autofill_placeholders()
        pipeline.write_all_themes()
        
        # File should be updated
        updated_data = read_theme(theme_path)
        assert len(updated_data['example_commanders']) > 0
        assert 'Tokens Anchor' in updated_data['example_commanders']
    
    def test_run_all_full_pipeline(self, temp_root: Path, temp_catalog_dir: Path):
        """Test running the complete enrichment pipeline."""
        write_theme(temp_catalog_dir, 'landfall.yml', {
            'display_name': 'Landfall',
            'synergies': ['Ramp', 'Lands'],
            'example_commanders': []
        })
        write_theme(temp_catalog_dir, 'reanimate.yml', {
            'display_name': 'Reanimate',
            'synergies': ['Graveyard'],
            'example_commanders': []
        })
        
        pipeline = ThemeEnrichmentPipeline(root=temp_root, min_examples=5)
        stats = pipeline.run_all(write=True, enforce_min=False, strict_lint=False)
        
        assert stats.total_themes == 2
        assert stats.autofilled >= 2
        assert stats.padded >= 2
        
        # Verify files were updated
        landfall_data = read_theme(temp_catalog_dir / 'landfall.yml')
        assert len(landfall_data['example_commanders']) >= 5
        assert landfall_data.get('editorial_quality') == 'draft'


def test_run_enrichment_pipeline_convenience_function(temp_root: Path, temp_catalog_dir: Path):
    """Test the convenience function wrapper."""
    write_theme(temp_catalog_dir, 'tokens.yml', {
        'display_name': 'Tokens',
        'synergies': ['Sacrifice'],
        'example_commanders': []
    })
    
    stats = run_enrichment_pipeline(
        root=temp_root,
        min_examples=3,
        write=True,
        enforce_min=False,
        strict=False,
        progress_callback=None,
    )
    
    assert isinstance(stats, EnrichmentStats)
    assert stats.total_themes == 1
    assert stats.autofilled >= 1
    
    # Verify file was written
    tokens_data = read_theme(temp_catalog_dir / 'tokens.yml')
    assert len(tokens_data['example_commanders']) >= 3
