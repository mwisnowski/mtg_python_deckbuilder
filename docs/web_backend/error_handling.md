# Error Handling Guide

## Overview

The web layer uses a layered error handling strategy:

1. **Typed domain exceptions** (`code/exceptions.py`) — raised by routes and services to express semantic failures
2. **Exception handlers** (`code/web/app.py`) — convert exceptions to appropriate HTTP responses
3. **Response utilities** (`code/web/utils/responses.py`) — build consistent JSON or HTML fragment responses

HTMX requests get an HTML error fragment; regular API requests get JSON.

---

## Exception Hierarchy

All custom exceptions inherit from `DeckBuilderError` (base) in `code/exceptions.py`.

### Status Code Mapping

| Exception | HTTP Status | Use When |
|---|---|---|
| `SessionExpiredError` | 401 | Session cookie is missing or stale |
| `BuildNotFoundError` | 404 | Session has no build result |
| `FeatureDisabledError` | 404 | Feature is off via env var |
| `CommanderValidationError` (and subclasses) | 400 | Invalid commander input |
| `ThemeSelectionError` | 400 | Invalid theme selection |
| `ThemeError` | 400 | General theme failure |
| `PriceLimitError`, `PriceValidationError` | 400 | Bad price constraint |
| `PriceAPIError` | 503 | External price API down |
| `CSVFileNotFoundError` | 503 | Card data files missing |
| `MTGJSONDownloadError` | 503 | Data download failure |
| `EmptyDataFrameError` | 503 | No card data available |
| `DeckBuilderError` (base, unrecognized) | 500 | Unexpected domain error |

### Web-Specific Exceptions

Added in M4, defined at the bottom of `code/exceptions.py`:

```python
SessionExpiredError(sid="abc")        # session missing or expired
BuildNotFoundError(sid="abc")          # no build result in session
FeatureDisabledError("partner_suggestions")  # feature toggled off
```

---

## Raising Exceptions in Routes

Prefer typed exceptions over `HTTPException` for domain failures:

```python
# Good — semantic, gets proper status code automatically
from code.exceptions import CommanderValidationError, FeatureDisabledError

raise CommanderValidationError("Commander 'Foo' not found")
raise FeatureDisabledError("batch_build")

# Still acceptable for HTTP-level concerns (rate limits, auth)
from fastapi import HTTPException
raise HTTPException(status_code=429, detail="rate_limited")
```

Keep `HTTPException` for infrastructure concerns (rate limiting, feature flags that are pure routing decisions). Use custom exceptions for domain logic failures.

---

## Response Shape

### JSON (non-HTMX)

```json
{
  "error": true,
  "status": 400,
  "error_type": "CommanderValidationError",
  "code": "CMD_VALID",
  "message": "Commander 'Foo' not found",
  "path": "/build/step1/confirm",
  "request_id": "a1b2c3d4",
  "timestamp": "2026-03-17T12:00:00Z"
}
```

### HTML (HTMX requests)

```html
<div class="error-banner" role="alert">
  <strong>400</strong> Commander 'Foo' not found
</div>
```

The `X-Request-ID` header is always set on both response types.

---

## Adding a New Exception

1. Add the class to `code/exceptions.py` inheriting from the appropriate parent
2. Add an entry to `_EXCEPTION_STATUS_MAP` in `code/web/utils/responses.py` if the status code differs from the parent
3. Raise it in your route or service
4. The handler in `app.py` will pick it up automatically

---

## Testing Error Handling

See `code/tests/test_error_handling.py` for patterns. Key fixtures:

```python
# Minimal app with DeckBuilderError handler
app = FastAPI()

@app.exception_handler(Exception)
async def handler(request, exc):
    if isinstance(exc, DeckBuilderError):
        return deck_builder_error_response(request, exc)
    ...

client = TestClient(app, raise_server_exceptions=False)
```

Always pass `raise_server_exceptions=False` so the handler runs during tests.
