"""Route-level tests for deck visibility access control (Milestones 2-4).

Uses an isolated user DB (tmp_path) and an isolated DECK_EXPORTS directory so
no real data/ or deck_files/ content is touched.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    import code.web.services.user_db as user_db
    monkeypatch.setattr(user_db, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(user_db, "_DB_PATH", tmp_path / "users.db")
    user_db.init_db()
    monkeypatch.setenv("DECK_EXPORTS", str(tmp_path / "deck_files"))
    yield


@pytest.fixture()
def client(_isolated_db, monkeypatch):
    from code.web.services.user_db import ensure_guest_user
    ensure_guest_user()
    from code.web.app import app
    # Each test uses a fresh tmp_path, so the module-level public-decks cache
    # (keyed only by a 60s TTL, not by directory) must be reset per test.
    import code.web.routes.decks as decks_routes
    monkeypatch.setitem(decks_routes._PUBLIC_DECKS_CACHE, "data", None)
    monkeypatch.setitem(decks_routes._PUBLIC_DECKS_CACHE, "ts", 0.0)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _register(client: TestClient, username: str, email: str, password: str = "password123") -> None:
    resp = client.post("/auth/register", data={
        "username": username, "email": email,
        "password": password, "confirm": password,
    }, follow_redirects=False)
    assert resp.status_code == 303


def _write_deck(tmp_path, user_id: str, deck_name: str, visibility: str, commander: str = "Test Commander") -> None:
    deck_dir = tmp_path / "deck_files" / user_id
    deck_dir.mkdir(parents=True, exist_ok=True)
    csv_path = deck_dir / deck_name
    csv_path.write_text("Name,Count,Type\nTest Commander,1,Creature\n", encoding="utf-8")
    sidecar = csv_path.with_suffix(".summary.json")
    payload = {"meta": {"commander": commander, "tags": [], "visibility": visibility}, "summary": {}}
    sidecar.write_text(json.dumps(payload), encoding="utf-8")


def test_private_deck_blocked_for_other_user(client, tmp_path):
    from code.web.services.user_db import get_user_by_username
    _register(client, "alice", "alice@example.com")
    alice = get_user_by_username("alice")
    _write_deck(tmp_path, alice["id"], "Deck.csv", "private")

    client.post("/auth/logout")
    _register(client, "bob", "bob@example.com")

    resp = client.get("/decks/alice/Deck.csv")
    assert resp.status_code == 404


def test_public_deck_visible_to_other_user(client, tmp_path):
    from code.web.services.user_db import get_user_by_username
    _register(client, "alice2", "alice2@example.com")
    alice = get_user_by_username("alice2")
    _write_deck(tmp_path, alice["id"], "Deck.csv", "public")

    client.post("/auth/logout")
    _register(client, "bob2", "bob2@example.com")

    resp = client.get("/decks/alice2/Deck.csv")
    assert resp.status_code == 200
    assert "Test Commander" in resp.text


def test_unlisted_deck_accessible_by_url(client, tmp_path):
    from code.web.services.user_db import get_user_by_username
    _register(client, "alice3", "alice3@example.com")
    alice = get_user_by_username("alice3")
    _write_deck(tmp_path, alice["id"], "Deck.csv", "unlisted")

    client.post("/auth/logout")
    _register(client, "bob3", "bob3@example.com")

    resp = client.get("/decks/alice3/Deck.csv")
    assert resp.status_code == 200


def test_namespaced_url_resolves_for_owner(client, tmp_path):
    from code.web.services.user_db import get_user_by_username
    _register(client, "alice4", "alice4@example.com")
    alice = get_user_by_username("alice4")
    _write_deck(tmp_path, alice["id"], "Deck.csv", "private")

    resp = client.get("/decks/alice4/Deck.csv")
    assert resp.status_code == 200
    assert "Test Commander" in resp.text


def test_unknown_username_returns_404(client):
    resp = client.get("/decks/nobody-here/Deck.csv")
    assert resp.status_code == 404


def test_set_visibility_owner_only(client, tmp_path):
    from code.web.services.user_db import get_user_by_username
    _register(client, "alice5", "alice5@example.com")
    alice = get_user_by_username("alice5")
    _write_deck(tmp_path, alice["id"], "Deck.csv", "private")

    client.post("/auth/logout")
    _register(client, "bob5", "bob5@example.com")

    resp = client.post("/decks/set-visibility", data={"deck_name": "Deck.csv", "visibility": "public"})
    # Bob doesn't own the deck (it lives under alice's dir); his own dir has no such file.
    assert resp.status_code == 404


def test_set_visibility_by_owner_succeeds(client, tmp_path):
    from code.web.services.user_db import get_user_by_username
    _register(client, "alice6", "alice6@example.com")
    alice = get_user_by_username("alice6")
    _write_deck(tmp_path, alice["id"], "Deck.csv", "private")

    resp = client.post("/decks/set-visibility", data={"deck_name": "Deck.csv", "visibility": "public"})
    assert resp.status_code == 200

    from code.web.services.deck_visibility import get_deck_visibility
    csv_path = tmp_path / "deck_files" / alice["id"] / "Deck.csv"
    assert get_deck_visibility(csv_path) == "public"


def test_set_visibility_invalid_value_rejected(client, tmp_path):
    from code.web.services.user_db import get_user_by_username
    _register(client, "alice7", "alice7@example.com")
    alice = get_user_by_username("alice7")
    _write_deck(tmp_path, alice["id"], "Deck.csv", "private")

    resp = client.post("/decks/set-visibility", data={"deck_name": "Deck.csv", "visibility": "bogus"})
    assert resp.status_code == 400


def test_owner_view_shows_visibility_selector(client, tmp_path):
    from code.web.services.user_db import get_user_by_username
    _register(client, "alice8", "alice8@example.com")
    alice = get_user_by_username("alice8")
    _write_deck(tmp_path, alice["id"], "Deck.csv", "private")

    resp = client.get("/decks/view?name=Deck.csv")
    assert resp.status_code == 200
    assert 'id="deck-visibility"' in resp.text


def test_owner_view_private_deck_hides_share_url(client, tmp_path):
    from code.web.services.user_db import get_user_by_username
    _register(client, "alice8b", "alice8b@example.com")
    alice = get_user_by_username("alice8b")
    _write_deck(tmp_path, alice["id"], "Deck.csv", "private")

    resp = client.get("/decks/view?name=Deck.csv")
    assert resp.status_code == 200
    assert "won't work for anyone else" in resp.text
    assert "/decks/alice8b/Deck.csv" not in resp.text


def test_owner_view_public_deck_shows_share_url(client, tmp_path):
    from code.web.services.user_db import get_user_by_username
    _register(client, "alice8c", "alice8c@example.com")
    alice = get_user_by_username("alice8c")
    _write_deck(tmp_path, alice["id"], "Deck.csv", "public")

    resp = client.get("/decks/view?name=Deck.csv")
    assert resp.status_code == 200
    assert "/decks/alice8c/Deck.csv" in resp.text
    assert "won't work for anyone else" not in resp.text


def test_non_owner_view_hides_visibility_selector(client, tmp_path):
    from code.web.services.user_db import get_user_by_username
    _register(client, "alice9", "alice9@example.com")
    alice = get_user_by_username("alice9")
    _write_deck(tmp_path, alice["id"], "Deck.csv", "public")

    client.post("/auth/logout")
    _register(client, "bob9", "bob9@example.com")

    resp = client.get("/decks/alice9/Deck.csv")
    assert resp.status_code == 200
    assert 'id="deck-visibility"' not in resp.text


def test_index_page_shows_visibility_select_for_own_decks(client, tmp_path):
    from code.web.services.user_db import get_user_by_username
    _register(client, "alice10", "alice10@example.com")
    alice = get_user_by_username("alice10")
    _write_deck(tmp_path, alice["id"], "Deck.csv", "unlisted")

    resp = client.get("/decks/")
    assert resp.status_code == 200
    assert "deck-visibility-select" in resp.text
    assert 'value="unlisted" selected' in resp.text


def test_set_visibility_response_includes_share_url_oob_for_public(client, tmp_path):
    from code.web.services.user_db import get_user_by_username
    _register(client, "alice11", "alice11@example.com")
    alice = get_user_by_username("alice11")
    _write_deck(tmp_path, alice["id"], "Deck.csv", "private")

    resp = client.post("/decks/set-visibility", data={"deck_name": "Deck.csv", "visibility": "public"})
    assert resp.status_code == 200
    assert 'hx-swap-oob="true"' in resp.text
    assert "/decks/alice11/Deck.csv" in resp.text


def test_set_visibility_response_includes_private_message_oob(client, tmp_path):
    from code.web.services.user_db import get_user_by_username
    _register(client, "alice12", "alice12@example.com")
    alice = get_user_by_username("alice12")
    _write_deck(tmp_path, alice["id"], "Deck.csv", "public")

    resp = client.post("/decks/set-visibility", data={"deck_name": "Deck.csv", "visibility": "private"})
    assert resp.status_code == 200
    assert "won't work for anyone else" in resp.text


def test_is_guest_request_helper(client):
    from code.web.routes.build_newflow import _is_guest_request
    from types import SimpleNamespace

    guest_request = SimpleNamespace(state=SimpleNamespace(current_user=None))
    assert _is_guest_request(guest_request) is True

    guest_user_request = SimpleNamespace(state=SimpleNamespace(current_user={"is_guest": True}))
    assert _is_guest_request(guest_user_request) is True

    real_user_request = SimpleNamespace(state=SimpleNamespace(current_user={"is_guest": False, "id": "u1"}))
    assert _is_guest_request(real_user_request) is False


# ---------------------------------------------------------------------------
# Milestone 5: public deck discovery on the Finished Decks index page
# ---------------------------------------------------------------------------

def test_list_public_decks_excludes_owner_and_private(client, tmp_path):
    from code.web.services.user_db import get_user_by_username
    from code.web.routes.decks import list_public_decks

    _register(client, "pub1", "pub1@example.com")
    owner = get_user_by_username("pub1")
    _write_deck(tmp_path, owner["id"], "Owned.csv", "public")

    client.post("/auth/logout")
    _register(client, "pub2", "pub2@example.com")
    other = get_user_by_username("pub2")
    _write_deck(tmp_path, other["id"], "OtherPublic.csv", "public")
    _write_deck(tmp_path, other["id"], "OtherPrivate.csv", "private")

    results = list_public_decks(exclude_user_id=other["id"])
    names = {r["name"] for r in results}
    assert "Owned.csv" in names  # pub1's public deck, visible to pub2's viewpoint
    assert "OtherPublic.csv" not in names  # excluded: it's the requester's (other's) own deck
    assert "OtherPrivate.csv" not in names  # never public


def test_index_page_shows_other_users_public_decks(client, tmp_path):
    from code.web.services.user_db import get_user_by_username

    _register(client, "pub3", "pub3@example.com")
    other = get_user_by_username("pub3")
    _write_deck(tmp_path, other["id"], "SharedDeck.csv", "public")
    _write_deck(tmp_path, other["id"], "HiddenDeck.csv", "private")

    client.post("/auth/logout")
    _register(client, "pub4", "pub4@example.com")

    resp = client.get("/decks/")
    assert resp.status_code == 200
    assert "Other Users" in resp.text
    assert "SharedDeck.csv" in resp.text
    assert "HiddenDeck.csv" not in resp.text
    assert 'id="deck-personal-only"' in resp.text


def test_index_page_hides_personal_only_toggle_when_no_public_decks(client):
    _register(client, "pub5", "pub5@example.com")
    resp = client.get("/decks/")
    assert resp.status_code == 200
    assert 'id="deck-personal-only"' not in resp.text


def test_index_page_omits_own_decks_from_other_users_section(client, tmp_path):
    from code.web.services.user_db import get_user_by_username

    _register(client, "pub6", "pub6@example.com")
    user = get_user_by_username("pub6")
    _write_deck(tmp_path, user["id"], "MyPublicDeck.csv", "public")

    resp = client.get("/decks/")
    assert resp.status_code == 200
    # Should show up once (under "My Decks"), not duplicated under "Other Users' Decks"
    assert "Other Users' Decks" not in resp.text


# ---------------------------------------------------------------------------
# Milestone 7: visibility selector in the build wizard
# ---------------------------------------------------------------------------

def test_new_deck_modal_shows_visibility_select_defaulting_to_profile(client):
    from code.web.services.user_db import get_user_by_username, set_default_visibility
    _register(client, "wiz1", "wiz1@example.com")
    user = get_user_by_username("wiz1")
    set_default_visibility(user["id"], "unlisted")

    resp = client.get("/build/new")
    assert resp.status_code == 200
    assert 'name="deck_visibility"' in resp.text
    assert 'value="unlisted" selected' in resp.text


def test_new_deck_modal_hides_visibility_select_for_guest(client):
    resp = client.get("/build/new")
    assert resp.status_code == 200
    assert 'name="deck_visibility"' not in resp.text

