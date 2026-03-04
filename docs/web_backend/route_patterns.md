# Route Handler Patterns

**Status**: ✅ Active Standard (R9 M1)  
**Last Updated**: 2026-02-20

This document defines the standard patterns for FastAPI route handlers in the MTG Deckbuilder web application.

## Table of Contents

- [Overview](#overview)
- [Standard Route Pattern](#standard-route-pattern)
- [Decorators](#decorators)
- [Request Handling](#request-handling)
- [Response Building](#response-building)
- [Error Handling](#error-handling)
- [Examples](#examples)

## Overview

All route handlers should follow these principles:
- **Consistency**: Use standard patterns for request/response handling
- **Clarity**: Clear separation between validation, business logic, and response building
- **Observability**: Proper logging and telemetry
- **Error Handling**: Use custom exceptions, not HTTPException directly
- **Type Safety**: Full type hints for all parameters and return types

## Standard Route Pattern

```python
from fastapi import APIRouter, Request, Query, Form
from fastapi.responses import HTMLResponse, JSONResponse
from ..decorators.telemetry import track_route_access, log_route_errors
from ..utils.responses import build_template_response, build_error_response
from exceptions import ValidationError, NotFoundError  # From code/exceptions.py

router = APIRouter()

@router.get("/endpoint", response_class=HTMLResponse)
@track_route_access("event_name")  # Optional: for telemetry
@log_route_errors("route_name")     # Optional: for error logging
async def endpoint_handler(
    request: Request,
    param: str = Query(..., description="Parameter description"),
) -> HTMLResponse:
    """
    Brief description of what this endpoint does.
    
    Args:
        request: FastAPI request object
        param: Query parameter description
        
    Returns:
        HTMLResponse with rendered template
        
    Raises:
        ValidationError: When parameter validation fails
        NotFoundError: When resource is not found
    """
    try:
        # 1. Validate inputs
        if not param:
            raise ValidationError("parameter_required", details={"param": "required"})
        
        # 2. Call service layer (business logic)
        from ..services.your_service import process_request
        result = await process_request(param)
        
        if not result:
            raise NotFoundError("resource_not_found", details={"param": param})
        
        # 3. Build and return response
        from ..app import templates
        context = {
            "result": result,
            "param": param,
        }
        return build_template_response(
            request, templates, "path/template.html", context
        )
        
    except (ValidationError, NotFoundError):
        # Let custom exception handlers in app.py handle these
        raise
    except Exception as e:
        # Log unexpected errors and re-raise
        LOGGER.error(f"Unexpected error in endpoint_handler: {e}", exc_info=True)
        raise
```

## Decorators

### Telemetry Decorators

Located in [code/web/decorators/telemetry.py](../../code/web/decorators/telemetry.py):

```python
from ..decorators.telemetry import (
    track_route_access,   # Track route access
    track_build_time,     # Track operation timing
    log_route_errors,     # Enhanced error logging
)

@router.get("/build/step1")
@track_route_access("build_step1_access")
@log_route_errors("build_step1")
async def step1_handler(request: Request):
    # Route implementation
    ...
```

**When to use:**
- `@track_route_access`: For all user-facing routes (telemetry)
- `@track_build_time`: For deck building operations (performance monitoring)
- `@log_route_errors`: For routes with complex error handling

### Decorator Ordering

Order matters! Apply decorators from bottom to top:

```python
@router.get("/endpoint")          # 1. Router decorator (bottom)
@track_route_access("event")      # 2. Telemetry (before error handler)
@log_route_errors("route")        # 3. Error logging (top)
async def handler(...):
    ...
```

## Request Handling

### Query Parameters

```python
from fastapi import Query

@router.get("/search")
async def search_cards(
    request: Request,
    query: str = Query(..., min_length=1, max_length=100, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Results limit"),
) -> JSONResponse:
    ...
```

### Form Data

```python
from fastapi import Form

@router.post("/build/create")
async def create_deck(
    request: Request,
    commander: str = Form(..., description="Commander name"),
    themes: list[str] = Form(default=[], description="Theme tags"),
) -> HTMLResponse:
    ...
```

### JSON Body (Pydantic Models)

```python
from pydantic import BaseModel, Field

class BuildRequest(BaseModel):
    """Build request validation model."""
    commander: str = Field(..., min_length=1, max_length=200)
    themes: list[str] = Field(default_factory=list, max_items=5)
    power_bracket: int = Field(default=2, ge=1, le=4)

@router.post("/api/build")
async def api_build_deck(
    request: Request,
    build_req: BuildRequest,
) -> JSONResponse:
    # build_req is automatically validated
    ...
```

### Session Data

```python
from ..services.tasks import get_session, set_session_value

@router.post("/step2")
async def step2_handler(request: Request):
    sid = request.cookies.get("sid")
    if not sid:
        raise ValidationError("session_required")
    
    session = get_session(sid)
    commander = session.get("commander")
    
    # Update session
    set_session_value(sid, "step", "2")
    ...
```

## Response Building

### Template Responses

Use `build_template_response` from [code/web/utils/responses.py](../../code/web/utils/responses.py):

```python
from ..utils.responses import build_template_response
from ..app import templates

context = {
    "title": "Page Title",
    "data": result_data,
}
return build_template_response(
    request, templates, "path/template.html", context
)
```

### JSON Responses

```python
from ..utils.responses import build_success_response

data = {
    "commander": "Atraxa, Praetors' Voice",
    "themes": ["Proliferate", "Superfriends"],
}
return build_success_response(data, status_code=200)
```

### HTMX Partial Responses

```python
from ..utils.responses import build_htmx_response

html_content = templates.get_template("partials/result.html").render(context)
return build_htmx_response(
    content=html_content,
    trigger={"deckUpdated": {"commander": "Atraxa"}},
    retarget="#result-container",
)
```

### Error Responses

```python
from ..utils.responses import build_error_response

# Manual error response (prefer raising custom exceptions instead)
return build_error_response(
    request,
    status_code=400,
    error_type="ValidationError",
    message="Invalid commander name",
    detail="Commander 'Foo' does not exist",
    fields={"commander": ["Commander 'Foo' does not exist"]}
)
```

## Error Handling

### Use Custom Exceptions

**Always use custom exceptions** from [code/exceptions.py](../../code/exceptions.py), not `HTTPException`:

```python
from exceptions import (
    ValidationError,
    NotFoundError,
    CommanderValidationError,
    ThemeError,
)

# ❌ DON'T DO THIS
from fastapi import HTTPException
raise HTTPException(status_code=400, detail="Invalid input")

# ✅ DO THIS INSTEAD
raise ValidationError("Invalid input", code="VALIDATION_ERR", details={"field": "value"})
```

### Exception Hierarchy

See [code/exceptions.py](../../code/exceptions.py) for the full hierarchy. Common exceptions:

- `DeckBuilderError` - Base class for all custom exceptions
  - `MTGSetupError` - Setup-related errors
  - `CSVError` - Data loading errors
  - `CommanderValidationError` - Commander validation failures
    - `CommanderTypeError`, `CommanderColorError`, etc.
  - `ThemeError` - Theme-related errors
  - `PriceError` - Price checking errors
  - `LibraryOrganizationError` - Deck organization errors

### Let Exception Handlers Handle It

The app.py exception handlers will convert custom exceptions to HTTP responses:

```python
@router.get("/commander/{name}")
async def get_commander(request: Request, name: str):
    # Validate
    if not name:
        raise ValidationError("Commander name required", code="CMD_NAME_REQUIRED")
    
    # Business logic
    try:
        commander = await load_commander(name)
    except CommanderNotFoundError as e:
        # Re-raise to let global handler convert to 404
        raise
    
    # Return success
    return build_success_response({"commander": commander})
```

## Examples

### Example 1: Simple GET with Template Response

```python
from fastapi import Request
from fastapi.responses import HTMLResponse
from ..utils.responses import build_template_response
from ..decorators.telemetry import track_route_access
from ..app import templates

@router.get("/commanders", response_class=HTMLResponse)
@track_route_access("commanders_list_view")
async def list_commanders(request: Request) -> HTMLResponse:
    """Display the commanders catalog page."""
    from ..services.commander_catalog_loader import load_commander_catalog
    
    catalog = load_commander_catalog()
    context = {"commanders": catalog.commanders}
    
    return build_template_response(
        request, templates, "commanders/list.html", context
    )
```

### Example 2: POST with Form Data and Session

```python
from fastapi import Request, Form
from fastapi.responses import HTMLResponse
from ..utils.responses import build_template_response, build_htmx_response
from ..services.tasks import get_session, set_session_value
from exceptions import CommanderValidationError

@router.post("/build/select_commander", response_class=HTMLResponse)
async def select_commander(
    request: Request,
    commander: str = Form(..., description="Selected commander name"),
) -> HTMLResponse:
    """Handle commander selection in deck builder wizard."""
    # Validate commander
    if not commander or len(commander) > 200:
        raise CommanderValidationError(
            f"Invalid commander name: {commander}",
            code="CMD_INVALID",
            details={"name": commander}
        )
    
    # Store in session
    sid = request.cookies.get("sid")
    if sid:
        set_session_value(sid, "commander", commander)
    
    # Return HTMX partial
    from ..app import templates
    context = {"commander": commander, "step": "themes"}
    html = templates.get_template("build/step2_themes.html").render(context)
    
    return build_htmx_response(
        content=html,
        trigger={"commanderSelected": {"name": commander}},
    )
```

### Example 3: API Endpoint with JSON Response

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from ..utils.responses import build_success_response
from exceptions import ThemeError

class ThemeSearchRequest(BaseModel):
    """Theme search request model."""
    query: str = Field(..., min_length=1, max_length=100)
    limit: int = Field(default=10, ge=1, le=50)

@router.post("/api/themes/search")
async def search_themes(
    request: Request,
    search: ThemeSearchRequest,
) -> JSONResponse:
    """API endpoint to search for themes."""
    from ..services.theme_catalog_loader import search_themes as _search
    
    results = _search(search.query, limit=search.limit)
    
    if not results:
        raise ThemeError(
            f"No themes found matching '{search.query}'",
            code="THEME_NOT_FOUND",
            details={"query": search.query}
        )
    
    return build_success_response({
        "query": search.query,
        "count": len(results),
        "themes": [{"id": t.id, "name": t.name} for t in results],
    })
```

## Migration Guide

### For Existing Routes

When updating existing routes to follow this pattern:

1. **Add type hints** if missing
2. **Replace HTTPException** with custom exceptions
3. **Use response builders** instead of direct Response construction
4. **Add telemetry decorators** where appropriate
5. **Add docstrings** following the standard format
6. **Separate concerns**: validation → business logic → response

### Checklist

- [ ] Route has full type hints
- [ ] Uses custom exceptions (not HTTPException)
- [ ] Uses response builder utilities
- [ ] Has telemetry decorators (if applicable)
- [ ] Has complete docstring
- [ ] Separates validation, logic, and response
- [ ] Handles errors gracefully

---

**Related Documentation:**
- [Service Layer Architecture](./service_architecture.md) (M2)
- [Validation Framework](./validation.md) (M3)
- [Error Handling Guide](./error_handling.md) (M4)
- [Testing Standards](./testing.md) (M5)

**Last Updated**: 2026-02-20  
**Roadmap**: R9 M1 - Route Handler Standardization
