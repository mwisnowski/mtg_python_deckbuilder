from __future__ import annotations

import pandas as pd
import pytest

from code.file_setup.token_setup import build_tokens_parquet


def _raw_row(**overrides):
    base = {
        "name": None, "layout": None, "type": None, "text": "",
        "power": None, "toughness": None, "colors": "", "colorIdentity": "",
        "subtypes": "", "keywords": None, "relatedCards": None, "side": None, "faceName": None,
    }
    base.update(overrides)
    return base


@pytest.fixture()
def raw_tokens_path(tmp_path):
    rows = [
        # Two reprints of the same "Elemental" identity, differing only by relatedCards
        # (must be unioned onto one row).
        _raw_row(
            name="Elemental", layout="token", type="Token Creature — Elemental",
            power="1", toughness="1", colors="R", colorIdentity="R", subtypes="Elemental",
            keywords="Haste", relatedCards='{"reverseRelated":["Card A"]}',
        ),
        _raw_row(
            name="Elemental", layout="token", type="Token Creature — Elemental",
            power="1", toughness="1", colors="R", colorIdentity="R", subtypes="Elemental",
            relatedCards='{"reverseRelated":["Card B"]}',
        ),
        # Same name, different power/toughness -> must survive as a distinct identity.
        _raw_row(
            name="Elemental", layout="token", type="Token Creature — Elemental",
            power="2", toughness="2", colors="G", colorIdentity="G", subtypes="Elemental",
            relatedCards='{"reverseRelated":["Card C"]}',
        ),
        # No known creator card (e.g. a convention/game-night promo token) -- must be
        # filtered out entirely, since it has no practical use for deck-building token surfacing.
        _raw_row(
            name="Filler Token", layout="token", type="Token Creature — Filler",
            power="1", toughness="1", colors="C", colorIdentity="C", subtypes="Filler",
            relatedCards=None,
        ),
        # Double-faced token: two side rows collapsing into one logical row.
        _raw_row(
            name="Snake // Zombie", layout="double_faced_token",
            type="Token Creature — Snake", text="Deathtouch",
            power="1", toughness="1", colors="B", colorIdentity="B", subtypes="Snake",
            relatedCards=None, side="a", faceName="Snake",
        ),
        _raw_row(
            name="Snake // Zombie", layout="double_faced_token",
            type="Token Creature — Zombie", text="",
            power="2", toughness="2", colors="B", colorIdentity="B", subtypes="Zombie",
            relatedCards='{"reverseRelated":["Some Card"]}', side="b", faceName="Zombie",
        ),
        # Same identity reprinted with a corrected subtype and an updated oracle-text
        # template ("enters the battlefield" -> "enters", self-name -> "this token") --
        # must collapse to one row instead of showing as a near-duplicate.
        _raw_row(
            name="Wizard Token", layout="token", type="Token Creature — Zombie Naga Wizard",
            text="When Wizard Token enters the battlefield, draw a card.",
            power="4", toughness="4", colors="B", colorIdentity="B", subtypes="Zombie Naga Wizard",
            relatedCards='{"reverseRelated":["Old Printing Card"]}',
        ),
        _raw_row(
            name="Wizard Token", layout="token", type="Token Creature — Zombie Snake Wizard",
            text="When this token enters, draw a card.",
            power="4", toughness="4", colors="B", colorIdentity="B", subtypes="Zombie Snake Wizard",
            relatedCards='{"reverseRelated":["New Printing Card"]}',
        ),
        # Emblem, deduped by (name, text).
        _raw_row(
            name="Test Emblem", layout="emblem", type="Emblem — Test",
            text="Test emblem text.", relatedCards='{"reverseRelated":["Creator Card"]}',
        ),
        _raw_row(
            name="Test Emblem", layout="emblem", type="Emblem — Test",
            text="Test emblem text.", relatedCards='{"reverseRelated":["Second Creator"]}',
        ),
        # Out-of-scope layout -- must be excluded entirely.
        _raw_row(
            name="Some Normal Card", layout="normal", type="Creature — Human",
            power="1", toughness="1", colors="W", colorIdentity="W", subtypes="Human",
        ),
    ]
    df = pd.DataFrame(rows)
    path = tmp_path / "tokens.parquet"
    df.to_parquet(path, index=False)
    return path


def test_build_tokens_parquet_missing_raw_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_tokens_parquet(raw_path=str(tmp_path / "missing.parquet"), output_path=str(tmp_path / "out.parquet"))


def test_build_tokens_parquet_excludes_out_of_scope_layouts(raw_tokens_path, tmp_path):
    result = build_tokens_parquet(raw_path=str(raw_tokens_path), output_path=str(tmp_path / "out.parquet"))
    assert "Some Normal Card" not in result["name"].values


def test_build_tokens_parquet_excludes_entries_without_related_cards(raw_tokens_path, tmp_path):
    result = build_tokens_parquet(raw_path=str(raw_tokens_path), output_path=str(tmp_path / "out.parquet"))
    assert "Filler Token" not in result["name"].values


