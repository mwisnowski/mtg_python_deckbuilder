"""
Unit tests for code/file_setup/art_tags_cache.py.

Small synthetic fixtures only; no live network access or dependency on real
Scryfall bulk data files.
"""
from __future__ import annotations

import json

import pandas as pd

from code.file_setup import art_tags_cache


def test_build_illustration_id_map(tmp_path, monkeypatch):
    bulk = [
        {"id": "sid-1", "illustration_id": "illus-1"},
        {"id": "sid-2", "illustration_id": "illus-2"},
        {"id": "sid-3"},  # no illustration_id -> excluded
        {"illustration_id": "illus-4"},  # no id -> excluded
    ]
    path = tmp_path / "scryfall_bulk_data.json"
    path.write_text(json.dumps(bulk), encoding="utf-8")
    monkeypatch.setattr(art_tags_cache, "LOCAL_BULK_DATA_PATH", path)

    result = art_tags_cache.build_illustration_id_map()
    assert result == {"sid-1": "illus-1", "sid-2": "illus-2"}


def test_build_illustration_id_map_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(art_tags_cache, "LOCAL_BULK_DATA_PATH", tmp_path / "missing.json")
    assert art_tags_cache.build_illustration_id_map() == {}


def test_build_art_tags_index_dedupes_and_sorts():
    bulk = [
        {"label": "blue glow", "slug": "blue-glow", "taggings": [{"illustration_id": "illus-1", "weight": "strong"}]},
        {"label": "Squirrel", "slug": "squirrel", "taggings": [
            {"illustration_id": "illus-1", "weight": "weak"},
            {"illustration_id": "illus-2", "weight": "very_strong"},
        ]},
        {"label": "squirrel", "slug": "squirrel-alias", "taggings": [{"illustration_id": "illus-1", "weight": "median"}]},
        {"slug": "no-label-tag", "taggings": [{"illustration_id": "illus-3", "weight": "strong"}]},
        {"label": "orphan tag", "taggings": []},
    ]
    index = art_tags_cache.build_art_tags_index(bulk)
    assert index["illus-1"] == ["Squirrel", "blue glow"]
    assert index["illus-2"] == ["Squirrel"]
    assert index["illus-3"] == ["no label tag"]
    assert "illus-4" not in index


def test_build_art_tags_cache_writes_column(tmp_path, monkeypatch):
    parquet_path = tmp_path / "all_cards.parquet"
    df = pd.DataFrame({
        "name": ["Card A", "Card B", "Card C"],
        "scryfallID": ["sid-1", "sid-2", None],
    })
    df.to_parquet(parquet_path, index=False)

    bulk_path = tmp_path / "scryfall_bulk_data.json"
    bulk_path.write_text(json.dumps([
        {"id": "sid-1", "illustration_id": "illus-1"},
        {"id": "sid-2", "illustration_id": "illus-2"},
    ]), encoding="utf-8")

    monkeypatch.setattr(art_tags_cache, "PARQUET_PATH", parquet_path)
    monkeypatch.setattr(art_tags_cache, "LOCAL_BULK_DATA_PATH", bulk_path)
    monkeypatch.setattr(
        art_tags_cache,
        "fetch_art_tags_bulk",
        lambda output_func=None: [
            {"label": "blue glow", "taggings": [{"illustration_id": "illus-1", "weight": "strong"}]},
        ],
    )

    art_tags_cache.build_art_tags_cache(output_func=lambda msg: None)

    result = pd.read_parquet(parquet_path)
    assert list(result.loc[result["name"] == "Card A", "artTags"].iloc[0]) == ["blue glow"]
    assert list(result.loc[result["name"] == "Card B", "artTags"].iloc[0]) == []
    assert list(result.loc[result["name"] == "Card C", "artTags"].iloc[0]) == []
