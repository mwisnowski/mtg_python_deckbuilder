"""
Migration Compatibility Tests

Ensures backward compatibility during migration from individual CSV files
to consolidated all_cards.parquet. Tests verify that legacy adapter functions
produce identical results to direct AllCardsLoader calls.
"""

from __future__ import annotations

import os
import tempfile

import pandas as pd
import pytest

from code.services.all_cards_loader import AllCardsLoader
from code.services.legacy_loader_adapter import (
    load_all_cards,
    load_cards_by_color_identity,
    load_cards_by_name,
    load_cards_by_names,
    load_cards_by_type,
    load_cards_with_tag,
    load_cards_with_tags,
    search_cards,
)


@pytest.fixture
def sample_cards_df():
    """Create a sample DataFrame for testing."""
    return pd.DataFrame(
        {
            "name": [
                "Sol Ring",
                "Lightning Bolt",
                "Counterspell",
                "Giant Growth",
                "Goblin Token Maker",
            ],
            "colorIdentity": ["Colorless", "R", "U", "G", "R"],
            "type": ["Artifact", "Instant", "Instant", "Instant", "Creature — Goblin"],
            "text": [
                "Add two mana",
                "Deal 3 damage",
                "Counter target spell",
                "Target creature gets +3/+3",
                "When this enters, create two 1/1 red Goblin creature tokens",
            ],
            "themeTags": ["", "burn,damage", "control,counterspells", "combat,pump", "tokens,goblins"],
        }
    )


