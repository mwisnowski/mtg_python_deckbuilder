from __future__ import annotations

import os


def csv_dir() -> str:
    """Return the base directory for CSV files.

    Defaults to 'csv_files'. Override with CSV_FILES_DIR for tests or advanced setups.
    
    NOTE: DEPRECATED in v3.0.0 - Use card_files_dir() instead.
    """
    try:
        base = os.getenv("CSV_FILES_DIR")
        base = base.strip() if isinstance(base, str) else None
        return base or "csv_files"
    except Exception:
        return "csv_files"


# New Parquet-based directory utilities (v3.0.0+)

def card_files_dir() -> str:
    """Return the base directory for card files (Parquet and metadata).
    
    Defaults to 'card_files'. Override with CARD_FILES_DIR environment variable.
    """
    try:
        base = os.getenv("CARD_FILES_DIR")
        base = base.strip() if isinstance(base, str) else None
        return base or "card_files"
    except Exception:
        return "card_files"


def card_files_raw_dir() -> str:
    """Return the directory for raw MTGJSON Parquet files.
    
    Defaults to 'card_files/raw'. Override with CARD_FILES_RAW_DIR environment variable.
    """
    try:
        base = os.getenv("CARD_FILES_RAW_DIR")
        base = base.strip() if isinstance(base, str) else None
        return base or os.path.join(card_files_dir(), "raw")
    except Exception:
        return os.path.join(card_files_dir(), "raw")


def card_files_processed_dir() -> str:
    """Return the directory for processed/tagged Parquet files.
    
    Defaults to 'card_files/processed'. Override with CARD_FILES_PROCESSED_DIR environment variable.
    """
    try:
        base = os.getenv("CARD_FILES_PROCESSED_DIR")
        base = base.strip() if isinstance(base, str) else None
        return base or os.path.join(card_files_dir(), "processed")
    except Exception:
        return os.path.join(card_files_dir(), "processed")


def get_raw_cards_path() -> str:
    """Get the path to the raw MTGJSON Parquet file.
    
    Returns:
        Path to card_files/raw/cards.parquet
    """
    return os.path.join(card_files_raw_dir(), "cards.parquet")


def get_processed_cards_path() -> str:
    """Get the path to the processed/tagged Parquet file.
    
    Returns:
        Path to card_files/processed/all_cards.parquet
    """
    return os.path.join(card_files_processed_dir(), "all_cards.parquet")


def get_commander_cards_path() -> str:
    """Get the path to the pre-filtered commander-only Parquet file.
    
    Returns:
        Path to card_files/processed/commander_cards.parquet
    """
    return os.path.join(card_files_processed_dir(), "commander_cards.parquet")


def get_batch_path(batch_id: int) -> str:
    """Get the path to a batch Parquet file.
    
    Args:
        batch_id: Batch number (e.g., 0, 1, 2, ...)
    
    Returns:
        Path to card_files/processed/batch_NNNN.parquet
    """
    return os.path.join(card_files_processed_dir(), f"batch_{batch_id:04d}.parquet")

