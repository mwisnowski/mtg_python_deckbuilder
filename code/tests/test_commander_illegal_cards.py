import json
from pathlib import Path

from file_setup.setup import refresh_card_lists_from_bulk


def test_refresh_card_lists_from_bulk_computes_commander_illegal(tmp_path, monkeypatch):
    """Cards not_legal on every printing (e.g. Aswan Jaguar) should land in
    commander_illegal_cards.json, but a card that's legal on at least one
    printing (even if another promo printing is not_legal), or that's only
    not_legal because it hasn't been released yet, should not.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config" / "card_lists").mkdir(parents=True)

    bulk_lines = [
        "[",
        json.dumps({"name": "Aswan Jaguar", "game_changer": False, "legalities": {"commander": "not_legal"}}) + ",",
        json.dumps({"name": "Sol Ring", "game_changer": False, "legalities": {"commander": "legal"}}) + ",",
        json.dumps({"name": "Sol Ring", "game_changer": False, "legalities": {"commander": "not_legal"}}) + ",",
        json.dumps({"name": "Balance", "game_changer": False, "legalities": {"commander": "banned"}}) + ",",
        json.dumps({"name": "Gaea's Cradle", "game_changer": True, "legalities": {"commander": "legal"}}) + ",",
        # Not-yet-released prerelease reprint: not_legal everywhere, but should
        # not be treated as permanently illegal since it just hasn't shipped yet.
        json.dumps({"name": "Duskwatch Hunter", "game_changer": False, "legalities": {"commander": "not_legal"}, "released_at": "2099-01-01"}),
        "]",
    ]
    bulk_path = tmp_path / "bulk.json"
    bulk_path.write_text("\n".join(bulk_lines), encoding="utf-8")

    refresh_card_lists_from_bulk(str(bulk_path), output_func=lambda *_: None)

    illegal_data = json.loads((tmp_path / "config" / "card_lists" / "commander_illegal_cards.json").read_text())
    assert illegal_data["cards"] == ["Aswan Jaguar"]

    banned_data = json.loads((tmp_path / "config" / "card_lists" / "banned_cards.json").read_text())
    assert banned_data["cards"] == ["Balance"]

    gc_data = json.loads((tmp_path / "config" / "card_lists" / "game_changers.json").read_text())
    assert gc_data["cards"] == ["Gaea's Cradle"]
