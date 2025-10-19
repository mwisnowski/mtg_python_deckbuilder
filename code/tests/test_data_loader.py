"""Tests for DataLoader abstraction layer.

Tests CSV/Parquet reading, writing, conversion, and schema validation.
"""

import os
import shutil
import tempfile

import pandas as pd
import pytest

from code.file_setup.data_loader import DataLoader, validate_schema


@pytest.fixture
def sample_card_data():
    """Sample card data for testing."""
    return pd.DataFrame({
        "name": ["Sol Ring", "Lightning Bolt", "Counterspell"],
        "colorIdentity": ["C", "R", "U"],
        "type": ["Artifact", "Instant", "Instant"],  # MTGJSON uses 'type' not 'types'
        "keywords": ["", "", ""],
        "manaValue": [1.0, 1.0, 2.0],
        "text": ["Tap: Add 2 mana", "Deal 3 damage", "Counter spell"],
        "power": ["", "", ""],
        "toughness": ["", "", ""],
    })


@pytest.fixture
def temp_dir():
    """Temporary directory for test files."""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


class TestDataLoader:
    """Test DataLoader class functionality."""
    
    def test_read_csv(self, sample_card_data, temp_dir):
        """Test reading CSV files."""
        csv_path = os.path.join(temp_dir, "test.csv")
        sample_card_data.to_csv(csv_path, index=False)
        
        loader = DataLoader()
        df = loader.read_cards(csv_path)
        
        assert len(df) == 3
        assert "name" in df.columns
        assert df["name"].iloc[0] == "Sol Ring"
    
    def test_read_parquet(self, sample_card_data, temp_dir):
        """Test reading Parquet files."""
        parquet_path = os.path.join(temp_dir, "test.parquet")
        sample_card_data.to_parquet(parquet_path, index=False)
        
        loader = DataLoader()
        df = loader.read_cards(parquet_path)
        
        assert len(df) == 3
        assert "name" in df.columns
        assert df["name"].iloc[0] == "Sol Ring"
    
    def test_read_with_columns(self, sample_card_data, temp_dir):
        """Test column filtering (Parquet optimization)."""
        parquet_path = os.path.join(temp_dir, "test.parquet")
        sample_card_data.to_parquet(parquet_path, index=False)
        
        loader = DataLoader()
        df = loader.read_cards(parquet_path, columns=["name", "manaValue"])
        
        assert len(df) == 3
        assert len(df.columns) == 2
        assert "name" in df.columns
        assert "manaValue" in df.columns
        assert "colorIdentity" not in df.columns
    
    def test_write_csv(self, sample_card_data, temp_dir):
        """Test writing CSV files."""
        csv_path = os.path.join(temp_dir, "output.csv")
        
        loader = DataLoader()
        loader.write_cards(sample_card_data, csv_path)
        
        assert os.path.exists(csv_path)
        df = pd.read_csv(csv_path)
        assert len(df) == 3
    
    def test_write_parquet(self, sample_card_data, temp_dir):
        """Test writing Parquet files."""
        parquet_path = os.path.join(temp_dir, "output.parquet")
        
        loader = DataLoader()
        loader.write_cards(sample_card_data, parquet_path)
        
        assert os.path.exists(parquet_path)
        df = pd.read_parquet(parquet_path)
        assert len(df) == 3
    
    def test_format_detection_csv(self, sample_card_data, temp_dir):
        """Test automatic CSV format detection."""
        csv_path = os.path.join(temp_dir, "test.csv")
        sample_card_data.to_csv(csv_path, index=False)
        
        loader = DataLoader(format="auto")
        df = loader.read_cards(csv_path)
        
        assert len(df) == 3
    
    def test_format_detection_parquet(self, sample_card_data, temp_dir):
        """Test automatic Parquet format detection."""
        parquet_path = os.path.join(temp_dir, "test.parquet")
        sample_card_data.to_parquet(parquet_path, index=False)
        
        loader = DataLoader(format="auto")
        df = loader.read_cards(parquet_path)
        
        assert len(df) == 3
    
    def test_convert_csv_to_parquet(self, sample_card_data, temp_dir):
        """Test CSV to Parquet conversion."""
        csv_path = os.path.join(temp_dir, "input.csv")
        parquet_path = os.path.join(temp_dir, "output.parquet")
        
        sample_card_data.to_csv(csv_path, index=False)
        
        loader = DataLoader()
        loader.convert(csv_path, parquet_path)
        
        assert os.path.exists(parquet_path)
        df = pd.read_parquet(parquet_path)
        assert len(df) == 3
    
    def test_convert_parquet_to_csv(self, sample_card_data, temp_dir):
        """Test Parquet to CSV conversion."""
        parquet_path = os.path.join(temp_dir, "input.parquet")
        csv_path = os.path.join(temp_dir, "output.csv")
        
        sample_card_data.to_parquet(parquet_path, index=False)
        
        loader = DataLoader()
        loader.convert(parquet_path, csv_path)
        
        assert os.path.exists(csv_path)
        df = pd.read_csv(csv_path)
        assert len(df) == 3
    
    def test_file_not_found(self, temp_dir):
        """Test error handling for missing files."""
        loader = DataLoader()
        
        with pytest.raises(FileNotFoundError):
            loader.read_cards(os.path.join(temp_dir, "nonexistent.csv"))
    
    def test_unsupported_format(self, temp_dir):
        """Test error handling for unsupported formats."""
        with pytest.raises(ValueError, match="Unsupported format"):
            DataLoader(format="xlsx")