def test_build_tokens_parquet_identity_dedup_and_related_cards_union(raw_tokens_path, tmp_path):
    result = build_tokens_parquet(raw_path=str(raw_tokens_path), output_path=str(tmp_path / "out.parquet"))
    elementals = result[result["name"] == "Elemental"]
    assert len(elementals) == 2  # 1/1 and 2/2 survive as distinct identities

    one_one = elementals[elementals["power"] == "1"].iloc[0]
    assert set(one_one["relatedCards"]) == {"Card A", "Card B"}
    assert one_one["keywords"] == ["Haste"]


def test_build_tokens_parquet_merges_oracle_templating_variants(raw_tokens_path, tmp_path):
    result = build_tokens_parquet(raw_path=str(raw_tokens_path), output_path=str(tmp_path / "out.parquet"))
    variants = result[result["name"] == "Wizard Token"]
    assert len(variants) == 1

    row = variants.iloc[0]
    assert row["text"] == "When this token enters, draw a card."  # modern wording preferred
    assert set(row["relatedCards"]) == {"Old Printing Card", "New Printing Card"}


def test_build_tokens_parquet_collapses_dual_face_rows(raw_tokens_path, tmp_path):
    result = build_tokens_parquet(raw_path=str(raw_tokens_path), output_path=str(tmp_path / "out.parquet"))
    dfc = result[result["name"] == "Snake // Zombie"]
    assert len(dfc) == 1

    row = dfc.iloc[0]
    assert row["face_a_type"] == "Token Creature — Snake"
    assert row["face_a_power"] == "1"
    assert row["face_b_type"] == "Token Creature — Zombie"
    assert row["face_b_power"] == "2"
    assert row["relatedCards"] == ["Some Card"]


def test_build_tokens_parquet_emblem_dedup(raw_tokens_path, tmp_path):
    result = build_tokens_parquet(raw_path=str(raw_tokens_path), output_path=str(tmp_path / "out.parquet"))
    emblems = result[result["name"] == "Test Emblem"]
    assert len(emblems) == 1
    assert emblems.iloc[0]["isEmblem"] is True or bool(emblems.iloc[0]["isEmblem"]) is True
    assert set(emblems.iloc[0]["relatedCards"]) == {"Creator Card", "Second Creator"}


def test_build_tokens_parquet_is_idempotent(raw_tokens_path, tmp_path):
    out_path = str(tmp_path / "out.parquet")
    first = build_tokens_parquet(raw_path=str(raw_tokens_path), output_path=out_path)
    second = build_tokens_parquet(raw_path=str(raw_tokens_path), output_path=out_path)
    assert first.equals(second)


def test_tag_token_catalog_own_fields(raw_tokens_path, tmp_path):
    from code.file_setup.token_setup import tag_token_catalog_own_fields

    catalog = build_tokens_parquet(raw_path=str(raw_tokens_path), output_path=str(tmp_path / "out.parquet"))
    tagged = tag_token_catalog_own_fields(catalog)

    one_one = tagged[(tagged["name"] == "Elemental") & (tagged["power"] == "1")].iloc[0]
    assert one_one["metadataTags"] == ["Token Detail: 1/1 Red Elemental - Haste"]
    assert "Elemental Token" in one_one["themeTags"]
    assert "Creature Token" in one_one["themeTags"]

    emblem = tagged[tagged["name"] == "Test Emblem"].iloc[0]
    assert emblem["metadataTags"] == []
    assert emblem["themeTags"] == ["Emblem"]

    dfc = tagged[tagged["name"] == "Snake // Zombie"].iloc[0]
    assert "Token Detail: 1/1 Black Snake - Deathtouch" in dfc["metadataTags"]
    assert "Token Detail: 2/2 Black Zombie" in dfc["metadataTags"]
    assert "Snake Token" in dfc["themeTags"]
    assert "Zombie Token" in dfc["themeTags"]


def test_apply_emblem_backreferences(raw_tokens_path, tmp_path):
    from code.file_setup.token_setup import apply_emblem_backreferences

    tokens_df = build_tokens_parquet(raw_path=str(raw_tokens_path), output_path=str(tmp_path / "out.parquet"))
    all_cards_df = pd.DataFrame({
        "name": ["Creator Card", "Second Creator", "Unrelated Card"],
        "themeTags": [[], [], []],
        "metadataTags": [[], [], []],
    })

    result = apply_emblem_backreferences(all_cards_df, tokens_df)

    creator = result[result["name"] == "Creator Card"].iloc[0]
    assert creator["metadataTags"] == ["Emblem: Test Emblem"]
    assert creator["themeTags"] == ["Emblem"]

    unrelated = result[result["name"] == "Unrelated Card"].iloc[0]
    assert unrelated["metadataTags"] == []
    assert unrelated["themeTags"] == []
