"""Tests for token/emblem image caching (roadmap_39, Milestone 3)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from code.file_setup.image_cache import ImageCache, _is_token_scryfall_entry


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


def _token_catalog_row(**overrides) -> dict:
    base = {
        "name": "Elemental", "layout": "token", "type": "Token Creature — Elemental",
        "text": "", "power": "1", "toughness": "1", "colors": ["R"], "colorIdentity": ["R"],
        "subtypes": ["Elemental"], "keywords": [], "isEmblem": False, "relatedCards": ["Card A"],
        "faceName_a": None, "faceName_b": None,
        "face_a_type": None, "face_a_text": None, "face_a_power": None, "face_a_toughness": None,
        "face_a_keywords": None,
        "face_b_type": None, "face_b_text": None, "face_b_power": None, "face_b_toughness": None,
        "face_b_keywords": None,
    }
    base.update(overrides)
    return base


def test_is_token_scryfall_entry_filters_correctly():
    assert _is_token_scryfall_entry({"layout": "token"})
    assert _is_token_scryfall_entry({"layout": "double_faced_token"})
    assert _is_token_scryfall_entry({"layout": "emblem"})
    assert _is_token_scryfall_entry({"layout": "flip", "type_line": "Token Creature — Goblin"})
    # Real flip cards never have "Token" in their type line.
    assert not _is_token_scryfall_entry({"layout": "flip", "type_line": "Creature — Kithkin"})
    assert not _is_token_scryfall_entry({"layout": "normal", "type_line": "Creature — Human"})
    assert not _is_token_scryfall_entry({"layout": "transform", "type_line": "Creature — Zombie"})


def test_build_token_printings_index_sets_is_default_for_no_pt_tokens(tmp_path: Path):
    """Emblems/non-creature tokens have no power/toughness (NaN); groupby drops
    NaN-keyed groups by default, which previously left `is_default` unset
    (None) for every one of them instead of True.
    """
    bulk_path = tmp_path / "scryfall_bulk_data.json"
    _write_bulk(
        [
            {
                "name": "Liliana Emblem", "layout": "emblem", "type_line": "Emblem",
                "id": "emblem-id", "set": "war", "set_name": "War of the Spark",
                "collector_number": "1", "released_at": "2019-05-03",
                "finishes": ["nonfoil"], "digital": False, "colors": ["R"],
                "image_uris": {"small": "https://example.com/small.jpg", "normal": "https://example.com/normal.jpg"},
            },
        ],
        bulk_path,
    )

    cache = ImageCache(base_dir=str(tmp_path / "images"), bulk_data_path=str(bulk_path))
    cache.token_printings_index_path = tmp_path / "token_printings.parquet"

    tokens_df = pd.DataFrame([_token_catalog_row(
        name="Liliana Emblem", layout="emblem", type="Emblem", isEmblem=True, power=None, toughness=None,
    )])
    count = cache.build_token_printings_index(tokens_df)

    assert count == 1
    df = pd.read_parquet(cache.token_printings_index_path)
    assert bool(df.iloc[0]["is_default"]) is True


def test_build_token_printings_index_bridges_identity_and_stays_separate(tmp_path: Path):
    bulk_path = tmp_path / "scryfall_bulk_data.json"
    _write_bulk(
        [
            {
                "name": "Elemental", "layout": "token", "type_line": "Token Creature — Elemental",
                "power": "1", "toughness": "1", "id": "elemental-id", "set": "l12",
                "set_name": "Launch Parties", "collector_number": "1", "released_at": "2012-01-01",
                "finishes": ["nonfoil"], "digital": False, "colors": ["R"],
                "image_uris": {"small": "https://example.com/small.jpg", "normal": "https://example.com/normal.jpg"},
            },
            # A real card sharing the token's name/type is never matched (different
            # layout, filtered out before identity bridging is even attempted).
            {
                "name": "Elemental", "layout": "normal", "type_line": "Creature — Elemental",
                "power": "1", "toughness": "1", "id": "real-card-id", "set": "abc",
                "set_name": "Some Set", "collector_number": "9", "released_at": "2020-01-01",
                "finishes": ["nonfoil"], "digital": False, "colors": ["R"],
                "image_uris": {"small": "https://example.com/real_small.jpg", "normal": "https://example.com/real_normal.jpg"},
            },
        ],
        bulk_path,
    )

    cache = ImageCache(base_dir=str(tmp_path / "images"), bulk_data_path=str(bulk_path))
    cache.token_printings_index_path = tmp_path / "token_printings.parquet"
    cache.printings_index_path = tmp_path / "card_printings.parquet"  # must stay untouched

    tokens_df = pd.DataFrame([_token_catalog_row()])
    count = cache.build_token_printings_index(tokens_df)

    assert count == 1
    df = pd.read_parquet(cache.token_printings_index_path)
    assert df.iloc[0]["scryfall_id"] == "elemental-id"
    assert df.iloc[0]["is_default"]
    assert not cache.printings_index_path.exists()


def test_build_token_printings_index_keeps_same_name_different_stats_distinct(tmp_path: Path):
    """Two catalog identities sharing a name but different P/T must both survive
    as their own default printing, not collapse into one (roadmap_39 notes
    "Elemental" alone has 9+ distinct power values -- name is not a safe key).
    """
    bulk_path = tmp_path / "scryfall_bulk_data.json"
    _write_bulk(
        [
            {
                "name": "Elemental", "layout": "token", "type_line": "Token Creature — Elemental",
                "power": "1", "toughness": "1", "id": "elemental-1-1", "set": "l12",
                "set_name": "Launch Parties", "collector_number": "1", "released_at": "2012-01-01",
                "finishes": ["nonfoil"], "digital": False, "colors": ["R"],
                "image_uris": {"small": "https://example.com/1_1_small.jpg", "normal": "https://example.com/1_1_normal.jpg"},
            },
            {
                "name": "Elemental", "layout": "token", "type_line": "Token Creature — Elemental",
                "power": "2", "toughness": "2", "id": "elemental-2-2", "set": "who",
                "set_name": "War of the Spark", "collector_number": "2", "released_at": "2019-05-03",
                "finishes": ["nonfoil"], "digital": False, "colors": ["R"],
                "image_uris": {"small": "https://example.com/2_2_small.jpg", "normal": "https://example.com/2_2_normal.jpg"},
            },
        ],
        bulk_path,
    )

    cache = ImageCache(base_dir=str(tmp_path / "images"), bulk_data_path=str(bulk_path))
    cache.token_printings_index_path = tmp_path / "token_printings.parquet"

    tokens_df = pd.DataFrame([
        _token_catalog_row(power="1", toughness="1"),
        _token_catalog_row(power="2", toughness="2"),
    ])
    count = cache.build_token_printings_index(tokens_df)

    assert count == 2
    df = pd.read_parquet(cache.token_printings_index_path)
    assert set(df["scryfall_id"]) == {"elemental-1-1", "elemental-2-2"}
    # Both variants get their own default printing -- neither is dropped in favor of the other.
    assert df["is_default"].sum() == 2


def test_download_all_token_printings_uses_separate_tree(tmp_path: Path):
    cache = ImageCache(base_dir=str(tmp_path / "images"))
    cache.token_printings_index_path = tmp_path / "token_printings.parquet"
    pd.DataFrame([
        {
            "name": "Elemental", "face_name": "Elemental", "power": "1", "toughness": "1",
            "scryfall_id": "elemental-id",
            "set": "l12", "set_name": "Launch Parties", "collector_number": "1",
            "released_at": "2012-01-01", "finishes": ["nonfoil"], "score": 20,
            "image_url_small": "https://example.com/small.jpg",
            "image_url_normal": "https://example.com/normal.jpg", "is_default": True,
        }
    ]).to_parquet(cache.token_printings_index_path, index=False)

    from unittest.mock import patch
    with patch.object(cache, "_download_image", return_value=True) as mock_download, \
            patch.object(cache, "is_enabled", return_value=True):
        stats = cache.download_all_token_printings(mode="default", sizes=["normal"])

    assert stats["downloaded"] == 1
    expected_path = tmp_path / "images" / "tokens" / "Elemental" / "normal" / "elemental-id.jpg"
    called_path = mock_download.call_args.args[1]
    assert called_path == expected_path
    assert "tokens" in expected_path.parts  # never mixed into card_files/images/{Card Name}/


def test_download_all_token_printings_keeps_both_stat_variants(tmp_path: Path):
    """Default mode must download BOTH "Elemental" variants, not dedup down to one."""
    cache = ImageCache(base_dir=str(tmp_path / "images"))
    cache.token_printings_index_path = tmp_path / "token_printings.parquet"
    pd.DataFrame([
        {
            "name": "Elemental", "face_name": "Elemental", "power": "1", "toughness": "1",
            "scryfall_id": "elemental-1-1",
            "set": "l12", "set_name": "Launch Parties", "collector_number": "1",
            "released_at": "2012-01-01", "finishes": ["nonfoil"], "score": 20,
            "image_url_small": "https://example.com/1_1_small.jpg",
            "image_url_normal": "https://example.com/1_1_normal.jpg", "is_default": True,
        },
        {
            "name": "Elemental", "face_name": "Elemental", "power": "2", "toughness": "2",
            "scryfall_id": "elemental-2-2",
            "set": "who", "set_name": "War of the Spark", "collector_number": "2",
            "released_at": "2019-05-03", "finishes": ["nonfoil"], "score": 20,
            "image_url_small": "https://example.com/2_2_small.jpg",
            "image_url_normal": "https://example.com/2_2_normal.jpg", "is_default": True,
        },
    ]).to_parquet(cache.token_printings_index_path, index=False)

    from unittest.mock import patch
    with patch.object(cache, "_download_image", return_value=True) as mock_download, \
            patch.object(cache, "is_enabled", return_value=True):
        stats = cache.download_all_token_printings(mode="default", sizes=["normal"])

    assert stats["total"] == 2
    assert stats["downloaded"] == 2
    called_paths = {call.args[1] for call in mock_download.call_args_list}
    assert called_paths == {
        tmp_path / "images" / "tokens" / "Elemental" / "normal" / "elemental-1-1.jpg",
        tmp_path / "images" / "tokens" / "Elemental" / "normal" / "elemental-2-2.jpg",
    }


def test_get_token_printings_disambiguates_by_stats(tmp_path: Path):
    cache = ImageCache(base_dir=str(tmp_path / "images"))
    cache.token_printings_index_path = tmp_path / "token_printings.parquet"
    pd.DataFrame([
        {
            "name": "Elemental", "face_name": "Elemental", "power": "1", "toughness": "1",
            "scryfall_id": "elemental-1-1",
            "set": "l12", "set_name": "Launch Parties", "collector_number": "1",
            "released_at": "2012-01-01", "finishes": ["nonfoil"], "score": 20,
            "image_url_small": "https://example.com/1_1_small.jpg",
            "image_url_normal": "https://example.com/1_1_normal.jpg", "is_default": True,
        },
        {
            "name": "Elemental", "face_name": "Elemental", "power": "2", "toughness": "2",
            "scryfall_id": "elemental-2-2",
            "set": "who", "set_name": "War of the Spark", "collector_number": "2",
            "released_at": "2019-05-03", "finishes": ["nonfoil"], "score": 20,
            "image_url_small": "https://example.com/2_2_small.jpg",
            "image_url_normal": "https://example.com/2_2_normal.jpg", "is_default": True,
        },
    ]).to_parquet(cache.token_printings_index_path, index=False)

    assert len(cache.get_token_printings("Elemental")) == 2
    assert cache.get_default_token_printing_id("Elemental", power="1", toughness="1") == "elemental-1-1"
    assert cache.get_default_token_printing_id("Elemental", power="2", toughness="2") == "elemental-2-2"


def test_token_cache_statistics_counts_across_token_folders(tmp_path: Path):
    cache = ImageCache(base_dir=str(tmp_path / "images"))
    for token_name, count in (("Elemental", 2), ("Spirit", 1)):
        size_dir = cache.token_base_dir / token_name / "normal"
        size_dir.mkdir(parents=True)
        for i in range(count):
            (size_dir / f"id{i}.jpg").write_bytes(b"x")

    from unittest.mock import patch
    with patch.object(cache, "is_enabled", return_value=True):
        stats = cache.token_cache_statistics()

    assert stats["normal"]["count"] == 3
    assert stats["small"]["count"] == 0

