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

import json

import pandas as pd

from code.file_setup.image_cache import ImageCache


def _write_bulk(cards: list[dict], path: Path) -> None:
    """Write cards in scryfall bulk-data line-per-object format."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("[\n")
        for i, card in enumerate(cards):
            f.write(json.dumps(card))
            if i < len(cards) - 1:
                f.write(",")
            f.write("\n")
        f.write("]\n")


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


def test_cache_statistics_counts_per_card_folder_layout(tmp_path: Path):
    """Regression: cache_statistics() must count the current per-card/
    per-printing layout (`{Card Name}/{size}/*.jpg`), not just the legacy
    flat layout (`{size}/*.jpg`) -- otherwise the Settings page reports
    ~0 cached images even when most cards are already downloaded, which
    causes the "Download Card Images" button to look like it's re-downloading
    everything from scratch.
    """
    cache = ImageCache(base_dir=str(tmp_path / "images"))

    # New per-card/per-printing layout.
    for card_name in ("Goblin", "Balls of Fire"):
        size_dir = cache.base_dir / card_name / "normal"
        size_dir.mkdir(parents=True)
        (size_dir / "abc123.jpg").write_bytes(b"x")

    # Legacy flat layout (a mixed-cache scenario should still be supported).
    legacy_dir = cache.base_dir / "normal"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "Legacy Card.jpg").write_bytes(b"x")

    with patch.object(cache, "is_enabled", return_value=True):
        stats = cache.cache_statistics()

    assert stats["normal"]["count"] == 3
    assert stats["small"]["count"] == 0


def test_stream_all_printings_excludes_token_copy_layout(tmp_path: Path, monkeypatch):
    """Regression (roadmap_39, Milestone 4): a token-copy Scryfall entry
    (Offspring/Embalm/etc.) can share a real card's name -- e.g. Agate
    Instigator's Offspring token copy is a separate `layout: "token"` entry
    named "Agate Instigator". Without a layout check, it leaks into
    `card_printings.parquet` as a fake printing of the real card.
    """
    bulk_path = tmp_path / "scryfall_bulk_data.json"
    _write_bulk(
        [
            {
                "name": "Agate Instigator", "layout": "normal", "type_line": "Creature — Human Warrior",
                "id": "real-printing", "set": "mkm", "set_name": "Murders at Karlov Manor",
                "collector_number": "1", "released_at": "2024-02-09",
                "finishes": ["nonfoil"], "digital": False,
                "image_uris": {"small": "https://example.com/real_small.jpg", "normal": "https://example.com/real_normal.jpg"},
            },
            {
                "name": "Agate Instigator", "layout": "token", "type_line": "Token Creature — Human Warrior",
                "id": "token-copy", "set": "tmkm", "set_name": "Murders at Karlov Manor Tokens",
                "collector_number": "1", "released_at": "2024-02-09",
                "finishes": ["nonfoil"], "digital": False,
                "image_uris": {"small": "https://example.com/token_small.jpg", "normal": "https://example.com/token_normal.jpg"},
            },
        ],
        bulk_path,
    )

    parquet_path = tmp_path / "all_cards.parquet"
    pd.DataFrame([{"name": "Agate Instigator"}]).to_parquet(parquet_path, index=False)

    cache = ImageCache(base_dir=str(tmp_path / "images"), bulk_data_path=str(bulk_path))
    cache.printings_index_path = tmp_path / "card_printings.parquet"
    monkeypatch.setattr("code.path_util.get_processed_cards_path", lambda: str(parquet_path))

    count = cache.build_printings_index()

    assert count == 1
    df = pd.read_parquet(cache.printings_index_path)
    assert list(df["scryfall_id"]) == ["real-printing"]

