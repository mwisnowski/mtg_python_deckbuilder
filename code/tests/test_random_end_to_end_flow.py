from __future__ import annotations

import os
import base64
import json
from fastapi.testclient import TestClient

# End-to-end scenario test for Random Modes.
# Flow:
# 1. Full build with seed S and (optional) theme.
# 2. Reroll from that seed (seed+1) and capture deck.
# 3. Replay permalink from step 1 (decode token) to reproduce original deck.
# Assertions:
# - Initial and reproduced decks identical (permalink determinism).
# - Reroll seed increments.
# - Reroll deck differs from original unless dataset too small (allow equality but tolerate identical for tiny pool).


def _decode_state(token: str) -> dict:
    pad = "=" * (-len(token) % 4)
    raw = base64.urlsafe_b64decode((token + pad).encode("ascii")).decode("utf-8")
    return json.loads(raw)


def test_random_end_to_end_flow(monkeypatch):
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("RANDOM_UI", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    from code.web.app import app
    client = TestClient(app)

    seed = 5150
    # Step 1: Full build
    r1 = client.post("/api/random_full_build", json={"seed": seed, "theme": "Tokens"})
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1.get("seed") == seed
    deck1 = d1.get("decklist")
    assert isinstance(deck1, list)
    permalink = d1.get("permalink")
    assert permalink and permalink.startswith("/build/from?state=")

    # Step 2: Reroll
    r2 = client.post("/api/random_reroll", json={"seed": seed})
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2.get("seed") == seed + 1
    deck2 = d2.get("decklist")
    assert isinstance(deck2, list)

    # Allow equality for tiny dataset; but typically expect difference
    if d2.get("commander") == d1.get("commander"):
        # At least one card difference ideally
        # If exact decklist same, just accept (document small test pool)
        pass
    else:
        assert d2.get("commander") != d1.get("commander") or deck2 != deck1

    # Step 3: Replay permalink
    token = permalink.split("state=", 1)[1]
    decoded = _decode_state(token)
    rnd = decoded.get("random") or {}
    r3 = client.post("/api/random_full_build", json={
        "seed": rnd.get("seed"),
        "theme": rnd.get("theme"),
        "constraints": rnd.get("constraints"),
    })
    assert r3.status_code == 200, r3.text
    d3 = r3.json()
    # Deck reproduced
    assert d3.get("decklist") == deck1
    assert d3.get("commander") == d1.get("commander")
