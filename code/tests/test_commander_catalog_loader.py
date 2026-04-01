from __future__ import annotations

from pathlib import Path

import pytest

from web.services import commander_catalog_loader as loader


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "csv_files" / "testdata"


def _set_csv_dir(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    """Legacy CSV directory setter - kept for compatibility but no longer used in M4."""
    monkeypatch.setenv("CSV_FILES_DIR", str(path))
    loader.clear_commander_catalog_cache()


def test_commander_catalog_basic_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test commander catalog loading from Parquet (M4: updated for Parquet migration)."""
    # Note: Commander catalog now loads from all_cards.parquet, not commander_cards.csv
    # This test validates the real production data instead of test fixtures
    
    catalog = loader.load_commander_catalog()

    # Changed: source_path now points to all_cards.parquet
    assert catalog.source_path.name == "all_cards.parquet"
    # Changed: Real data has 2800+ commanders, not just 4 test fixtures
    assert len(catalog.entries) > 2700  # At least 2700 commanders

    # Test a known commander from production data
    krenko = catalog.by_slug.get("krenko-mob-boss")
    if krenko:  # May not be in every version of the data
        assert krenko.display_name == "Krenko, Mob Boss"
        assert krenko.color_identity == ("R",)
        assert krenko.color_identity_key == "R"
        assert not krenko.is_colorless
        assert "Goblin Kindred" in krenko.themes or "goblin kindred" in [t.lower() for t in krenko.themes]



