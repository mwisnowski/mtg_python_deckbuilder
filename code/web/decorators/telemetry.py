"""Telemetry decorators for route handlers.

Provides decorators to automatically track route access, build times, and other metrics.
"""
from functools import wraps
from typing import Callable, Any
import time
from code.logging_util import get_logger

LOGGER = get_logger(__name__)


def track_route_access(event_name: str):
    """Decorator to track route access with telemetry.
    
    Args:
        event_name: Name of the telemetry event to log
        
    Example:
        @router.get("/build/new")
        @track_route_access("build_start")
        async def start_build(request: Request):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed_ms = int((time.time() - start_time) * 1000)
                LOGGER.debug(f"Route {event_name} completed in {elapsed_ms}ms")
                return result
            except Exception as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                LOGGER.error(f"Route {event_name} failed after {elapsed_ms}ms: {e}")
                raise
        return wrapper
    return decorator


def track_build_time(operation: str):
    """Decorator to track deck building operation timing.
    
    Args:
        operation: Description of the build operation
        
    Example:
        @track_build_time("commander_selection")
        async def select_commander(request: Request):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            result = await func(*args, **kwargs)
            elapsed_ms = int((time.time() - start_time) * 1000)
            LOGGER.info(f"Build operation '{operation}' took {elapsed_ms}ms")
            return result
        return wrapper
    return decorator


def log_route_errors(route_name: str):
    """Decorator to log route errors with context.
    
    Args:
        route_name: Name of the route for error context
        
    Example:
        @router.post("/build/create")
        @log_route_errors("build_create")
        async def create_deck(request: Request):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Extract request if available
                request = None
                for arg in args:
                    if hasattr(arg, "url") and hasattr(arg, "state"):
                        request = arg
                        break
                
                request_id = getattr(request.state, "request_id", "unknown") if request else "unknown"
                LOGGER.error(
                    f"Error in route '{route_name}' [request_id={request_id}]: {e}",
                    exc_info=True
                )
                raise
        return wrapper
    return decorator
