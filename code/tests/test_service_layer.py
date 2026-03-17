"""Tests for service layer base classes, interfaces, and registry."""
from __future__ import annotations

import pytest
import time
from typing import Dict, Any

from code.web.services.base import (
    BaseService,
    StateService,
    DataService,
    CachedService,
    ServiceError,
    ValidationError,
    NotFoundError,
)
from code.web.services.registry import ServiceRegistry, get_registry, reset_registry
from code.web.services.tasks import SessionManager


class TestBaseService:
    """Test BaseService abstract base class."""
    
    def test_validation_helper(self):
        """Test _validate helper method."""
        service = BaseService()
        
        # Should not raise on True
        service._validate(True, "Should not raise")
        
        # Should raise on False
        with pytest.raises(ValidationError, match="Should raise"):
            service._validate(False, "Should raise")


class MockStateService(StateService):
    """Mock state service for testing."""
    
    def _initialize_state(self, key: str) -> Dict[str, Any]:
        return {"created": time.time(), "data": f"init-{key}"}
    
    def _should_cleanup(self, key: str, state: Dict[str, Any]) -> bool:
        # Cleanup if "expired" flag is set
        return state.get("expired", False)


class TestStateService:
    """Test StateService base class."""
    
    def test_get_state_creates_new(self):
        """Test that get_state creates new state."""
        service = MockStateService()
        state = service.get_state("test-key")
        
        assert "created" in state
        assert state["data"] == "init-test-key"
    
    def test_get_state_returns_existing(self):
        """Test that get_state returns existing state."""
        service = MockStateService()
        
        state1 = service.get_state("test-key")
        state1["custom"] = "value"
        
        state2 = service.get_state("test-key")
        assert state2 is state1
        assert state2["custom"] == "value"
    
    def test_set_and_get_value(self):
        """Test setting and getting state values."""
        service = MockStateService()
        
        service.set_state_value("key1", "field1", "value1")
        assert service.get_state_value("key1", "field1") == "value1"
        assert service.get_state_value("key1", "missing", "default") == "default"
    
    def test_cleanup_state(self):
        """Test cleanup of expired state."""
        service = MockStateService()
        
        # Create some state
        service.get_state("keep1")
        service.get_state("keep2")
        service.get_state("expire1")
        service.get_state("expire2")
        
        # Mark some as expired
        service.set_state_value("expire1", "expired", True)
        service.set_state_value("expire2", "expired", True)
        
        # Cleanup
        removed = service.cleanup_state()
        assert removed == 2
        
        # Verify expired are gone
        state = service._state
        assert "keep1" in state
        assert "keep2" in state
        assert "expire1" not in state
        assert "expire2" not in state


class MockDataService(DataService[Dict[str, Any]]):
    """Mock data service for testing."""
    
    def __init__(self, data: Dict[str, Any]):
        super().__init__()
        self._mock_data = data
    
    def _load_data(self) -> Dict[str, Any]:
        return self._mock_data.copy()


class TestDataService:
    """Test DataService base class."""
    
    def test_lazy_loading(self):
        """Test that data is loaded lazily."""
        service = MockDataService({"key": "value"})
        
        assert not service.is_loaded()
        data = service.get_data()
        assert service.is_loaded()
        assert data["key"] == "value"
    
    def test_cached_loading(self):
        """Test that data is cached after first load."""
        service = MockDataService({"key": "value"})
        
        data1 = service.get_data()
        data1["modified"] = True
        
        data2 = service.get_data()
        assert data2 is data1
        assert data2["modified"]
    
    def test_force_reload(self):
        """Test force reload of data."""
        service = MockDataService({"key": "value"})
        
        data1 = service.get_data()
        data1["modified"] = True
        
        data2 = service.get_data(force_reload=True)
        assert data2 is not data1
        assert "modified" not in data2


class MockCachedService(CachedService[str, int]):
    """Mock cached service for testing."""
    
    def __init__(self, ttl_seconds: int | None = None, max_size: int | None = None):
        super().__init__(ttl_seconds=ttl_seconds, max_size=max_size)
        self.compute_count = 0
    
    def _compute_value(self, key: str) -> int:
        self.compute_count += 1
        return len(key)


class TestCachedService:
    """Test CachedService base class."""
    
    def test_cache_hit(self):
        """Test that values are cached."""
        service = MockCachedService()
        
        value1 = service.get("hello")
        assert value1 == 5
        assert service.compute_count == 1
        
        value2 = service.get("hello")
        assert value2 == 5
        assert service.compute_count == 1  # Should not recompute
    
    def test_cache_miss(self):
        """Test cache miss computes new value."""
        service = MockCachedService()
        
        value1 = service.get("hello")
        value2 = service.get("world")
        
        assert value1 == 5
        assert value2 == 5
        assert service.compute_count == 2
    
    def test_ttl_expiration(self):
        """Test TTL-based expiration."""
        service = MockCachedService(ttl_seconds=1)
        
        value1 = service.get("hello")
        assert service.compute_count == 1
        
        # Should hit cache immediately
        value2 = service.get("hello")
        assert service.compute_count == 1
        
        # Wait for expiration
        time.sleep(1.1)
        
        value3 = service.get("hello")
        assert service.compute_count == 2  # Should recompute
    
    def test_max_size_limit(self):
        """Test cache size limit."""
        service = MockCachedService(max_size=2)
        
        service.get("key1")
        service.get("key2")
        service.get("key3")  # Should evict oldest (key1)
        
        # key1 should be evicted
        assert len(service._cache) == 2
        assert "key1" not in service._cache
        assert "key2" in service._cache
        assert "key3" in service._cache
    
    def test_invalidate_single(self):
        """Test invalidating single cache entry."""
        service = MockCachedService()
        
        service.get("key1")
        service.get("key2")
        
        service.invalidate("key1")
        
        assert "key1" not in service._cache
        assert "key2" in service._cache
    
    def test_invalidate_all(self):
        """Test invalidating entire cache."""
        service = MockCachedService()
        
        service.get("key1")
        service.get("key2")
        
        service.invalidate()
        
        assert len(service._cache) == 0