class TestSchemaValidation:
    """Test schema validation functionality."""
    
    def test_valid_schema(self, sample_card_data):
        """Test validation with valid schema."""
        # Should not raise
        validate_schema(sample_card_data)
    
    def test_missing_columns(self):
        """Test validation with missing required columns."""
        df = pd.DataFrame({
            "name": ["Sol Ring"],
            "type": ["Artifact"],  # MTGJSON uses 'type'
        })
        
        with pytest.raises(ValueError, match="missing required columns"):
            validate_schema(df)
    
    def test_custom_required_columns(self, sample_card_data):
        """Test validation with custom required columns."""
        # Should not raise with minimal requirements
        validate_schema(sample_card_data, required=["name", "type"])
    
    def test_empty_dataframe(self):
        """Test validation with empty DataFrame."""
        df = pd.DataFrame()
        
        with pytest.raises(ValueError):
            validate_schema(df)


class TestBatchParquet:
    """Test batch Parquet functionality for tagging workflow."""
    
    def test_write_batch_parquet(self, sample_card_data, temp_dir):
        """Test writing batch Parquet files."""
        loader = DataLoader()
        batches_dir = os.path.join(temp_dir, "batches")
        
        # Write batch with tag
        batch_path = loader.write_batch_parquet(
            sample_card_data,
            batch_id=0,
            tag="white",
            batches_dir=batches_dir
        )
        
        assert os.path.exists(batch_path)
        assert batch_path.endswith("batch_0_white.parquet")
        
        # Verify content
        df = loader.read_cards(batch_path)
        assert len(df) == 3
        assert list(df["name"]) == ["Sol Ring", "Lightning Bolt", "Counterspell"]
    
    def test_write_batch_parquet_no_tag(self, sample_card_data, temp_dir):
        """Test writing batch without tag."""
        loader = DataLoader()
        batches_dir = os.path.join(temp_dir, "batches")
        
        batch_path = loader.write_batch_parquet(
            sample_card_data,
            batch_id=1,
            batches_dir=batches_dir
        )
        
        assert batch_path.endswith("batch_1.parquet")
    
    def test_merge_batches(self, sample_card_data, temp_dir):
        """Test merging batch files."""
        loader = DataLoader()
        batches_dir = os.path.join(temp_dir, "batches")
        output_path = os.path.join(temp_dir, "all_cards.parquet")
        
        # Create multiple batches
        batch1 = sample_card_data.iloc[:2]  # First 2 cards
        batch2 = sample_card_data.iloc[2:]  # Last card
        
        loader.write_batch_parquet(batch1, batch_id=0, tag="white", batches_dir=batches_dir)
        loader.write_batch_parquet(batch2, batch_id=1, tag="blue", batches_dir=batches_dir)
        
        # Merge batches
        merged_df = loader.merge_batches(
            output_path=output_path,
            batches_dir=batches_dir,
            cleanup=True
        )
        
        # Verify merged data
        assert len(merged_df) == 3
        assert os.path.exists(output_path)
        
        # Verify batches directory cleaned up
        assert not os.path.exists(batches_dir)
    
    def test_merge_batches_no_cleanup(self, sample_card_data, temp_dir):
        """Test merging without cleanup."""
        loader = DataLoader()
        batches_dir = os.path.join(temp_dir, "batches")
        output_path = os.path.join(temp_dir, "all_cards.parquet")
        
        loader.write_batch_parquet(sample_card_data, batch_id=0, batches_dir=batches_dir)
        
        merged_df = loader.merge_batches(
            output_path=output_path,
            batches_dir=batches_dir,
            cleanup=False
        )
        
        assert len(merged_df) == 3
        assert os.path.exists(batches_dir)  # Should still exist
    
    def test_merge_batches_no_files(self, temp_dir):
        """Test error handling when no batch files exist."""
        loader = DataLoader()
        batches_dir = os.path.join(temp_dir, "empty_batches")
        os.makedirs(batches_dir, exist_ok=True)
        
        with pytest.raises(FileNotFoundError, match="No batch files found"):
            loader.merge_batches(batches_dir=batches_dir)

