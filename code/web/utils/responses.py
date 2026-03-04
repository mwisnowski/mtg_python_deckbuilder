"""Response builder utilities for standardized HTTP responses.

Provides helper functions for creating consistent response objects across all routes.
"""
from typing import Any, Dict, Optional
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates


def build_error_response(
    request: Request,
    status_code: int,
    error_type: str,
    message: str,
    detail: Optional[str] = None,
    fields: Optional[Dict[str, list[str]]] = None
) -> JSONResponse:
    """Build a standardized error response.
    
    Args:
        request: FastAPI request object
        status_code: HTTP status code
        error_type: Type of error (e.g., "ValidationError", "NotFoundError")
        message: User-friendly error message
        detail: Additional error detail
        fields: Field-level validation errors
        
    Returns:
        JSONResponse with standardized error structure
    """
    import time
    
    request_id = getattr(request.state, "request_id", "unknown")
    error_data = {
        "status": status_code,
        "error": error_type,
        "message": message,
        "path": str(request.url.path),
        "request_id": request_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    
    if detail:
        error_data["detail"] = detail
    if fields:
        error_data["fields"] = fields
    
    return JSONResponse(content=error_data, status_code=status_code)


def build_success_response(
    data: Any,
    status_code: int = 200,
    headers: Optional[Dict[str, str]] = None
) -> JSONResponse:
    """Build a standardized success response.
    
    Args:
        data: Response data to return
        status_code: HTTP status code (default 200)
        headers: Optional additional headers
        
    Returns:
        JSONResponse with data
    """
    response = JSONResponse(content=data, status_code=status_code)
    if headers:
        for key, value in headers.items():
            response.headers[key] = value
    return response


def build_template_response(
    request: Request,
    templates: Jinja2Templates,
    template_name: str,
    context: Dict[str, Any],
    status_code: int = 200
) -> HTMLResponse:
    """Build a standardized template response.
    
    Args:
        request: FastAPI request object
        templates: Jinja2Templates instance
        template_name: Name of template to render
        context: Template context dictionary
        status_code: HTTP status code (default 200)
        
    Returns:
        HTMLResponse with rendered template
    """
    # Ensure request is in context
    if "request" not in context:
        context["request"] = request
    
    return templates.TemplateResponse(
        request,
        template_name,
        context,
        status_code=status_code
    )


def build_htmx_response(
    content: str,
    trigger: Optional[Dict[str, Any]] = None,
    retarget: Optional[str] = None,
    reswap: Optional[str] = None
) -> HTMLResponse:
    """Build an HTMX partial response with appropriate headers.
    
    Args:
        content: HTML content to return
        trigger: HTMX trigger events to fire
        retarget: Optional HX-Retarget header
        reswap: Optional HX-Reswap header
        
    Returns:
        HTMLResponse with HTMX headers
    """
    import json
    
    response = HTMLResponse(content=content)
    
    if trigger:
        response.headers["HX-Trigger"] = json.dumps(trigger)
    if retarget:
        response.headers["HX-Retarget"] = retarget
    if reswap:
        response.headers["HX-Reswap"] = reswap
    
    return response


def merge_hx_trigger(response: HTMLResponse, events: Dict[str, Any]) -> None:
    """Merge additional HTMX trigger events into an existing response.
    
    Args:
        response: Existing HTMLResponse
        events: Additional trigger events to merge
    """
    import json
    
    if not events:
        return
    
    existing = response.headers.get("HX-Trigger")
    if existing:
        try:
            existing_events = json.loads(existing)
            existing_events.update(events)
            response.headers["HX-Trigger"] = json.dumps(existing_events)
        except (json.JSONDecodeError, AttributeError):
            # If existing is a simple string, convert to dict
            response.headers["HX-Trigger"] = json.dumps(events)
    else:
        response.headers["HX-Trigger"] = json.dumps(events)
