# Web Backend Testing Guide

## Overview

The test suite lives in `code/tests/`. All tests use **pytest** and run against the real FastAPI app via `TestClient`. This guide covers patterns, conventions, and how to write new tests correctly.

---

## Running Tests

```powershell
# All tests
.venv/Scripts/python.exe -m pytest -q

# Specific files (always use explicit paths — no wildcards)
.venv/Scripts/python.exe -m pytest code/tests/test_commanders_route.py code/tests/test_validation.py -q

# Fast subset (locks + summary utils)
# Use the VS Code task: pytest-fast-locks
```

**Always use the full venv Python path** — never `python` or `pytest` directly.

---

## Test File Naming

Name test files by the **functionality they test**, not by milestone or ticket:

| Good | Bad |
|---|---|
| `test_commander_search.py` | `test_m3_validation.py` |
| `test_error_handling.py` | `test_phase2_routes.py` |
| `test_include_exclude_validation.py` | `test_milestone_4_fixes.py` |

One file per logical area. Merge overlapping coverage rather than creating many small files.

---

## Test Structure

### Class-based grouping (preferred)

Group related tests into classes. Use descriptive method names that read as sentences:

```python
class TestCommanderSearch:
    def test_empty_query_returns_no_candidates(self, client):
        ...

    def test_exact_match_returns_top_result(self, client):
        ...

    def test_fuzzy_match_works_for_misspellings(self, client):
        ...
```

### Standalone functions (acceptable for simple cases)

```python
def test_health_endpoint_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200
```

---

## Route Tests

Route tests use `TestClient` against the real `app`. Use `monkeypatch` to isolate external dependencies (CSV reads, session state, orchestrator calls).

```python
from fastapi.testclient import TestClient
from code.web.app import app

@pytest.fixture
def client(monkeypatch):
    # Patch heavy dependencies before creating client
    monkeypatch.setattr("code.web.services.orchestrator.commander_candidates", lambda q, limit=10: [])
    with TestClient(app) as c:
        yield c
```

**Key rules:**
- Always use `with TestClient(app) as c:` (context manager) so lifespan events run
- Pass `raise_server_exceptions=False` when testing error handlers:
  ```python
  with TestClient(app, raise_server_exceptions=False) as c:
      yield c
  ```
- Set session cookies when routes read session state:
  ```python
  resp = client.get("/build/step2", cookies={"sid": "test-sid"})
  ```

### Example: route with session

```python
from code.web.services.tasks import get_session

@pytest.fixture
def client_with_session(monkeypatch):
    sid = "test-session-id"
    session = get_session(sid)
    session["commander"] = {"name": "Atraxa, Praetors' Voice", "ok": True}

    with TestClient(app) as c:
        c.cookies.set("sid", sid)
        yield c
```

### Example: HTMX request

```python
def test_step2_htmx_partial(client_with_session):
    resp = client_with_session.get(
        "/build/step2",
        headers={"HX-Request": "true"}
    )
    assert resp.status_code == 200
    # HTMX partials are HTML fragments, not full pages
    assert "<html>" not in resp.text
```

### Example: error handler response shape

```python
def test_invalid_commander_returns_400(client):
    resp = client.post("/build/step1/confirm", data={"name": ""})
    assert resp.status_code == 400
    # Check standardized error shape from M4
    data = resp.json()
    assert data["error"] is True
    assert "request_id" in data
```

---

## Service / Unit Tests

Service tests don't need `TestClient`. Test classes directly with mocked dependencies.

```python
from code.web.services.base import BaseService, ValidationError

class TestMyService:
    def test_validate_raises_on_false(self):
        svc = BaseService()
        with pytest.raises(ValidationError, match="must not be empty"):
            svc._validate(False, "must not be empty")
```

For services with external I/O (CSV reads, API calls), use `monkeypatch` or `unittest.mock.patch`:

```python
from unittest.mock import patch, MagicMock

def test_catalog_loader_caches_result(monkeypatch):
    mock_data = [{"name": "Test Commander"}]
    with patch("code.web.services.commander_catalog_loader._load_from_disk", return_value=mock_data):
        result = load_commander_catalog()
        assert len(result.entries) == 1
```

---

## Validation Tests

Pydantic model tests are pure unit tests — no fixtures needed:

```python
from code.web.validation.models import BuildRequest
from pydantic import ValidationError

class TestBuildRequest:
    def test_commander_required(self):
        with pytest.raises(ValidationError):
            BuildRequest(commander="")

    def test_themes_defaults_to_empty_list(self):
        req = BuildRequest(commander="Atraxa, Praetors' Voice")
        assert req.themes == []
```

---

## Exception / Error Handling Tests

Use a minimal inline app to test exception handlers in isolation — avoids loading the full app stack:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient
from code.exceptions import DeckBuilderError, CommanderValidationError
from code.web.utils.responses import deck_builder_error_response

@pytest.fixture(scope="module")
def error_test_client():
    mini_app = FastAPI()

    @mini_app.get("/raise")
    async def raise_error(request: Request):
        raise CommanderValidationError("test error")

    @mini_app.exception_handler(Exception)
    async def handler(request, exc):
        if isinstance(exc, DeckBuilderError):
            return deck_builder_error_response(request, exc)
        raise exc

    with TestClient(mini_app, raise_server_exceptions=False) as c:
        yield c

def test_commander_error_returns_400(error_test_client):
    resp = error_test_client.get("/raise")
    assert resp.status_code == 400
    assert resp.json()["error_type"] == "CommanderValidationError"
```

See `code/tests/test_error_handling.py` for complete examples.

---

## Environment & Fixtures

### `conftest.py` globals

`code/tests/conftest.py` provides:
- `ensure_test_environment` (autouse) — sets `ALLOW_MUST_HAVES=1` and restores env after each test

### Test data

CSV test data lives in `csv_files/testdata/`. Point tests there with:

```python
monkeypatch.setenv("CSV_FILES_DIR", str(Path("csv_files/testdata").resolve()))
```

### Clearing caches between tests

Some services use module-level caches. Clear them in fixtures to avoid cross-test pollution:

```python
from code.web.services.commander_catalog_loader import clear_commander_catalog_cache

@pytest.fixture(autouse=True)
def reset_catalog():
    clear_commander_catalog_cache()
    yield
    clear_commander_catalog_cache()
```

---

## Coverage Targets

| Layer | Target | Notes |
|---|---|---|
| Validation models | 95%+ | Pure Pydantic, easy to cover |
| Service layer | 80%+ | Mock external I/O |
| Route handlers | 70%+ | Cover happy path + key error paths |
| Exception handlers | 90%+ | Covered by `test_error_handling.py` |
| Utilities | 90%+ | `responses.py`, `telemetry.py` |

Run coverage:

```powershell
.venv/Scripts/python.exe -m pytest --cov=code/web --cov-report=term-missing -q
```

---

## What Not to Test

- Framework internals (FastAPI routing, Starlette middleware behavior)
- Trivial getters/setters with no logic
- Template rendering correctness (covered by template validation tests)
- Third-party library behavior (Pydantic, SQLAlchemy, etc.)

Focus tests on **your logic**: validation rules, session state transitions, error mapping, orchestrator integration.
