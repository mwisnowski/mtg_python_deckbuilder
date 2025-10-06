from __future__ import annotations

from pathlib import Path

import pytest

from code.deck_builder.background_loader import (
    BackgroundCatalog,
    BackgroundCard,
    clear_background_cards_cache,
    load_background_cards,
)


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    clear_background_cards_cache()


def _write_csv(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / "background_cards.csv"
    path.write_text(rows, encoding="utf-8")
    return path


def test_load_background_cards_filters_non_backgrounds(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO")
    csv_text = """# version=123 count=2\nname,faceName,type,text,themeTags,colorIdentity,colors,manaCost,manaValue,keywords,edhrecRank,layout,side\nAcolyte of Bahamut,,Legendary Enchantment — Background,Commander creatures you own have menace.,['Backgrounds Matter'],G,G,{1}{G},2.0,,7570,normal,\nNot a Background,,Legendary Creature — Elf,Partner with Foo,,G,G,{3}{G},4.0,,5000,normal,\n"""
    path = _write_csv(tmp_path, csv_text)
    catalog = load_background_cards(path)

    assert isinstance(catalog, BackgroundCatalog)
    assert [card.display_name for card in catalog.entries] == ["Acolyte of Bahamut"]
    assert catalog.version == "123"
    assert "background_cards_loaded" in caplog.text


def test_load_background_cards_empty_file(tmp_path: Path) -> None:
    csv_text = """# version=empty count=0\nname,faceName,type,text,themeTags,colorIdentity,colors,manaCost,manaValue,keywords,edhrecRank,layout,side\n"""
    path = _write_csv(tmp_path, csv_text)
    catalog = load_background_cards(path)

    assert catalog.version == "empty"
    assert catalog.entries == tuple()


def test_load_background_cards_deduplicates_by_name(tmp_path: Path) -> None:
    csv_text = (
        "# version=dedupe count=2\n"
        "name,faceName,type,text,themeTags,colorIdentity,colors,manaCost,manaValue,keywords,edhrecRank,layout,side\n"
        "Guild Artisan,,Legendary Enchantment — Background,Commander creatures you own have treasure.,['Backgrounds Matter'],R,R,{1}{R},2.0,,3366,normal,\n"
        "Guild Artisan,,Legendary Enchantment — Background,Commander creatures you own have treasure tokens.,['Backgrounds Matter'],R,R,{1}{R},2.0,,3366,normal,\n"
    )
    path = _write_csv(tmp_path, csv_text)
    catalog = load_background_cards(path)

    assert len(catalog.entries) == 1
    card = catalog.entries[0]
    assert isinstance(card, BackgroundCard)
    assert card.display_name == "Guild Artisan"
    assert "treasure" in card.oracle_text.lower()
    assert catalog.get("guild artisan") is card
