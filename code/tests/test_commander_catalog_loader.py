from __future__ import annotations

import time
from pathlib import Path

import pytest

from web.services import commander_catalog_loader as loader


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "csv_files" / "testdata"


def _set_csv_dir(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setenv("CSV_FILES_DIR", str(path))
    loader.clear_commander_catalog_cache()


def test_commander_catalog_basic_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_csv_dir(monkeypatch, FIXTURE_DIR)

    catalog = loader.load_commander_catalog()

    assert catalog.source_path.name == "commander_cards.csv"
    assert len(catalog.entries) == 4

    krenko = catalog.by_slug["krenko-mob-boss"]
    assert krenko.display_name == "Krenko, Mob Boss"
    assert krenko.color_identity == ("R",)
    assert krenko.color_identity_key == "R"
    assert not krenko.is_colorless
    assert krenko.themes == ("Goblin Kindred",)
    assert "goblin kindred" in krenko.theme_tokens
    assert "version=small" in krenko.image_small_url
    assert "exact=Krenko%2C%20Mob%20Boss" in krenko.image_small_url

    traxos = catalog.by_slug["traxos-scourge-of-kroog"]
    assert traxos.is_colorless
    assert traxos.color_identity == ()
    assert traxos.color_identity_key == "C"

    atraxa = catalog.by_slug["atraxa-praetors-voice"]
    assert atraxa.color_identity == ("W", "U", "B", "G")
    assert atraxa.color_identity_key == "WUBG"
    assert atraxa.is_partner is False
    assert atraxa.supports_backgrounds is False


def test_commander_catalog_cache_invalidation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_csv = FIXTURE_DIR / "commander_cards.csv"
    work_dir = tmp_path / "csv"
    work_dir.mkdir()
    target_csv = work_dir / "commander_cards.csv"
    target_csv.write_text(fixture_csv.read_text(encoding="utf-8"), encoding="utf-8")

    _set_csv_dir(monkeypatch, work_dir)

    first = loader.load_commander_catalog()
    again = loader.load_commander_catalog()
    assert again is first

    time.sleep(1.1)  # ensure mtime tick on systems with 1s resolution
    target_csv.write_text(
        fixture_csv.read_text(encoding="utf-8")
        + "\"Zada, Hedron Grinder\",\"Zada, Hedron Grinder\",9999,R,R,{3}{R},4,\"Legendary Creature — Goblin\",\"['Goblin']\",\"Test\",3,3,,\"['Goblin Kindred']\",normal,\n",
        encoding="utf-8",
    )

    updated = loader.load_commander_catalog()
    assert updated is not first
    assert "zada-hedron-grinder" in updated.by_slug
