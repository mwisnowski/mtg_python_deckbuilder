import pandas as pd

from file_setup.setup_utils import filter_dataframe


def _record(name: str, security_stamp: str) -> dict[str, object]:
    return {
        "name": name,
        "faceName": name,
        "edhrecRank": 100,
        "colorIdentity": "G",
        "colors": "G",
        "manaCost": "{G}",
        "manaValue": 1,
        "type": "Creature",
        "layout": "normal",
        "text": "",
        "power": "1",
        "toughness": "1",
        "keywords": "",
        "side": "a",
        "availability": "paper,arena",
        "promoTypes": "",
        "securityStamp": security_stamp,
        "printings": "RNA",
    }


def test_filter_dataframe_removes_acorn_and_heart_security_stamps() -> None:
    df = pd.DataFrame(
        [
            _record("Acorn Card", "Acorn"),
            _record("Heart Card", "heart"),
            _record("Legal Card", ""),
        ]
    )

    filtered = filter_dataframe(df, banned_cards=[])

    assert list(filtered["name"]) == ["Legal Card"]
