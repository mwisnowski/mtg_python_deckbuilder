from __future__ import annotations

import time
import uuid
from typing import Dict, Any, Optional

from .base import StateService
from .interfaces import SessionService


# Session TTL: 8 hours
SESSION_TTL_SECONDS = 60 * 60 * 8


class SessionManager(StateService):
    """Session management service.
    
    Manages user sessions with automatic TTL-based cleanup.
    Thread-safe with in-memory storage.
    """
    
    def __init__(self, ttl_seconds: int = SESSION_TTL_SECONDS) -> None:
        """Initialize session manager.
        
        Args:
            ttl_seconds: Session time-to-live in seconds
        """
        super().__init__()
        self._ttl_seconds = ttl_seconds
    
    def new_session_id(self) -> str:
        """Create a new session ID.
        
        Returns:
            Unique session identifier
        """
        return uuid.uuid4().hex
    
    def touch_session(self, session_id: str) -> Dict[str, Any]:
        """Update session last access time.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session state dictionary
        """
        now = time.time()
        state = self.get_state(session_id)
        state["updated"] = now
        return state
    
    def get_session(self, session_id: Optional[str]) -> Dict[str, Any]:
        """Get or create session state.
        
        Args:
            session_id: Session identifier (creates new if None)
            
        Returns:
            Session state dictionary
        """
        if not session_id:
            session_id = self.new_session_id()
        return self.touch_session(session_id)
    
    def set_value(self, session_id: str, key: str, value: Any) -> None:
        """Set a value in session state.
        
        Args:
            session_id: Session identifier
            key: State key
            value: Value to store
        """
        self.touch_session(session_id)[key] = value
    
    def get_value(self, session_id: str, key: str, default: Any = None) -> Any:
        """Get a value from session state.
        
        Args:
            session_id: Session identifier
            key: State key
            default: Default value if key not found
            
        Returns:
            Stored value or default
        """
        return self.touch_session(session_id).get(key, default)
    
    def _initialize_state(self, key: str) -> Dict[str, Any]:
        """Initialize state for a new session.
        
        Args:
            key: Session ID
            
        Returns:
            Initial session state
        """
        now = time.time()
        return {"created": now, "updated": now}
    
    def _should_cleanup(self, key: str, state: Dict[str, Any]) -> bool:
        """Check if session should be cleaned up.
        
        Args:
            key: Session ID
            state: Session state
            
        Returns:
            True if session is expired
        """
        now = time.time()
        updated = state.get("updated", 0)
        return (now - updated) > self._ttl_seconds


# Global session manager instance
_session_manager: Optional[SessionManager] = None


def _get_manager() -> SessionManager:
    """Get or create global session manager instance.
    
    Returns:
        SessionManager instance
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


# Backward-compatible function API
def new_sid() -> str:
    """Create a new session ID.
    
    Returns:
        Unique session identifier
    """
    return _get_manager().new_session_id()


def touch_session(sid: str) -> Dict[str, Any]:
    """Update session last access time.
    
    Args:
        sid: Session identifier
        
    Returns:
        Session state dictionary
    """
    return _get_manager().touch_session(sid)


def get_session(sid: Optional[str]) -> Dict[str, Any]:
    """Get or create session state.
    
    Args:
        sid: Session identifier (creates new if None)
        
    Returns:
        Session state dictionary
    """
    return _get_manager().get_session(sid)


def set_session_value(sid: str, key: str, value: Any) -> None:
    """Set a value in session state.
    
    Args:
        sid: Session identifier
        key: State key
        value: Value to store
    """
    _get_manager().set_value(sid, key, value)


def get_session_value(sid: str, key: str, default: Any = None) -> Any:
    """Get a value from session state.
    
    Args:
        sid: Session identifier
        key: State key
        default: Default value if key not found
        
    Returns:
        Stored value or default
    """
    return _get_manager().get_value(sid, key, default)


def cleanup_expired() -> int:
    """Clean up expired sessions.
    
    Returns:
        Number of sessions cleaned up
    """
    return _get_manager().cleanup_state()
