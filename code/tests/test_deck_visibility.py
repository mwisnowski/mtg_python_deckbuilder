from __future__ import annotations

import json

from code.web.services.deck_visibility import (
    DEFAULT_VISIBILITY,
    get_deck_visibility,
    resolve_visibility_for_write,
    set_deck_visibility,
)


def _write_sidecar(csv_path, meta: dict | None = None) -> None:
    sidecar = csv_path.with_suffix(".summary.json")
    payload = {"meta": meta or {}, "summary": {}}
    sidecar.write_text(json.dumps(payload), encoding="utf-8")


def test_missing_sidecar_defaults_private(tmp_path):
    csv_path = tmp_path / "Deck.csv"
    assert get_deck_visibility(csv_path) == DEFAULT_VISIBILITY == "private"


def test_missing_visibility_key_defaults_private(tmp_path):
    csv_path = tmp_path / "Deck.csv"
    _write_sidecar(csv_path, {"commander": "Test"})
    assert get_deck_visibility(csv_path) == "private"


def test_set_and_get_visibility_roundtrip(tmp_path):
    csv_path = tmp_path / "Deck.csv"
    _write_sidecar(csv_path, {"commander": "Test"})
    set_deck_visibility(csv_path, "public")
    assert get_deck_visibility(csv_path) == "public"


def test_set_visibility_invalid_raises(tmp_path):
    csv_path = tmp_path / "Deck.csv"
    _write_sidecar(csv_path, {"commander": "Test"})
    try:
        set_deck_visibility(csv_path, "bogus")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_set_visibility_missing_sidecar_raises(tmp_path):
    csv_path = tmp_path / "Deck.csv"
    try:
        set_deck_visibility(csv_path, "public")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_resolve_visibility_for_write_preserves_existing(tmp_path):
    csv_path = tmp_path / "Deck.csv"
    _write_sidecar(csv_path, {"commander": "Test", "visibility": "unlisted"})
    assert resolve_visibility_for_write(csv_path) == "unlisted"


def test_resolve_visibility_for_write_new_sidecar_uses_fallback(tmp_path):
    csv_path = tmp_path / "Deck.csv"
    assert resolve_visibility_for_write(csv_path) == DEFAULT_VISIBILITY
    assert resolve_visibility_for_write(csv_path, fallback="public") == "public"


def test_set_visibility_preserves_other_meta_keys(tmp_path):
    csv_path = tmp_path / "Deck.csv"
    _write_sidecar(csv_path, {"commander": "Test", "tags": ["Aggro"]})
    set_deck_visibility(csv_path, "unlisted")
    sidecar = csv_path.with_suffix(".summary.json")
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["meta"]["commander"] == "Test"
    assert payload["meta"]["tags"] == ["Aggro"]
    assert payload["meta"]["visibility"] == "unlisted"


# ---------------------------------------------------------------------------
# Milestone 6: profile default visibility fallback via deck_dir
# ---------------------------------------------------------------------------

def test_resolve_visibility_for_write_uses_profile_default(tmp_path, monkeypatch):
    import code.web.services.user_db as user_db
    monkeypatch.setattr(user_db, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(user_db, "_DB_PATH", tmp_path / "users.db")
    user_db.init_db()
    user = user_db.create_user("dana", "dana@example.com", "password123")
    user_db.set_default_visibility(user["id"], "public")

    deck_dir = tmp_path / "deck_files" / user["id"]
    deck_dir.mkdir(parents=True)
    csv_path = deck_dir / "Deck.csv"
    assert resolve_visibility_for_write(csv_path, deck_dir=deck_dir) == "public"


def test_resolve_visibility_for_write_falls_back_when_no_profile(tmp_path):
    deck_dir = tmp_path / "deck_files" / "guest"
    deck_dir.mkdir(parents=True)
    csv_path = deck_dir / "Deck.csv"
    assert resolve_visibility_for_write(csv_path, deck_dir=deck_dir) == "private"


# ---------------------------------------------------------------------------
# Milestone 7: wizard per-build override takes precedence
# ---------------------------------------------------------------------------

def test_resolve_visibility_for_write_override_beats_profile_default(tmp_path, monkeypatch):
    import code.web.services.user_db as user_db
    monkeypatch.setattr(user_db, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(user_db, "_DB_PATH", tmp_path / "users.db")
    user_db.init_db()
    user = user_db.create_user("erin", "erin@example.com", "password123")
    user_db.set_default_visibility(user["id"], "private")

    deck_dir = tmp_path / "deck_files" / user["id"]
    deck_dir.mkdir(parents=True)
    csv_path = deck_dir / "Deck.csv"
    # Profile default is "private" but the wizard override should win.
    assert resolve_visibility_for_write(csv_path, deck_dir=deck_dir, override="public") == "public"


def test_resolve_visibility_for_write_override_beats_existing_sidecar(tmp_path):
    csv_path = tmp_path / "Deck.csv"
    _write_sidecar(csv_path, {"commander": "Test", "visibility": "unlisted"})
    assert resolve_visibility_for_write(csv_path, override="private") == "private"


def test_resolve_visibility_for_write_invalid_override_ignored(tmp_path):
    csv_path = tmp_path / "Deck.csv"
    assert resolve_visibility_for_write(csv_path, override="bogus") == DEFAULT_VISIBILITY
