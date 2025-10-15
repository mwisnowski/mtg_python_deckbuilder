"""
Tests for Card Aggregator

Tests the CardAggregator class functionality including:
- Full aggregation of multiple CSV files
- Deduplication (keeping most recent)
- Exclusion of master files (cards.csv, commander_cards.csv)
- Validation of output
- Version rotation
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from code.file_setup.card_aggregator import CardAggregator


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as output_dir:
        yield source_dir, output_dir


@pytest.fixture
def sample_card_data():
    """Sample card data for testing."""
    return {
        "name": ["Sol Ring", "Lightning Bolt", "Counterspell"],
        "faceName": ["Sol Ring", "Lightning Bolt", "Counterspell"],
        "colorIdentity": ["Colorless", "R", "U"],
        "manaCost": ["{1}", "{R}", "{U}{U}"],
        "manaValue": [1, 1, 2],
        "type": ["Artifact", "Instant", "Instant"],
        "text": [
            "Add two colorless mana",
            "Deal 3 damage",
            "Counter target spell",
        ],
    }


def test_ensure_output_dir(temp_dirs):
    """Test that output directory is created."""
    _, output_dir = temp_dirs
    aggregator = CardAggregator(output_dir=output_dir)

    assert os.path.exists(output_dir)
    assert aggregator.output_dir == output_dir


def test_get_card_csvs_excludes_master_files(temp_dirs):
    """Test that cards.csv and commander_cards.csv are excluded."""
    source_dir, _ = temp_dirs

    # Create test files
    Path(source_dir, "cards.csv").touch()
    Path(source_dir, "commander_cards.csv").touch()
    Path(source_dir, "blue_cards.csv").touch()
    Path(source_dir, "red_cards.csv").touch()
    Path(source_dir, ".temp_cards.csv").touch()
    Path(source_dir, "_temp_cards.csv").touch()

    aggregator = CardAggregator()
    csv_files = aggregator.get_card_csvs(source_dir)

    # Should only include blue_cards.csv and red_cards.csv
    basenames = [os.path.basename(f) for f in csv_files]
    assert "blue_cards.csv" in basenames
    assert "red_cards.csv" in basenames
    assert "cards.csv" not in basenames
    assert "commander_cards.csv" not in basenames
    assert ".temp_cards.csv" not in basenames
    assert "_temp_cards.csv" not in basenames
    assert len(csv_files) == 2


def test_deduplicate_cards(sample_card_data):
    """Test that duplicate cards are removed, keeping the last occurrence."""
    # Create DataFrame with duplicates
    df = pd.DataFrame(sample_card_data)

    # Add duplicate Sol Ring with different text
    duplicate_data = {
        "name": ["Sol Ring"],
        "faceName": ["Sol Ring"],
        "colorIdentity": ["Colorless"],
        "manaCost": ["{1}"],
        "manaValue": [1],
        "type": ["Artifact"],
        "text": ["Add two colorless mana (updated)"],
    }
    df_duplicate = pd.DataFrame(duplicate_data)
    df_combined = pd.concat([df, df_duplicate], ignore_index=True)

    # Should have 4 rows before deduplication
    assert len(df_combined) == 4

    aggregator = CardAggregator()
    df_deduped = aggregator.deduplicate_cards(df_combined)

    # Should have 3 rows after deduplication
    assert len(df_deduped) == 3

    # Should keep the last Sol Ring (updated text)
    sol_ring = df_deduped[df_deduped["name"] == "Sol Ring"].iloc[0]
    assert "updated" in sol_ring["text"]


def test_aggregate_all(temp_dirs, sample_card_data):
    """Test full aggregation of multiple CSV files."""
    source_dir, output_dir = temp_dirs

    # Create test CSV files
    df1 = pd.DataFrame(
        {
            "name": ["Sol Ring", "Lightning Bolt"],
            "faceName": ["Sol Ring", "Lightning Bolt"],
            "colorIdentity": ["Colorless", "R"],
            "manaCost": ["{1}", "{R}"],
            "manaValue": [1, 1],
            "type": ["Artifact", "Instant"],
            "text": ["Add two colorless mana", "Deal 3 damage"],
        }
    )

    df2 = pd.DataFrame(
        {
            "name": ["Counterspell", "Path to Exile"],
            "faceName": ["Counterspell", "Path to Exile"],
            "colorIdentity": ["U", "W"],
            "manaCost": ["{U}{U}", "{W}"],
            "manaValue": [2, 1],
            "type": ["Instant", "Instant"],
            "text": ["Counter target spell", "Exile target creature"],
        }
    )

    df1.to_csv(os.path.join(source_dir, "blue_cards.csv"), index=False)
    df2.to_csv(os.path.join(source_dir, "white_cards.csv"), index=False)

    # Create excluded files (should be ignored)
    df1.to_csv(os.path.join(source_dir, "cards.csv"), index=False)
    df1.to_csv(os.path.join(source_dir, "commander_cards.csv"), index=False)

    # Aggregate
    aggregator = CardAggregator(output_dir=output_dir)
    output_path = os.path.join(output_dir, "all_cards.parquet")
    stats = aggregator.aggregate_all(source_dir, output_path)

    # Verify stats
    assert stats["files_processed"] == 2  # Only 2 files (excluded 2)
    assert stats["total_cards"] == 4  # 2 + 2 cards
    assert stats["duplicates_removed"] == 0
    assert os.path.exists(output_path)

    # Verify output
    df_result = pd.read_parquet(output_path)
    assert len(df_result) == 4
    assert "Sol Ring" in df_result["name"].values
    assert "Counterspell" in df_result["name"].values


def test_aggregate_with_duplicates(temp_dirs):
    """Test aggregation with duplicate cards across files."""
    source_dir, output_dir = temp_dirs

    # Create two files with the same card
    df1 = pd.DataFrame(
        {
            "name": ["Sol Ring"],
            "faceName": ["Sol Ring"],
            "colorIdentity": ["Colorless"],
            "manaCost": ["{1}"],
            "manaValue": [1],
            "type": ["Artifact"],
            "text": ["Version 1"],
        }
    )

    df2 = pd.DataFrame(
        {
            "name": ["Sol Ring"],
            "faceName": ["Sol Ring"],
            "colorIdentity": ["Colorless"],
            "manaCost": ["{1}"],
            "manaValue": [1],
            "type": ["Artifact"],
            "text": ["Version 2 (newer)"],
        }
    )

    # Write file1 first, then file2 (file2 is newer)
    file1 = os.path.join(source_dir, "file1.csv")
    file2 = os.path.join(source_dir, "file2.csv")
    df1.to_csv(file1, index=False)
    df2.to_csv(file2, index=False)

    # Make file2 newer by touching it
    os.utime(file2, (datetime.now().timestamp() + 1, datetime.now().timestamp() + 1))

    # Aggregate
    aggregator = CardAggregator(output_dir=output_dir)
    output_path = os.path.join(output_dir, "all_cards.parquet")
    stats = aggregator.aggregate_all(source_dir, output_path)

    # Should have removed 1 duplicate
    assert stats["duplicates_removed"] == 1
    assert stats["total_cards"] == 1

    # Should keep the newer version (file2)
    df_result = pd.read_parquet(output_path)
    assert "Version 2 (newer)" in df_result["text"].iloc[0]


def test_validate_output(temp_dirs, sample_card_data):
    """Test output validation."""
    source_dir, output_dir = temp_dirs

    # Create and aggregate test data
    df = pd.DataFrame(sample_card_data)
    df.to_csv(os.path.join(source_dir, "test_cards.csv"), index=False)

    aggregator = CardAggregator(output_dir=output_dir)
    output_path = os.path.join(output_dir, "all_cards.parquet")
    aggregator.aggregate_all(source_dir, output_path)

    # Validate
    is_valid, errors = aggregator.validate_output(output_path, source_dir)

    assert is_valid
    assert len(errors) == 0


def test_validate_missing_file(temp_dirs):
    """Test validation with missing output file."""
    source_dir, output_dir = temp_dirs

    aggregator = CardAggregator(output_dir=output_dir)
    output_path = os.path.join(output_dir, "nonexistent.parquet")

    is_valid, errors = aggregator.validate_output(output_path, source_dir)

    assert not is_valid
    assert len(errors) > 0
    assert "not found" in errors[0].lower()


def test_rotate_versions(temp_dirs, sample_card_data):
    """Test version rotation."""
    _, output_dir = temp_dirs

    # Create initial file
    df = pd.DataFrame(sample_card_data)
    output_path = os.path.join(output_dir, "all_cards.parquet")
    df.to_parquet(output_path)

    aggregator = CardAggregator(output_dir=output_dir)

    # Rotate versions
    aggregator.rotate_versions(output_path, keep_versions=3)

    # Should have created v1
    v1_path = os.path.join(output_dir, "all_cards_v1.parquet")
    assert os.path.exists(v1_path)
    assert not os.path.exists(output_path)  # Original moved to v1

    # Create new file and rotate again
    df.to_parquet(output_path)
    aggregator.rotate_versions(output_path, keep_versions=3)

    # Should have v1 and v2
    v2_path = os.path.join(output_dir, "all_cards_v2.parquet")
    assert os.path.exists(v1_path)
    assert os.path.exists(v2_path)


def test_detect_changes(temp_dirs):
    """Test change detection for incremental updates."""
    source_dir, output_dir = temp_dirs

    # Create metadata file
    metadata_path = os.path.join(output_dir, ".aggregate_metadata.json")
    past_time = (datetime.now() - timedelta(hours=1)).isoformat()
    metadata = {"timestamp": past_time}
    with open(metadata_path, "w") as f:
        json.dump(metadata, f)

    # Create CSV files (one old, one new)
    old_file = os.path.join(source_dir, "old_cards.csv")
    new_file = os.path.join(source_dir, "new_cards.csv")

    df = pd.DataFrame({"name": ["Test Card"]})
    df.to_csv(old_file, index=False)
    df.to_csv(new_file, index=False)

    # Make old_file older than metadata
    old_time = (datetime.now() - timedelta(hours=2)).timestamp()
    os.utime(old_file, (old_time, old_time))

    aggregator = CardAggregator(output_dir=output_dir)
    changed_files = aggregator.detect_changes(source_dir, metadata_path)

    # Should only detect new_file as changed
    assert len(changed_files) == 1
    assert os.path.basename(changed_files[0]) == "new_cards.csv"


def test_aggregate_all_no_files(temp_dirs):
    """Test aggregation with no CSV files."""
    source_dir, output_dir = temp_dirs

    aggregator = CardAggregator(output_dir=output_dir)
    output_path = os.path.join(output_dir, "all_cards.parquet")

    with pytest.raises(ValueError, match="No CSV files found"):
        aggregator.aggregate_all(source_dir, output_path)


def test_aggregate_all_empty_files(temp_dirs):
    """Test aggregation with empty CSV files."""
    source_dir, output_dir = temp_dirs

    # Create empty CSV file
    empty_file = os.path.join(source_dir, "empty.csv")
    pd.DataFrame().to_csv(empty_file, index=False)

    aggregator = CardAggregator(output_dir=output_dir)
    output_path = os.path.join(output_dir, "all_cards.parquet")

    with pytest.raises(ValueError, match="No valid CSV files"):
        aggregator.aggregate_all(source_dir, output_path)
