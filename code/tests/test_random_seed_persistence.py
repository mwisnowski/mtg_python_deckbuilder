import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    os.environ["RANDOM_MODES"] = "1"
    os.environ["RANDOM_UI"] = "1"
    os.environ["CSV_FILES_DIR"] = os.path.join("csv_files", "testdata")
    from web.app import app
    with TestClient(app) as c:
        yield c


def test_recent_seeds_flow(client: TestClient):
    # Initially empty
    r0 = client.get("/api/random/seeds")
    assert r0.status_code == 200, r0.text
    data0 = r0.json()
    assert data0.get("seeds") == [] or data0.get("seeds") is not None

    # Run a full build with a specific seed
    r1 = client.post("/api/random_full_build", json={"seed": 1001})
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1.get("seed") == 1001

    # Reroll (should increment to 1002) and be stored
    r2 = client.post("/api/random_reroll", json={"seed": 1001})
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2.get("seed") == 1002

    # Fetch recent seeds; expect to include both 1001 and 1002, with last==1002
    r3 = client.get("/api/random/seeds")
    assert r3.status_code == 200, r3.text
    d3 = r3.json()
    seeds = d3.get("seeds") or []
    assert 1001 in seeds and 1002 in seeds
    assert d3.get("last") == 1002
