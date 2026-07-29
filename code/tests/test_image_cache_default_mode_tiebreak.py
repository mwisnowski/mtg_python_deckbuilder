"""Regression test: default-mode downloads must pick exactly one printing
per card even when multiple printings tie for the top score.

`card_printings.parquet`'s `is_default` column can have multiple True rows
per card name (documented tie behavior), and `get_default_printing_id()`
already breaks ties by most recent `released_at`. `download_all_printings()`
must apply the same tie-break when filtering to `default` mode, otherwise
it downloads one file per tied printing instead of a single default image.
"""
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from code.file_setup.image_cache import ImageCache


def _make_printings_df():
    # "Thought Vessel"-style tie: two rows share the top score (20); the
    # more recently released one should win.
    return pd.DataFrame(
        [
            {
                "name": "Tied Card",
                "face_name": "Tied Card",
                "scryfall_id": "old-printing",
                "set": "old",
                "set_name": "Old Set",
                "collector_number": "1",
                "released_at": "2015-01-01",
                "finishes": ["nonfoil"],
                "score": 20,
                "image_url_small": "https://example.com/old_small.jpg",
                "image_url_normal": "https://example.com/old_normal.jpg",
                "is_default": True,
            },
            {
                "name": "Tied Card",
                "face_name": "Tied Card",
                "scryfall_id": "new-printing",
                "set": "new",
                "set_name": "New Set",
                "collector_number": "2",
                "released_at": "2024-06-01",
                "finishes": ["nonfoil"],
                "score": 20,
                "image_url_small": "https://example.com/new_small.jpg",
                "image_url_normal": "https://example.com/new_normal.jpg",
                "is_default": True,
            },
        ]
    )


def test_download_all_printings_default_mode_dedupes_tied_default_rows(tmp_path: Path):
    cache = ImageCache(base_dir=str(tmp_path / "images"))
    cache.printings_index_path = tmp_path / "card_printings.parquet"
    _make_printings_df().to_parquet(cache.printings_index_path, index=False)

    with patch.object(cache, "_download_image", return_value=True) as mock_download, \
            patch.object(cache, "is_enabled", return_value=True):
        stats = cache.download_all_printings(mode="default", sizes=["normal"])

    assert stats["total"] == 1, "default mode must keep exactly one row for a tied card"
    # Only the most recently released tied printing should be downloaded.
    downloaded_urls = [call.args[0] for call in mock_download.call_args_list]
    assert downloaded_urls == ["https://example.com/new_normal.jpg"]
