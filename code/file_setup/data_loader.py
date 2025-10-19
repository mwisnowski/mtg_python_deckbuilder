"""Data loader abstraction for CSV and Parquet formats.

This module provides a unified interface for reading and writing card data
in both CSV and Parquet formats. It handles format detection, conversion,
and schema validation.

Introduced in v3.0.0 as part of the Parquet migration.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import pandas as pd

from logging_util import get_logger
from path_util import card_files_processed_dir

logger = get_logger(__name__)


# Required columns for deck building
REQUIRED_COLUMNS = [
    "name",
    "colorIdentity",
    "type",  # MTGJSON uses 'type' not 'types'
    "keywords",
    "manaValue",
    "text",
    "power",
    "toughness",
]


def validate_schema(df: pd.DataFrame, required: Optional[List[str]] = None) -> None:
    """Validate that DataFrame contains required columns.
    
    Args:
        df: DataFrame to validate
        required: List of required columns (uses REQUIRED_COLUMNS if None)
    
    Raises:
        ValueError: If required columns are missing
    """
    required = required or REQUIRED_COLUMNS
    missing = [col for col in required if col not in df.columns]
    
    if missing:
        raise ValueError(
            f"Schema validation failed: missing required columns {missing}. "
            f"Available columns: {list(df.columns)}"
        )
    
    logger.debug(f"✓ Schema validation passed ({len(required)} required columns present)")


class DataLoader:
    """Unified data loading interface supporting CSV and Parquet formats.
    
    This class provides transparent access to card data regardless of the
    underlying storage format. It automatically detects the format based on
    file extensions and provides conversion utilities.
    
    Examples:
        >>> loader = DataLoader()
        >>> df = loader.read_cards("card_files/processed/all_cards.parquet")
        >>> loader.write_cards(df, "output.parquet")
        >>> loader.convert("input.csv", "output.parquet")
    """
    
    def __init__(self, format: str = "auto"):
        """Initialize the data loader.
        
        Args:
            format: Format preference - "csv", "parquet", or "auto" (default: auto)
                   "auto" detects format from file extension
        """
        self.format = format.lower()
        if self.format not in ("csv", "parquet", "auto"):
            raise ValueError(f"Unsupported format: {format}. Use 'csv', 'parquet', or 'auto'.")
    
    def read_cards(
        self,
        path: str,
        columns: Optional[List[str]] = None,
        format: Optional[str] = None
    ) -> pd.DataFrame:
        """Load card data from a file.
        
        Args:
            path: File path (e.g., "card_files/processed/all_cards.parquet")
            columns: Optional list of columns to load (Parquet optimization)
            format: Override format detection (uses self.format if None)
        
        Returns:
            DataFrame with card data
        
        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If format is unsupported
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Card data file not found: {path}")
        
        detected_format = format or self._detect_format(path)
        
        logger.debug(f"Loading card data from {path} (format: {detected_format})")
        
        if detected_format == "csv":
            return self._read_csv(path, columns)
        elif detected_format == "parquet":
            return self._read_parquet(path, columns)
        else:
            raise ValueError(f"Unsupported format: {detected_format}")
    
    def write_cards(
        self,
        df: pd.DataFrame,
        path: str,
        format: Optional[str] = None,
        index: bool = False
    ) -> None:
        """Save card data to a file.
        
        Args:
            df: DataFrame to save
            path: Output file path
            format: Force format (overrides auto-detection)
            index: Whether to write DataFrame index (default: False)
        
        Raises:
            ValueError: If format is unsupported
        """
        detected_format = format or self._detect_format(path)
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        
        logger.debug(f"Writing card data to {path} (format: {detected_format}, rows: {len(df)})")
        
        if detected_format == "csv":
            self._write_csv(df, path, index)
        elif detected_format == "parquet":
            self._write_parquet(df, path, index)
        else:
            raise ValueError(f"Unsupported format: {detected_format}")
    
    def convert(
        self,
        src_path: str,
        dst_path: str,
        columns: Optional[List[str]] = None
    ) -> None:
        """Convert between CSV and Parquet formats.
        
        Args:
            src_path: Source file path
            dst_path: Destination file path
            columns: Optional list of columns to include (all if None)
        
        Examples:
            >>> loader.convert("cards.csv", "cards.parquet")
            >>> loader.convert("cards.parquet", "cards.csv", columns=["name", "type"])
        """
        logger.info(f"Converting {src_path} → {dst_path}")
        df = self.read_cards(src_path, columns=columns)
        self.write_cards(df, dst_path)
        logger.info(f"✓ Converted {len(df)} cards")
    
    def _read_csv(self, path: str, columns: Optional[List[str]] = None) -> pd.DataFrame:
        """Read CSV file."""
        try:
            return pd.read_csv(path, usecols=columns, low_memory=False)
        except Exception as e:
            logger.error(f"Failed to read CSV from {path}: {e}")
            raise
    
    def _read_parquet(self, path: str, columns: Optional[List[str]] = None) -> pd.DataFrame:
        """Read Parquet file."""
        try:
            return pd.read_parquet(path, columns=columns)
        except Exception as e:
            logger.error(f"Failed to read Parquet from {path}: {e}")
            raise
    
    def _write_csv(self, df: pd.DataFrame, path: str, index: bool) -> None:
        """Write CSV file."""
        try:
            df.to_csv(path, index=index)
        except Exception as e:
            logger.error(f"Failed to write CSV to {path}: {e}")
            raise
    
    def _write_parquet(self, df: pd.DataFrame, path: str, index: bool) -> None:
        """Write Parquet file with Snappy compression."""
        try:
            df.to_parquet(path, index=index, compression="snappy", engine="pyarrow")
        except Exception as e:
            logger.error(f"Failed to write Parquet to {path}: {e}")
            raise
    
    def _detect_format(self, path: str) -> str:
        """Detect file format from extension.
        
        Args:
            path: File path to analyze
        
        Returns:
            Format string: "csv" or "parquet"
        
        Raises:
            ValueError: If format cannot be determined
        """
        if self.format != "auto":
            return self.format
        
        # Check file extension
        if path.endswith(".csv"):
            return "csv"
        elif path.endswith(".parquet"):
            return "parquet"
        
        # Try to infer from existing files (no extension provided)
        if os.path.exists(f"{path}.parquet"):
            return "parquet"
        elif os.path.exists(f"{path}.csv"):
            return "csv"
        
        raise ValueError(
            f"Cannot determine format for '{path}'. "
            "Use .csv or .parquet extension, or specify format explicitly."
        )
    
    def write_batch_parquet(
        self,
        df: pd.DataFrame,
        batch_id: int,
        tag: str = "",
        batches_dir: Optional[str] = None
    ) -> str:
        """Write a batch Parquet file (used during tagging).
        
        Args:
            df: DataFrame to save as a batch
            batch_id: Unique batch identifier (e.g., 0, 1, 2...)
            tag: Optional tag to include in filename (e.g., "white", "commander")
            batches_dir: Directory for batch files (defaults to card_files/processed/batches)
        
        Returns:
            Path to the written batch file
        
        Example:
            >>> loader.write_batch_parquet(white_df, batch_id=0, tag="white")
            'card_files/processed/batches/batch_0_white.parquet'
        """
        if batches_dir is None:
            batches_dir = os.path.join(card_files_processed_dir(), "batches")
        
        os.makedirs(batches_dir, exist_ok=True)
        
        # Build filename: batch_{id}_{tag}.parquet or batch_{id}.parquet
        filename = f"batch_{batch_id}_{tag}.parquet" if tag else f"batch_{batch_id}.parquet"
        path = os.path.join(batches_dir, filename)
        
        logger.debug(f"Writing batch {batch_id} ({tag or 'no tag'}): {len(df)} cards → {path}")
        self.write_cards(df, path, format="parquet")
        
        return path
    
    def merge_batches(
        self,
        output_path: Optional[str] = None,
        batches_dir: Optional[str] = None,
        cleanup: bool = True
    ) -> pd.DataFrame:
        """Merge all batch Parquet files into a single output file.
        
        Args:
            output_path: Path for merged output (defaults to card_files/processed/all_cards.parquet)
            batches_dir: Directory containing batch files (defaults to card_files/processed/batches)
            cleanup: Whether to delete batch files after merging (default: True)
        
        Returns:
            Merged DataFrame
        
        Raises:
            FileNotFoundError: If no batch files found
        
        Example:
            >>> loader.merge_batches()  # Merges all batches → all_cards.parquet
        """
        if batches_dir is None:
            batches_dir = os.path.join(card_files_processed_dir(), "batches")
        
        if output_path is None:
            from code.path_util import get_processed_cards_path
            output_path = get_processed_cards_path()
        
        # Find all batch files
        batch_files = sorted(Path(batches_dir).glob("batch_*.parquet"))
        
        if not batch_files:
            raise FileNotFoundError(f"No batch files found in {batches_dir}")
        
        logger.info(f"Merging {len(batch_files)} batch files from {batches_dir}")
        
        # Read and concatenate all batches
        dfs = []
        for batch_file in batch_files:
            logger.debug(f"Reading batch: {batch_file.name}")
            df = self.read_cards(str(batch_file), format="parquet")
            dfs.append(df)
        
        # Merge all batches
        merged_df = pd.concat(dfs, ignore_index=True)
        logger.info(f"Merged {len(merged_df)} total cards from {len(dfs)} batches")
        
        # Write merged output
        self.write_cards(merged_df, output_path, format="parquet")
        logger.info(f"✓ Wrote merged data to {output_path}")
        
        # Cleanup batch files if requested
        if cleanup:
            logger.debug(f"Cleaning up {len(batch_files)} batch files")
            for batch_file in batch_files:
                batch_file.unlink()
            
            # Remove batches directory if empty
            try:
                Path(batches_dir).rmdir()
                logger.debug(f"Removed empty batches directory: {batches_dir}")
            except OSError:
                pass  # Directory not empty, keep it
        
        return merged_df

