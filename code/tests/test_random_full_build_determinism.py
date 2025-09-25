from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient
from deck_builder.random_entrypoint import build_random_full_deck


@pytest.fixture(scope="module")
def client():
    os.environ["RANDOM_MODES"] = "1"
    os.environ["CSV_FILES_DIR"] = os.path.join("csv_files", "testdata")
    from web.app import app
    with TestClient(app) as c:
        yield c


def test_full_build_same_seed_produces_same_deck(client: TestClient):
    body = {"seed": 4242}
    r1 = client.post("/api/random_full_build", json=body)
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    r2 = client.post("/api/random_full_build", json=body)
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d1.get("seed") == d2.get("seed") == 4242
    assert d1.get("decklist") == d2.get("decklist")


def test_random_full_build_is_deterministic_on_frozen_dataset(monkeypatch):
    # Use frozen dataset for determinism
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    # Fixed seed should produce the same compact decklist
    out1 = build_random_full_deck(theme="Goblin Kindred", seed=777)
    out2 = build_random_full_deck(theme="Goblin Kindred", seed=777)

    assert out1.seed == out2.seed == 777
    assert out1.commander == out2.commander
    assert isinstance(out1.decklist, list) and isinstance(out2.decklist, list)
    assert out1.decklist == out2.decklist