class MockService:
    """Mock service for registry testing."""
    
    def __init__(self, value: str):
        self.value = value


class TestServiceRegistry:
    """Test ServiceRegistry for dependency injection."""
    
    def test_register_and_get_singleton(self):
        """Test registering and retrieving singleton."""
        registry = ServiceRegistry()
        instance = MockService("test")
        
        registry.register_singleton(MockService, instance)
        retrieved = registry.get(MockService)
        
        assert retrieved is instance
        assert retrieved.value == "test"
    
    def test_register_and_get_factory(self):
        """Test registering and retrieving from factory."""
        registry = ServiceRegistry()
        
        registry.register_factory(MockService, lambda: MockService("factory"))
        
        instance1 = registry.get(MockService)
        instance2 = registry.get(MockService)
        
        assert instance1 is not instance2  # Factory creates new instances
        assert instance1.value == "factory"
        assert instance2.value == "factory"
    
    def test_lazy_singleton(self):
        """Test lazy-initialized singleton."""
        registry = ServiceRegistry()
        call_count = {"count": 0}
        
        def factory():
            call_count["count"] += 1
            return MockService("lazy")
        
        registry.register_lazy_singleton(MockService, factory)
        
        instance1 = registry.get(MockService)
        assert call_count["count"] == 1
        
        instance2 = registry.get(MockService)
        assert call_count["count"] == 1  # Should not call factory again
        assert instance1 is instance2
    
    def test_duplicate_registration_error(self):
        """Test error on duplicate registration."""
        registry = ServiceRegistry()
        registry.register_singleton(MockService, MockService("first"))
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register_singleton(MockService, MockService("second"))
    
    def test_get_unregistered_error(self):
        """Test error on getting unregistered service."""
        registry = ServiceRegistry()
        
        with pytest.raises(KeyError, match="not registered"):
            registry.get(MockService)
    
    def test_try_get(self):
        """Test try_get returns None for unregistered."""
        registry = ServiceRegistry()
        
        result = registry.try_get(MockService)
        assert result is None
        
        registry.register_singleton(MockService, MockService("test"))
        result = registry.try_get(MockService)
        assert result is not None
    
    def test_is_registered(self):
        """Test checking if service is registered."""
        registry = ServiceRegistry()
        
        assert not registry.is_registered(MockService)
        
        registry.register_singleton(MockService, MockService("test"))
        assert registry.is_registered(MockService)
    
    def test_unregister(self):
        """Test unregistering a service."""
        registry = ServiceRegistry()
        registry.register_singleton(MockService, MockService("test"))
        
        assert registry.is_registered(MockService)
        registry.unregister(MockService)
        assert not registry.is_registered(MockService)
    
    def test_clear(self):
        """Test clearing all services."""
        registry = ServiceRegistry()
        registry.register_singleton(MockService, MockService("test"))
        
        registry.clear()
        assert not registry.is_registered(MockService)


class TestSessionManager:
    """Test SessionManager refactored service."""
    
    def test_new_session_id(self):
        """Test creating new session IDs."""
        manager = SessionManager()
        
        sid1 = manager.new_session_id()
        sid2 = manager.new_session_id()
        
        assert isinstance(sid1, str)
        assert isinstance(sid2, str)
        assert sid1 != sid2
        assert len(sid1) == 32  # UUID hex is 32 chars
    
    def test_get_session_creates_new(self):
        """Test get_session with None creates new."""
        manager = SessionManager()
        
        session = manager.get_session(None)
        assert "created" in session
        assert "updated" in session
    
    def test_get_session_returns_existing(self):
        """Test get_session returns existing session."""
        manager = SessionManager()
        
        sid = manager.new_session_id()
        session1 = manager.get_session(sid)
        session1["custom"] = "data"
        
        session2 = manager.get_session(sid)
        assert session2 is session1
        assert session2["custom"] == "data"
    
    def test_set_and_get_value(self):
        """Test setting and getting session values."""
        manager = SessionManager()
        sid = manager.new_session_id()
        
        manager.set_value(sid, "key1", "value1")
        assert manager.get_value(sid, "key1") == "value1"
        assert manager.get_value(sid, "missing", "default") == "default"
    
    def test_cleanup_expired_sessions(self):
        """Test cleanup of expired sessions."""
        manager = SessionManager(ttl_seconds=1)
        
        sid1 = manager.new_session_id()
        sid2 = manager.new_session_id()
        
        manager.get_session(sid1)
        time.sleep(1.1)  # Let sid1 expire
        manager.get_session(sid2)  # sid2 is fresh
        
        removed = manager.cleanup_state()
        assert removed == 1
        
        # sid1 should be gone, sid2 should exist
        assert sid1 not in manager._state
        assert sid2 in manager._state
