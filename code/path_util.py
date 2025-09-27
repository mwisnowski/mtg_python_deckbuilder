from __future__ import annotations

import os


def csv_dir() -> str:
    """Return the base directory for CSV files.

    Defaults to 'csv_files'. Override with CSV_FILES_DIR for tests or advanced setups.
    """
    try:
        base = os.getenv("CSV_FILES_DIR")
        base = base.strip() if isinstance(base, str) else None
        return base or "csv_files"
    except Exception:
        return "csv_files"
