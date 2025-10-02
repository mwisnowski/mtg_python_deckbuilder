from __future__ import annotations

import pandas as pd

from code.tagging.multi_face_merger import merge_multi_face_rows


def _build_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "name": "Eddie Brock // Venom, Lethal Protector",
                "faceName": "Eddie Brock",
                "edhrecRank": 12345.0,
                "colorIdentity": "B",
                "colors": "B",
                "manaCost": "{3}{B}{B}",
                "manaValue": 5.0,
                "type": "Legendary Creature — Human",
                "creatureTypes": ["Human"],
                "text": "When Eddie Brock enters...",
                "power": 3,
                "toughness": 4,
                "keywords": "Transform",
                "themeTags": ["Aggro", "Control"],
                "layout": "transform",
                "side": "a",
                "roleTags": ["Value Engine"],
            },
            {
                "name": "Eddie Brock // Venom, Lethal Protector",
                "faceName": "Venom, Lethal Protector",
                "edhrecRank": 12345.0,
                "colorIdentity": "B",
                "colors": "B",
                "manaCost": "",
                "manaValue": 5.0,
                "type": "Legendary Creature — Symbiote",
                "creatureTypes": ["Symbiote"],
                "text": "Whenever Venom attacks...",
                "power": 5,
                "toughness": 5,
                "keywords": "Menace, Transform",
                "themeTags": ["Menace", "Legends Matter"],
                "layout": "transform",
                "side": "b",
                "roleTags": ["Finisher"],
            },
            {
                "name": "Bonecrusher Giant // Stomp",
                "faceName": "Bonecrusher Giant",
                "edhrecRank": 6789.0,
                "colorIdentity": "R",
                "colors": "R",
                "manaCost": "{2}{R}",
                "manaValue": 3.0,
                "type": "Creature — Giant",
                "creatureTypes": ["Giant"],
                "text": "Whenever this creature becomes the target...",
                "power": 4,
                "toughness": 3,
                "keywords": "",
                "themeTags": ["Aggro"],
                "layout": "adventure",
                "side": "a",
                "roleTags": [],
            },
            {
                "name": "Bonecrusher Giant // Stomp",
                "faceName": "Stomp",
                "edhrecRank": 6789.0,
                "colorIdentity": "R",
                "colors": "R",
                "manaCost": "{1}{R}",
                "manaValue": 2.0,
                "type": "Instant — Adventure",
                "creatureTypes": [],
                "text": "Stomp deals 2 damage to any target.",
                "power": None,
                "toughness": None,
                "keywords": "Instant",
                "themeTags": ["Removal"],
                "layout": "adventure",
                "side": "b",
                "roleTags": [],
            },
            {
                "name": "Expansion // Explosion",
                "faceName": "Expansion",
                "edhrecRank": 4321.0,
                "colorIdentity": "U, R",
                "colors": "U, R",
                "manaCost": "{U/R}{U/R}",
                "manaValue": 2.0,
                "type": "Instant",
                "creatureTypes": [],
                "text": "Copy target instant or sorcery spell...",
                "power": None,
                "toughness": None,
                "keywords": "",
                "themeTags": ["Spell Copy"],
                "layout": "split",
                "side": "a",
                "roleTags": ["Copy Enabler"],
            },
            {
                "name": "Expansion // Explosion",
                "faceName": "Explosion",
                "edhrecRank": 4321.0,
                "colorIdentity": "U, R",
                "colors": "U, R",
                "manaCost": "{X}{X}{U}{R}",
                "manaValue": 4.0,
                "type": "Instant",
                "creatureTypes": [],
                "text": "Explosion deals X damage to any target...",
                "power": None,
                "toughness": None,
                "keywords": "",
                "themeTags": ["Burn", "Card Draw"],
                "layout": "split",
                "side": "b",
                "roleTags": ["Finisher"],
            },
            {
                "name": "Persistent Petitioners",
                "faceName": "Persistent Petitioners",
                "edhrecRank": 5555.0,
                "colorIdentity": "U",
                "colors": "U",
                "manaCost": "{1}{U}",
                "manaValue": 2.0,
                "type": "Creature — Human Advisor",
                "creatureTypes": ["Human", "Advisor"],
                "text": "{1}{U}, Tap four untapped Advisors you control: Mill 12.",
                "power": 1,
                "toughness": 3,
                "keywords": "",
                "themeTags": ["Mill"],
                "layout": "normal",
                "side": "",
                "roleTags": ["Mill Enabler"],
            },
        ]
    )


def test_merge_multi_face_rows_combines_themes_and_keywords():
    df = _build_dataframe()

    merged = merge_multi_face_rows(df, "grixis", logger=None)

    # Eddie Brock merge assertions
    eddie = merged[merged["name"] == "Eddie Brock // Venom, Lethal Protector"].iloc[0]
    assert set(eddie["themeTags"]) == {
        "Aggro",
        "Control",
        "Legends Matter",
        "Menace",
    }
    assert set(eddie["creatureTypes"]) == {"Human", "Symbiote"}
    assert eddie["keywords"] == "Menace, Transform"

    assert (merged["faceName"] == "Venom, Lethal Protector").sum() == 0

    # Bonecrusher Giant adventure merge assertions
    bonecrusher = merged[merged["name"] == "Bonecrusher Giant // Stomp"].iloc[0]
    assert set(bonecrusher["themeTags"]) == {"Aggro", "Removal"}
    assert set(bonecrusher["creatureTypes"]) == {"Giant"}
    assert bonecrusher["keywords"] == "Instant"
    assert (merged["faceName"] == "Stomp").sum() == 0

    # Split card merge assertions
    explosion = merged[merged["name"] == "Expansion // Explosion"].iloc[0]
    assert set(explosion["themeTags"]) == {"Spell Copy", "Burn", "Card Draw"}
    assert set(explosion["roleTags"]) == {"Copy Enabler", "Finisher"}
    assert (merged["faceName"] == "Explosion").sum() == 0

    # Persistent Petitioners should remain untouched
    petitioners = merged[merged["name"] == "Persistent Petitioners"].iloc[0]
    assert petitioners["themeTags"] == ["Mill"]
    assert petitioners["roleTags"] == ["Mill Enabler"]
    assert "faceDetails" not in merged.columns
    assert len(merged) == 4


def test_merge_multi_face_rows_is_idempotent():
    df = _build_dataframe()
    once = merge_multi_face_rows(df, "izzet", logger=None)
    twice = merge_multi_face_rows(once, "izzet", logger=None)

    pd.testing.assert_frame_equal(once, twice)