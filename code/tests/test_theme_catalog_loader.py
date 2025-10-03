from __future__ import annotations

from pathlib import Path

import pytest

from code.deck_builder.theme_catalog_loader import ThemeCatalogEntry, load_theme_catalog


def _write_catalog(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_load_theme_catalog_basic(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    catalog_path = tmp_path / "theme_catalog.csv"
    _write_catalog(
        catalog_path,
        [
            "# theme_catalog version=abc123 generated_at=2025-01-02T00:00:00Z",
            "theme,source_count,commander_count,card_count,last_generated_at,version",
            "Lifegain,3,1,2,2025-01-02T00:00:00Z,abc123",
            "Token Swarm,5,2,3,2025-01-02T00:00:00Z,abc123",
        ],
    )

    with caplog.at_level("INFO"):
        entries, version = load_theme_catalog(catalog_path)

    assert version == "abc123"
    assert entries == [
        ThemeCatalogEntry(theme="Lifegain", commander_count=1, card_count=2),
        ThemeCatalogEntry(theme="Token Swarm", commander_count=2, card_count=3),
    ]
    log_messages = {record.message for record in caplog.records}
    assert any("theme_catalog_loaded" in message for message in log_messages)


def test_load_theme_catalog_empty_file(tmp_path: Path) -> None:
    catalog_path = tmp_path / "theme_catalog.csv"
    _write_catalog(catalog_path, ["# theme_catalog version=empty"])

    entries, version = load_theme_catalog(catalog_path)

    assert entries == []
    assert version == "empty"


def test_load_theme_catalog_missing_columns(tmp_path: Path) -> None:
    catalog_path = tmp_path / "theme_catalog.csv"
    _write_catalog(
        catalog_path,
        [
            "# theme_catalog version=missing",
            "theme,card_count,last_generated_at,version",
            "Lifegain,2,2025-01-02T00:00:00Z,missing",
        ],
    )

    with pytest.raises(ValueError):
        load_theme_catalog(catalog_path)
