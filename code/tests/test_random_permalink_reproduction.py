import os
import base64
import json

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


def _decode_state_token(token: str) -> dict:
    pad = "=" * (-len(token) % 4)
    raw = base64.urlsafe_b64decode((token + pad).encode("ascii")).decode("utf-8")
    return json.loads(raw)


def test_permalink_reproduces_random_full_build(client: TestClient):
    # Build once with a fixed seed
    seed = 1111
    r1 = client.post("/api/random_full_build", json={"seed": seed})
    assert r1.status_code == 200, r1.text
    data1 = r1.json()
    assert data1.get("seed") == seed
    assert data1.get("permalink")
    deck1 = data1.get("decklist")

    # Extract and decode permalink token
    permalink: str = data1["permalink"]
    assert permalink.startswith("/build/from?state=")
    token = permalink.split("state=", 1)[1]
    decoded = _decode_state_token(token)
    # Validate token contains the random payload
    rnd = decoded.get("random") or {}
    assert rnd.get("seed") == seed
    # Rebuild using only the fields contained in the permalink random payload
    r2 = client.post("/api/random_full_build", json={
        "seed": rnd.get("seed"),
        "theme": rnd.get("theme"),
        "constraints": rnd.get("constraints"),
    })
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    deck2 = data2.get("decklist")

    # Reproduction should be identical
    assert deck2 == deck1