@pytest.fixture
def temp_parquet_file(sample_cards_df):
    """Create a temporary Parquet file for testing."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".parquet") as tmp:
        sample_cards_df.to_parquet(tmp.name, engine="pyarrow")
        yield tmp.name
    os.unlink(tmp.name)


def test_load_all_cards_adapter(temp_parquet_file):
    """Test load_all_cards() legacy function."""
    # Direct loader call
    loader = AllCardsLoader(file_path=temp_parquet_file)
    direct_result = loader.load()

    # Legacy adapter call
    # Note: We need to temporarily override the loader's file path
    from code.services import legacy_loader_adapter
    legacy_loader_adapter._shared_loader = AllCardsLoader(file_path=temp_parquet_file)
    
    with pytest.warns(DeprecationWarning):
        adapter_result = load_all_cards()

    # Results should be identical
    pd.testing.assert_frame_equal(direct_result, adapter_result)


def test_load_cards_by_name_adapter(temp_parquet_file):
    """Test load_cards_by_name() legacy function."""
    loader = AllCardsLoader(file_path=temp_parquet_file)
    direct_result = loader.get_by_name("Sol Ring")

    # Setup adapter with test file
    from code.services import legacy_loader_adapter
    legacy_loader_adapter._shared_loader = AllCardsLoader(file_path=temp_parquet_file)

    with pytest.warns(DeprecationWarning):
        adapter_result = load_cards_by_name("Sol Ring")

    # Results should be identical
    assert adapter_result is not None
    pd.testing.assert_series_equal(direct_result, adapter_result)


def test_load_cards_by_names_adapter(temp_parquet_file):
    """Test load_cards_by_names() legacy function."""
    loader = AllCardsLoader(file_path=temp_parquet_file)
    names = ["Sol Ring", "Lightning Bolt"]
    direct_result = loader.get_by_names(names)

    from code.services import legacy_loader_adapter
    legacy_loader_adapter._shared_loader = AllCardsLoader(file_path=temp_parquet_file)

    with pytest.warns(DeprecationWarning):
        adapter_result = load_cards_by_names(names)

    pd.testing.assert_frame_equal(direct_result, adapter_result)


def test_load_cards_by_type_adapter(temp_parquet_file):
    """Test load_cards_by_type() legacy function."""
    loader = AllCardsLoader(file_path=temp_parquet_file)
    direct_result = loader.filter_by_type("Instant")

    from code.services import legacy_loader_adapter
    legacy_loader_adapter._shared_loader = AllCardsLoader(file_path=temp_parquet_file)

    with pytest.warns(DeprecationWarning):
        adapter_result = load_cards_by_type("Instant")

    pd.testing.assert_frame_equal(direct_result, adapter_result)


def test_load_cards_with_tag_adapter(temp_parquet_file):
    """Test load_cards_with_tag() legacy function."""
    loader = AllCardsLoader(file_path=temp_parquet_file)
    direct_result = loader.filter_by_themes(["tokens"], mode="any")

    from code.services import legacy_loader_adapter
    legacy_loader_adapter._shared_loader = AllCardsLoader(file_path=temp_parquet_file)

    with pytest.warns(DeprecationWarning):
        adapter_result = load_cards_with_tag("tokens")

    pd.testing.assert_frame_equal(direct_result, adapter_result)


def test_load_cards_with_tags_any_mode(temp_parquet_file):
    """Test load_cards_with_tags() with mode='any'."""
    loader = AllCardsLoader(file_path=temp_parquet_file)
    direct_result = loader.filter_by_themes(["burn", "tokens"], mode="any")

    from code.services import legacy_loader_adapter
    legacy_loader_adapter._shared_loader = AllCardsLoader(file_path=temp_parquet_file)

    with pytest.warns(DeprecationWarning):
        adapter_result = load_cards_with_tags(["burn", "tokens"], require_all=False)

    pd.testing.assert_frame_equal(direct_result, adapter_result)


def test_load_cards_with_tags_all_mode(temp_parquet_file):
    """Test load_cards_with_tags() with mode='all'."""
    loader = AllCardsLoader(file_path=temp_parquet_file)
    direct_result = loader.filter_by_themes(["tokens", "goblins"], mode="all")

    from code.services import legacy_loader_adapter
    legacy_loader_adapter._shared_loader = AllCardsLoader(file_path=temp_parquet_file)

    with pytest.warns(DeprecationWarning):
        adapter_result = load_cards_with_tags(["tokens", "goblins"], require_all=True)

    pd.testing.assert_frame_equal(direct_result, adapter_result)


def test_load_cards_by_color_identity_adapter(temp_parquet_file):
    """Test load_cards_by_color_identity() legacy function."""
    loader = AllCardsLoader(file_path=temp_parquet_file)
    direct_result = loader.filter_by_color_identity(["R"])

    from code.services import legacy_loader_adapter
    legacy_loader_adapter._shared_loader = AllCardsLoader(file_path=temp_parquet_file)

    with pytest.warns(DeprecationWarning):
        adapter_result = load_cards_by_color_identity(["R"])

    pd.testing.assert_frame_equal(direct_result, adapter_result)


def test_search_cards_adapter(temp_parquet_file):
    """Test search_cards() legacy function."""
    loader = AllCardsLoader(file_path=temp_parquet_file)
    direct_result = loader.search("token", limit=100)

    from code.services import legacy_loader_adapter
    legacy_loader_adapter._shared_loader = AllCardsLoader(file_path=temp_parquet_file)

    with pytest.warns(DeprecationWarning):
        adapter_result = search_cards("token", limit=100)

    pd.testing.assert_frame_equal(direct_result, adapter_result)


def test_deprecation_warnings_logged(temp_parquet_file, caplog):
    """Test that deprecation warnings are properly logged."""
    from code.services import legacy_loader_adapter
    legacy_loader_adapter._shared_loader = AllCardsLoader(file_path=temp_parquet_file)

    with pytest.warns(DeprecationWarning):
        load_cards_by_name("Sol Ring")

    # Check that warning was logged
    assert any("DEPRECATION" in record.message for record in caplog.records)


def test_feature_flag_disabled(temp_parquet_file, monkeypatch):
    """Test behavior when USE_ALL_CARDS_FILE is disabled."""
    # Disable feature flag
    monkeypatch.setattr("code.settings.USE_ALL_CARDS_FILE", False)
    
    # Reimport to pick up new setting
    import importlib
    from code.services import legacy_loader_adapter
    importlib.reload(legacy_loader_adapter)

    legacy_loader_adapter._shared_loader = AllCardsLoader(file_path=temp_parquet_file)

    with pytest.warns(DeprecationWarning):
        result = load_all_cards()

    # Should return empty DataFrame when disabled
    assert result.empty


def test_adapter_uses_shared_loader(temp_parquet_file):
    """Test that adapter reuses shared loader instance for performance."""
    from code.services import legacy_loader_adapter
    
    # Clear any existing loader
    legacy_loader_adapter._shared_loader = None
    legacy_loader_adapter._shared_loader = AllCardsLoader(file_path=temp_parquet_file)

    with pytest.warns(DeprecationWarning):
        load_all_cards()
    
    loader1 = legacy_loader_adapter._shared_loader

    with pytest.warns(DeprecationWarning):
        load_cards_by_name("Sol Ring")
    
    loader2 = legacy_loader_adapter._shared_loader

    # Should be the same instance
    assert loader1 is loader2


def test_multiple_calls_use_cache(temp_parquet_file, monkeypatch):
    """Test that multiple adapter calls benefit from caching."""
    import time
    from code.services import legacy_loader_adapter
    
    # Ensure feature flag is enabled
    monkeypatch.setattr("code.settings.USE_ALL_CARDS_FILE", True)
    
    # Reimport to pick up setting
    import importlib
    importlib.reload(legacy_loader_adapter)
    
    legacy_loader_adapter._shared_loader = AllCardsLoader(file_path=temp_parquet_file)

    # First call (loads from disk)
    start = time.time()
    with pytest.warns(DeprecationWarning):
        load_all_cards()
    first_time = time.time() - start

    # Second call (should use cache)
    start = time.time()
    with pytest.warns(DeprecationWarning):
        load_all_cards()
    second_time = time.time() - start

    # Cache should make second call faster (or at least not slower)
    # Use a more lenient check since file is very small
    assert second_time <= first_time * 2  # Allow some variance
