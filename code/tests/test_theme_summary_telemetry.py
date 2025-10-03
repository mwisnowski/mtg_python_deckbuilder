from __future__ import annotations

from deck_builder.summary_telemetry import (
    _reset_metrics_for_test,
    get_theme_metrics,
    record_theme_summary,
)


def setup_function() -> None:
    _reset_metrics_for_test()


def teardown_function() -> None:
    _reset_metrics_for_test()


def test_record_theme_summary_tracks_user_themes() -> None:
    payload = {
        "commanderThemes": ["Lifegain"],
        "userThemes": ["Angels", "Life Gain"],
        "requested": ["Angels"],
        "resolved": ["angels"],
        "unresolved": [],
        "mode": "AND",
        "weight": 1.3,
        "themeCatalogVersion": "test-cat",
    }
    record_theme_summary(payload)
    metrics = get_theme_metrics()
    assert metrics["total_builds"] == 1
    assert metrics["with_user_themes"] == 1
    summary = metrics["last_summary"]
    assert summary is not None
    assert summary["commanderThemes"] == ["Lifegain"]
    assert summary["userThemes"] == ["Angels", "Life Gain"]
    assert summary["mergedThemes"] == ["Lifegain", "Angels", "Life Gain"]
    assert summary["unresolvedCount"] == 0
    assert metrics["top_user_themes"][0]["theme"] in {"Angels", "Life Gain"}


def test_record_theme_summary_without_user_themes() -> None:
    payload = {
        "commanderThemes": ["Artifacts"],
        "userThemes": [],
        "requested": [],
        "resolved": [],
        "unresolved": [],
        "mode": "AND",
        "weight": 1.0,
    }
    record_theme_summary(payload)
    metrics = get_theme_metrics()
    assert metrics["total_builds"] == 1
    assert metrics["with_user_themes"] == 0
    summary = metrics["last_summary"]
    assert summary is not None
    assert summary["commanderThemes"] == ["Artifacts"]
    assert summary["userThemes"] == []
    assert summary["mergedThemes"] == ["Artifacts"]
    assert summary["unresolvedCount"] == 0
