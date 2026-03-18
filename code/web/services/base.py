"""Base classes for web services.

Provides standardized patterns for service layer implementation including
state management, data loading, and caching.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, Optional, TypeVar
import threading
import time


T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


class ServiceError(Exception):
    """Base exception for service layer errors."""
    pass


class ValidationError(ServiceError):
    """Validation failed."""
    pass


class NotFoundError(ServiceError):
    """Resource not found."""
    pass


class BaseService(ABC):
    """Abstract base class for all services.
    
    Provides common patterns for initialization, validation, and error handling.
    Services should be stateless where possible and inject dependencies via __init__.
    """
    
    def __init__(self) -> None:
        """Initialize service. Override in subclasses to inject dependencies."""
        pass
    
    def _validate(self, condition: bool, message: str) -> None:
        """Validate a condition, raise ValidationError if false.
        
        Args:
            condition: Condition to check
            message: Error message if validation fails
            
        Raises:
            ValidationError: If condition is False
        """
        if not condition:
            raise ValidationError(message)


class StateService(BaseService):
    """Base class for services that manage mutable state.
    
    Provides thread-safe state management with automatic cleanup.
    Subclasses should implement _initialize_state and _should_cleanup.
    """
    
    def __init__(self) -> None:
        super().__init__()
        self._state: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
    
    def get_state(self, key: str) -> Dict[str, Any]:
        """Get or create state for a key.
        
        Args:
            key: State key (e.g., session ID)
            
        Returns:
            State dictionary
        """
        with self._lock:
            if key not in self._state:
                self._state[key] = self._initialize_state(key)
            return self._state[key]
    
    def set_state_value(self, key: str, field: str, value: Any) -> None:
        """Set a field in state.
        
        Args:
            key: State key
            field: Field name
            value: Value to set
        """
        with self._lock:
            state = self.get_state(key)
            state[field] = value
    
    def get_state_value(self, key: str, field: str, default: Any = None) -> Any:
        """Get a field from state.
        
        Args:
            key: State key
            field: Field name
            default: Default value if field not found
            
        Returns:
            Field value or default
        """
        with self._lock:
            state = self.get_state(key)
            return state.get(field, default)
    
    def cleanup_state(self) -> int:
        """Clean up expired or invalid state.
        
        Returns:
            Number of entries cleaned up
        """
        with self._lock:
            to_remove = [k for k, v in self._state.items() if self._should_cleanup(k, v)]
            for key in to_remove:
                del self._state[key]
            return len(to_remove)
    
    @abstractmethod
    def _initialize_state(self, key: str) -> Dict[str, Any]:
        """Initialize state for a new key.
        
        Args:
            key: State key
            
        Returns:
            Initial state dictionary
        """
        pass
    
    @abstractmethod
    def _should_cleanup(self, key: str, state: Dict[str, Any]) -> bool:
        """Check if state should be cleaned up.
        
        Args:
            key: State key
            state: State dictionary
            
        Returns:
            True if state should be removed
        """
        pass


class DataService(BaseService, Generic[T]):
    """Base class for services that load and manage data.
    
    Provides patterns for lazy loading, validation, and refresh.
    Subclasses should implement _load_data.
    """
    
    def __init__(self) -> None:
        super().__init__()
        self._data: Optional[T] = None
        self._loaded = False
        self._lock = threading.RLock()
    
    def get_data(self, force_reload: bool = False) -> T:
        """Get data, loading if necessary.
        
        Args:
            force_reload: Force reload even if already loaded
            
        Returns:
            Loaded data
            
        Raises:
            ServiceError: If data loading fails
        """
        with self._lock:
            if force_reload or not self._loaded:
                self._data = self._load_data()
                self._loaded = True
            if self._data is None:
                raise ServiceError("Failed to load data")
            return self._data
    
    def is_loaded(self) -> bool:
        """Check if data is loaded.
        
        Returns:
            True if data is loaded
        """
        with self._lock:
            return self._loaded
    
    def reload(self) -> T:
        """Force reload data.
        
        Returns:
            Reloaded data
        """
        return self.get_data(force_reload=True)
    
    @abstractmethod
    def _load_data(self) -> T:
        """Load data from source.
        
        Returns:
            Loaded data
            
        Raises:
            ServiceError: If loading fails
        """
        pass


class CachedService(BaseService, Generic[K, V]):
    """Base class for services with caching behavior.
    
    Provides thread-safe caching with TTL and size limits.
    Subclasses should implement _compute_value.
    """
    
    def __init__(self, ttl_seconds: Optional[int] = None, max_size: Optional[int] = None) -> None:
        """Initialize cached service.
        
        Args:
            ttl_seconds: Time-to-live for cache entries (None = no expiration)
            max_size: Maximum cache size (None = no limit)
        """
        super().__init__()
        self._cache: Dict[K, tuple[V, float]] = {}
        self._lock = threading.RLock()
        self._ttl_seconds = ttl_seconds
        self._max_size = max_size
    
    def get(self, key: K, force_recompute: bool = False) -> V:
        """Get cached value or compute it.
        
        Args:
            key: Cache key
            force_recompute: Force recompute even if cached
            
        Returns:
            Cached or computed value
        """
        with self._lock:
            now = time.time()
            
            # Check cache
            if not force_recompute and key in self._cache:
                value, timestamp = self._cache[key]
                if self._ttl_seconds is None or (now - timestamp) < self._ttl_seconds:
                    return value
            
            # Compute new value
            value = self._compute_value(key)
            
            # Store in cache
            self._cache[key] = (value, now)
            
            # Enforce size limit (simple LRU: remove oldest)
            if self._max_size is not None and len(self._cache) > self._max_size:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
            
            return value
    
    def invalidate(self, key: Optional[K] = None) -> None:
        """Invalidate cache entry or entire cache.
        
        Args:
            key: Cache key to invalidate (None = invalidate all)
        """
        with self._lock:
            if key is None:
                self._cache.clear()
            elif key in self._cache:
                del self._cache[key]
    
    def cleanup_expired(self) -> int:
        """Remove expired cache entries.
        
        Returns:
            Number of entries removed
        """
        if self._ttl_seconds is None:
            return 0
        
        with self._lock:
            now = time.time()
            expired = [k for k, (_, ts) in self._cache.items() if (now - ts) >= self._ttl_seconds]
            for key in expired:
                del self._cache[key]
            return len(expired)
    
    @abstractmethod
    def _compute_value(self, key: K) -> V:
        """Compute value for a cache key.
        
        Args:
            key: Cache key
            
        Returns:
            Computed value
            
        Raises:
            ServiceError: If computation fails
        """
        pass
