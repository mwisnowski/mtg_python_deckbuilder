"""
Unit tests for code/scripts/apply_oracle_tag_adoptions.py.

Uses small synthetic report/DataFrame/bulk-data fixtures; no live network
access or dependency on the real oracle_tag_comparison.json.
"""
from __future__ import annotations

import json

import pandas as pd

from code.scripts.apply_oracle_tag_adoptions import (
    apply_adoptions,
    collect_consolidate_to_adoptions,
    collect_possible_metadata_tag_adoptions,
    find_needs_manual_review,
    load_classification_overrides,
    resolve_target_column,
)


def _tag(**kwargs):
    base = {
        "id": "tag-id",
        "slug": "tag-slug",
        "classification": "consolidation_candidate",
        "consolidate_to": [],
        "possible_metadata_tags": [],
        "related_local_tag": None,
        "related_local_tag_candidates": None,
    }
    base.update(kwargs)
    return base


def test_collect_consolidate_to_explicit_honored_for_any_classification():
    report = {"tags": [_tag(id="t1", classification="ambiguous", consolidate_to=["Removal"])]}
    assert collect_consolidate_to_adoptions(report) == {"t1": ["Removal"]}


def test_collect_consolidate_to_fallback_only_for_actionable_classifications():
    report = {"tags": [_tag(id="t1", classification="ambiguous", related_local_tag="Ramp")]}
    assert collect_consolidate_to_adoptions(report) == {}


def test_collect_consolidate_to_fallback_single_related_tag():
    report = {"tags": [_tag(id="t1", classification="consolidation_candidate", related_local_tag="Ramp")]}
    assert collect_consolidate_to_adoptions(report) == {"t1": ["Ramp"]}


def test_collect_consolidate_to_fallback_candidates_within_cap():
    report = {
        "tags": [
            _tag(
                id="t1",
                classification="metadata_or_synergy_candidate",
                related_local_tag_candidates=["Ramp", "Mana Rocks"],
            )
        ]
    }
    assert collect_consolidate_to_adoptions(report) == {"t1": ["Ramp", "Mana Rocks"]}


def test_collect_consolidate_to_fallback_candidates_over_cap_skipped():
    report = {
        "tags": [
            _tag(
                id="t1",
                classification="consolidation_candidate",
                related_local_tag_candidates=["A", "B", "C", "D"],
            )
        ]
    }
    adoptions = collect_consolidate_to_adoptions(report)
    assert adoptions == {}
    assert find_needs_manual_review(report, adoptions) == ["t1"]


def test_collect_possible_metadata_tags_any_classification():
    report = {
        "tags": [
            _tag(id="t1", classification="new_theme_candidate", possible_metadata_tags=["Removal: Spot"]),
            _tag(id="t2", classification="not_applicable"),
        ]
    }
    assert collect_possible_metadata_tag_adoptions(report) == {"t1": ["Removal: Spot"]}


def test_resolve_target_column_existing_tag_uses_its_column():
    vocab = {"removal": "themeTags", "token detail: x": "metadataTags"}
    assert resolve_target_column("Removal", vocab, {}) == "themeTags"
    assert resolve_target_column("Token Detail: X", vocab, {}) == "metadataTags"


def test_resolve_target_column_new_tag_uses_override():
    assert resolve_target_column("Brand New Thing", {}, {"brand new thing": "metadata"}) == "metadataTags"


def test_resolve_target_column_new_tag_uses_classify_tag_heuristic():
    assert resolve_target_column("Bracket: Game Changer", {}, {}) == "metadataTags"
    assert resolve_target_column("Spellslinger Synergy", {}, {}) == "themeTags"


def test_load_classification_overrides_missing_file_returns_empty(tmp_path):
    assert load_classification_overrides(tmp_path / "missing.yml") == {}


def test_load_classification_overrides_normalizes_keys(tmp_path):
    path = tmp_path / "overrides.yml"
    path.write_text("Brand New Thing: Metadata\n", encoding="utf-8")
    assert load_classification_overrides(path) == {"brand new thing": "metadata"}


def _make_df():
    return pd.DataFrame([
        {"scryfallID": "sid-1", "themeTags": ["Ramp"], "metadataTags": []},
        {"scryfallID": "sid-2", "themeTags": ["Removal"], "metadataTags": ["Token Detail: X"]},
        {"scryfallID": "sid-3", "themeTags": [], "metadataTags": []},
    ])


def _make_bulk_tags():
    return [
        {
            "id": "t1",
            "taggings": [{"oracle_id": "oid-1"}, {"oracle_id": "oid-2"}],
        },
        {
            "id": "t2",
            "taggings": [{"oracle_id": "oid-3"}],
        },
    ]


def test_apply_adoptions_dry_run_does_not_modify_df(monkeypatch, tmp_path):
    import code.scripts.apply_oracle_tag_adoptions as mod

    bulk_data_path = tmp_path / "scryfall_bulk_data.json"
    bulk_data_path.write_text(json.dumps([
        {"id": "sid-1", "oracle_id": "oid-1"},
        {"id": "sid-2", "oracle_id": "oid-2"},
        {"id": "sid-3", "oracle_id": "oid-3"},
    ]), encoding="utf-8")
    monkeypatch.setattr("code.scripts.compare_oracle_tags.LOCAL_BULK_DATA_PATH", bulk_data_path)

    df = _make_df()
    report = {
        "tags": [
            # t1's taggings (oid-1, oid-2) resolve to rows 0 and 1.
            _tag(id="t1", classification="consolidation_candidate", consolidate_to=["New Theme Tag"]),
            # t2's tagging (oid-3) resolves to row 2 only.
            _tag(id="t2", classification="new_theme_candidate", possible_metadata_tags=["Removal: Spot"]),
        ]
    }
    result, summary = mod.apply_adoptions(df, report, _make_bulk_tags(), {}, dry_run=True)

    assert result is df
    assert list(df.loc[0, "themeTags"]) == ["Ramp"]
    assert summary["cards_affected"] == 3
    assert summary["tag_applications"] == 3
    assert summary["newly_created_tags"] == {"New Theme Tag": "themeTags", "Removal: Spot": "metadataTags"}


def test_apply_adoptions_applies_and_dedupes(monkeypatch, tmp_path):
    import code.scripts.apply_oracle_tag_adoptions as mod

    bulk_data_path = tmp_path / "scryfall_bulk_data.json"
    bulk_data_path.write_text(json.dumps([
        {"id": "sid-1", "oracle_id": "oid-1"},
        {"id": "sid-2", "oracle_id": "oid-2"},
        {"id": "sid-3", "oracle_id": "oid-3"},
    ]), encoding="utf-8")
    monkeypatch.setattr("code.scripts.compare_oracle_tags.LOCAL_BULK_DATA_PATH", bulk_data_path)

    df = _make_df()
    report = {
        "tags": [
            # "Ramp" already on sid-1's themeTags; must not duplicate.
            _tag(id="t1", classification="consolidation_candidate", consolidate_to=["Ramp"]),
            # Brand-new metadata tag applied to sid-3 only.
            _tag(id="t2", classification="new_theme_candidate", possible_metadata_tags=["Removal: Spot"]),
        ]
    }
    result, summary = mod.apply_adoptions(df, report, _make_bulk_tags(), {}, dry_run=False)

    assert list(result.loc[0, "themeTags"]) == ["Ramp"]
    assert list(result.loc[1, "themeTags"]) == ["Ramp", "Removal"]
    assert list(result.loc[2, "metadataTags"]) == ["Removal: Spot"]
    assert summary["newly_created_tags"] == {"Removal: Spot": "metadataTags"}
