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


def test_permalink_roundtrip_via_build_routes(client: TestClient):
    # Create a permalink via random full build
    r1 = client.post("/api/random_full_build", json={"seed": 777})
    assert r1.status_code == 200, r1.text
    p1 = r1.json().get("permalink")
    assert p1 and p1.startswith("/build/from?state=")
    token = p1.split("state=", 1)[1]
    state1 = _decode_state_token(token)
    rnd1 = state1.get("random") or {}

    # Visit the permalink (server should rehydrate session from token)
    r_page = client.get(p1)
    assert r_page.status_code == 200

    # Ask server to produce a permalink from current session
    r2 = client.get("/build/permalink")
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2.get("ok") is True
    p2 = body2.get("permalink")
    assert p2 and p2.startswith("/build/from?state=")
    token2 = p2.split("state=", 1)[1]
    state2 = _decode_state_token(token2)
    rnd2 = state2.get("random") or {}

    # The random payload should survive the roundtrip unchanged
    assert rnd2 == rnd1
