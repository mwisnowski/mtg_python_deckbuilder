"""Service registry for dependency injection.

Provides a centralized registry for managing service instances and dependencies.
Supports singleton and factory patterns with thread-safe access.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Type, TypeVar, cast
import threading


T = TypeVar("T")


class ServiceRegistry:
    """Thread-safe service registry for dependency injection.
    
    Manages service instances and factories with support for:
    - Singleton services (one instance per registry)
    - Factory services (new instance per request)
    - Lazy initialization
    - Thread-safe access
    
    Example:
        registry = ServiceRegistry()
        registry.register_singleton(SessionService, session_service_instance)
        registry.register_factory(BuildService, lambda: BuildService(deps...))
        
        # Get services
        session_svc = registry.get(SessionService)
        build_svc = registry.get(BuildService)
    """
    
    def __init__(self) -> None:
        """Initialize empty registry."""
        self._singletons: Dict[Type[Any], Any] = {}
        self._factories: Dict[Type[Any], Callable[[], Any]] = {}
        self._lock = threading.RLock()
    
    def register_singleton(self, service_type: Type[T], instance: T) -> None:
        """Register a singleton service instance.
        
        Args:
            service_type: Service type/interface
            instance: Service instance to register
            
        Raises:
            ValueError: If service already registered
        """
        with self._lock:
            if service_type in self._singletons or service_type in self._factories:
                raise ValueError(f"Service {service_type.__name__} already registered")
            self._singletons[service_type] = instance
    
    def register_factory(self, service_type: Type[T], factory: Callable[[], T]) -> None:
        """Register a factory for creating service instances.
        
        Args:
            service_type: Service type/interface
            factory: Factory function that returns service instance
            
        Raises:
            ValueError: If service already registered
        """
        with self._lock:
            if service_type in self._singletons or service_type in self._factories:
                raise ValueError(f"Service {service_type.__name__} already registered")
            self._factories[service_type] = factory
    
    def register_lazy_singleton(self, service_type: Type[T], factory: Callable[[], T]) -> None:
        """Register a lazy-initialized singleton service.
        
        The factory will be called once on first access, then the instance is cached.
        
        Args:
            service_type: Service type/interface
            factory: Factory function that returns service instance
            
        Raises:
            ValueError: If service already registered
        """
        with self._lock:
            if service_type in self._singletons or service_type in self._factories:
                raise ValueError(f"Service {service_type.__name__} already registered")
            
            # Wrap factory to cache result
            instance_cache: Dict[str, Any] = {}
            
            def lazy_factory() -> T:
                if "instance" not in instance_cache:
                    instance_cache["instance"] = factory()
                return instance_cache["instance"]
            
            self._factories[service_type] = lazy_factory
    
    def get(self, service_type: Type[T]) -> T:
        """Get service instance.
        
        Args:
            service_type: Service type/interface
            
        Returns:
            Service instance
            
        Raises:
            KeyError: If service not registered
        """
        with self._lock:
            # Check singletons first
            if service_type in self._singletons:
                return cast(T, self._singletons[service_type])
            
            # Check factories
            if service_type in self._factories:
                return cast(T, self._factories[service_type]())
            
            raise KeyError(f"Service {service_type.__name__} not registered")
    
    def try_get(self, service_type: Type[T]) -> Optional[T]:
        """Try to get service instance, return None if not registered.
        
        Args:
            service_type: Service type/interface
            
        Returns:
            Service instance or None
        """
        try:
            return self.get(service_type)
        except KeyError:
            return None
    
    def is_registered(self, service_type: Type[Any]) -> bool:
        """Check if service is registered.
        
        Args:
            service_type: Service type/interface
            
        Returns:
            True if registered
        """
        with self._lock:
            return service_type in self._singletons or service_type in self._factories
    
    def unregister(self, service_type: Type[Any]) -> None:
        """Unregister a service.
        
        Args:
            service_type: Service type/interface
        """
        with self._lock:
            self._singletons.pop(service_type, None)
            self._factories.pop(service_type, None)
    
    def clear(self) -> None:
        """Clear all registered services."""
        with self._lock:
            self._singletons.clear()
            self._factories.clear()
    
    def get_registered_types(self) -> list[Type[Any]]:
        """Get list of all registered service types.
        
        Returns:
            List of service types
        """
        with self._lock:
            return list(self._singletons.keys()) + list(self._factories.keys())


# Global registry instance
_global_registry: Optional[ServiceRegistry] = None
_global_registry_lock = threading.Lock()


def get_registry() -> ServiceRegistry:
    """Get the global service registry instance.
    
    Creates registry on first access (lazy initialization).
    
    Returns:
        Global ServiceRegistry instance
    """
    global _global_registry
    
    if _global_registry is None:
        with _global_registry_lock:
            if _global_registry is None:
                _global_registry = ServiceRegistry()
    
    return _global_registry


def reset_registry() -> None:
    """Reset the global registry (primarily for testing).
    
    Clears all registered services and creates a new registry instance.
    """
    global _global_registry
    
    with _global_registry_lock:
        _global_registry = ServiceRegistry()
