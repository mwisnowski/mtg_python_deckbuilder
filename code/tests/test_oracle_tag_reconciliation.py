"""
Unit tests for code/scripts/compare_oracle_tags.py.

Covers classify_oracle_tag_candidate() against known real Oracle Tag labels,
and the oracle_id join logic (build_oracle_id_to_local_tags_map) against a
tiny mocked local bulk-data snapshot. No live network access.
"""
from __future__ import annotations

import json

import pandas as pd

from code.scripts.compare_oracle_tags import (
    _load_previous_manual_fields,
    _load_previous_tag_ids,
    build_oracle_id_to_local_tags_map,
    classify_oracle_tag_candidate,
    find_related_local_tag,
)


def test_classify_already_covered_case_and_hyphen_insensitive():
    vocab = {"card draw", "ramp"}
    assert classify_oracle_tag_candidate("Card Draw", "card-draw", vocab) == "already_covered"
    assert classify_oracle_tag_candidate("ramp", "mana-ramp", vocab) == "already_covered"


def test_classify_new_theme_candidate():
    vocab = {"card draw"}
    assert classify_oracle_tag_candidate("Removal", "removal", vocab) == "new_theme_candidate"


def test_classify_not_applicable_flavor_tag():
    vocab: set[str] = set()
    assert classify_oracle_tag_candidate("You Make the Card", "you-make-the-card", vocab) == "not_applicable"


def test_classify_ambiguous_when_no_signal():
    vocab: set[str] = set()
    assert classify_oracle_tag_candidate("Mysterious", "mysterious", vocab) == "ambiguous"


def test_build_oracle_id_to_local_tags_map(tmp_path, monkeypatch):
    bulk_data_path = tmp_path / "scryfall_bulk_data.json"
    bulk_data_path.write_text(json.dumps([
        {"id": "sid-1", "oracle_id": "oid-1"},
        {"id": "sid-2", "oracle_id": "oid-2"},
    ]), encoding="utf-8")

    import code.scripts.compare_oracle_tags as mod
    monkeypatch.setattr(mod, "LOCAL_BULK_DATA_PATH", bulk_data_path)

    df = pd.DataFrame([
        {"scryfallID": "sid-1", "themeTags": ["Ramp"], "metadataTags": []},
        {"scryfallID": "sid-2", "themeTags": ["Removal"], "metadataTags": ["Token Detail: X"]},
        {"scryfallID": "sid-missing", "themeTags": ["Draw"], "metadataTags": []},
    ])

    result = build_oracle_id_to_local_tags_map(df)
    assert result == {
        "oid-1": {"Ramp"},
        "oid-2": {"Removal", "Token Detail: X"},
    }


def test_find_related_local_tag_strong_overlap():
    taggings = [{"oracle_id": "oid-1"}, {"oracle_id": "oid-2"}, {"oracle_id": "oid-3"}]
    oracle_local_map = {
        "oid-1": {"Exile Matters"},
        "oid-2": {"Exile Matters", "Removal"},
        "oid-3": {"Ramp"},
    }
    tag, overlap, resolved, tied = find_related_local_tag(taggings, oracle_local_map)
    assert tag == "Exile Matters"
    assert overlap == 2 / 3
    assert resolved == 3
    assert tied == ["Exile Matters"]


def test_find_related_local_tag_tie_returns_all_candidates():
    taggings = [{"oracle_id": "oid-1"}, {"oracle_id": "oid-2"}]
    oracle_local_map = {
        "oid-1": {"Proliferate", "Planeswalkers"},
        "oid-2": {"Proliferate", "Planeswalkers"},
    }
    tag, overlap, resolved, tied = find_related_local_tag(taggings, oracle_local_map)
    assert tag == "Planeswalkers"  # alphabetically first of the tie
    assert overlap == 1.0
    assert tied == ["Planeswalkers", "Proliferate"]


def test_find_related_local_tag_no_resolved_cards():
    assert find_related_local_tag([{"oracle_id": "oid-unknown"}], {}) == (None, 0.0, 0, [])


def test_load_previous_manual_fields_reads_only_filled_in_values(tmp_path):
    report_path = tmp_path / "oracle_tag_comparison.json"
    report_path.write_text(json.dumps({
        "tags": [
            {"id": "tag-1", "consolidate_to": ["Auras Matter"], "possible_metadata_tags": []},
            {"id": "tag-2", "consolidate_to": [], "possible_metadata_tags": ["Aura Tutor"]},
            {"id": "tag-3", "consolidate_to": [], "possible_metadata_tags": []},
            {"id": "tag-4"},
        ]
    }), encoding="utf-8")
    assert _load_previous_manual_fields(report_path) == {
        "tag-1": {"consolidate_to": ["Auras Matter"]},
        "tag-2": {"possible_metadata_tags": ["Aura Tutor"]},
    }


def test_load_previous_manual_fields_missing_file(tmp_path):
    assert _load_previous_manual_fields(tmp_path / "missing.json") == {}


def test_load_previous_tag_ids_reads_ids(tmp_path):
    report_path = tmp_path / "oracle_tag_comparison.json"
    report_path.write_text(json.dumps({
        "tags": [{"id": "tag-1"}, {"id": "tag-2"}],
    }), encoding="utf-8")
    assert _load_previous_tag_ids(report_path) == {"tag-1", "tag-2"}


def test_load_previous_tag_ids_missing_file(tmp_path):
    assert _load_previous_tag_ids(tmp_path / "missing.json") == set()
