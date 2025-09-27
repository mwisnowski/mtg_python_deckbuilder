import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # Ensure flags and frozen dataset
    os.environ["RANDOM_MODES"] = "1"
    os.environ["RANDOM_UI"] = "1"
    os.environ["CSV_FILES_DIR"] = os.path.join("csv_files", "testdata")

    from web.app import app

    with TestClient(app) as c:
        yield c


def test_reroll_idempotency_and_progression(client: TestClient):
    # Initial build
    base_seed = 2024
    r1 = client.post("/api/random_full_build", json={"seed": base_seed})
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    deck1 = d1.get("decklist")
    assert isinstance(deck1, list) and deck1

    # Rebuild with the same seed should produce identical result
    r_same = client.post("/api/random_full_build", json={"seed": base_seed})
    assert r_same.status_code == 200, r_same.text
    deck_same = r_same.json().get("decklist")
    assert deck_same == deck1

    # Reroll (seed+1) should typically change the result
    r2 = client.post("/api/random_reroll", json={"seed": base_seed})
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2.get("seed") == base_seed + 1
    deck2 = d2.get("decklist")

    # It is acceptable that a small dataset could still coincide, but in practice should differ
    assert deck2 != deck1 or d2.get("commander") != d1.get("commander")
