from __future__ import annotations

from pathlib import Path

import pytest

from code.headless_runner import resolve_additional_theme_inputs as _resolve_additional_theme_inputs


def _parse_theme_list(themes_str: str) -> list[str]:
    """Parse semicolon-separated theme list (helper for tests)."""
    if not themes_str:
        return []
    themes = [t.strip() for t in themes_str.split(';') if t.strip()]
    # Deduplicate while preserving order (case-insensitive)
    seen = set()
    result = []
    for theme in themes:
        key = theme.lower()
        if key not in seen:
            seen.add(key)
            result.append(theme)
    return result


def _write_catalog(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# theme_catalog version=test_version",
                "theme,commander_count,card_count",
                "Lifegain,5,20",
                "Token Swarm,3,15",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_parse_theme_list_handles_semicolons() -> None:
    assert _parse_theme_list("Lifegain;Token Swarm ; lifegain") == ["Lifegain", "Token Swarm"]


def test_resolve_additional_themes_permissive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    catalog_path = tmp_path / "theme_catalog.csv"
    _write_catalog(catalog_path)
    monkeypatch.setenv("THEME_CATALOG_PATH", str(catalog_path))

    resolution = _resolve_additional_theme_inputs(
        ["Lifegain", "Unknown"],
        mode="permissive",
        commander_tags=["Lifegain"],
    )

    assert resolution.mode == "permissive"
    assert resolution.catalog_version == "test_version"
    # Lifegain deduped against commander tag
    assert resolution.resolved == []
    assert resolution.matches[0]["matched"] == "Lifegain"
    assert len(resolution.unresolved) == 1
    assert resolution.unresolved[0]["input"] == "Unknown"
    assert resolution.unresolved[0]["reason"] in {"no_match", "suggestions", "no_candidates"}


def test_resolve_additional_themes_strict_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    catalog_path = tmp_path / "theme_catalog.csv"
    _write_catalog(catalog_path)
    monkeypatch.setenv("THEME_CATALOG_PATH", str(catalog_path))

    with pytest.raises(ValueError) as exc:
        _resolve_additional_theme_inputs(["Mystery"], mode="strict")
    assert "Mystery" in str(exc.value)


def test_resolve_additional_themes_fuzzy_correction(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    catalog_path = tmp_path / "theme_catalog.csv"
    _write_catalog(catalog_path)
    monkeypatch.setenv("THEME_CATALOG_PATH", str(catalog_path))

    resolution = _resolve_additional_theme_inputs(["lifgain"], mode="permissive")

    assert resolution.resolved == ["Lifegain"]
    assert resolution.fuzzy_corrections == {"lifgain": "Lifegain"}
    assert not resolution.unresolved
