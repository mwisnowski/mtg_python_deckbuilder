import os
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


def test_api_random_reroll_increments_seed(client: TestClient):
    r1 = client.post("/api/random_full_build", json={"seed": 123})
    assert r1.status_code == 200, r1.text
    data1 = r1.json()
    assert data1.get("seed") == 123

    r2 = client.post("/api/random_reroll", json={"seed": 123})
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    assert data2.get("seed") == 124
    assert data2.get("permalink")


def test_hx_random_reroll_returns_html(client: TestClient):
    headers = {"HX-Request": "true", "Content-Type": "application/json"}
    r = client.post("/hx/random_reroll", data=json.dumps({"seed": 42}), headers=headers)
    assert r.status_code == 200, r.text
    # Accept either HTML fragment or JSON fallback
    content_type = r.headers.get("content-type", "")
    if "text/html" in content_type:
        assert "Seed:" in r.text
    else:
        j = r.json()
        assert j.get("seed") in (42, 43)  # depends on increment policy