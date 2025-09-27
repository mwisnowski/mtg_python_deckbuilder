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


def test_random_modes_page_renders(client: TestClient):
    r = client.get("/random")
    assert r.status_code == 200
    assert "Random Modes" in r.text
