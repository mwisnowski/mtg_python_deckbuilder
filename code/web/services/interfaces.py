"""Service interfaces using Protocol for structural typing.

Defines contracts for different types of services without requiring inheritance.
Use these for type hints and dependency injection.
"""
from __future__ import annotations

from typing import Protocol, Any, Dict, List, Optional, TypeVar, runtime_checkable
import pandas as pd


T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


@runtime_checkable
class SessionService(Protocol):
    """Interface for session management services."""
    
    def new_session_id(self) -> str:
        """Create a new session ID.
        
        Returns:
            Unique session identifier
        """
        ...
    
    def get_session(self, session_id: Optional[str]) -> Dict[str, Any]:
        """Get or create session state.
        
        Args:
            session_id: Session identifier (creates new if None)
            
        Returns:
            Session state dictionary
        """
        ...
    
    def set_value(self, session_id: str, key: str, value: Any) -> None:
        """Set a value in session state.
        
        Args:
            session_id: Session identifier
            key: State key
            value: Value to store
        """
        ...
    
    def get_value(self, session_id: str, key: str, default: Any = None) -> Any:
        """Get a value from session state.
        
        Args:
            session_id: Session identifier
            key: State key
            default: Default value if key not found
            
        Returns:
            Stored value or default
        """
        ...
    
    def cleanup_expired(self) -> int:
        """Clean up expired sessions.
        
        Returns:
            Number of sessions cleaned up
        """
        ...


@runtime_checkable
class CardLoaderService(Protocol):
    """Interface for card data loading services."""
    
    def get_cards(self, force_reload: bool = False) -> pd.DataFrame:
        """Get card data.
        
        Args:
            force_reload: Force reload from source
            
        Returns:
            DataFrame with card data
        """
        ...
    
    def is_loaded(self) -> bool:
        """Check if card data is loaded.
        
        Returns:
            True if data is loaded
        """
        ...


@runtime_checkable
class CatalogService(Protocol):
    """Interface for catalog services (commanders, themes, etc.)."""
    
    def get_catalog(self, force_reload: bool = False) -> pd.DataFrame:
        """Get catalog data.
        
        Args:
            force_reload: Force reload from source
            
        Returns:
            DataFrame with catalog data
        """
        ...
    
    def search(self, query: str, **filters: Any) -> pd.DataFrame:
        """Search catalog with filters.
        
        Args:
            query: Search query string
            **filters: Additional filters
            
        Returns:
            Filtered DataFrame
        """
        ...


@runtime_checkable
class OwnedCardsService(Protocol):
    """Interface for owned cards management."""
    
    def get_owned_names(self) -> List[str]:
        """Get list of owned card names.
        
        Returns:
            List of card names
        """
        ...
    
    def add_owned_names(self, names: List[str]) -> None:
        """Add card names to owned list.
        
        Args:
            names: Card names to add
        """
        ...
    
    def remove_owned_name(self, name: str) -> bool:
        """Remove a card name from owned list.
        
        Args:
            name: Card name to remove
            
        Returns:
            True if removed, False if not found
        """
        ...
    
    def clear_owned(self) -> None:
        """Clear all owned cards."""
        ...
    
    def import_from_file(self, file_content: str, format_type: str) -> int:
        """Import owned cards from file content.
        
        Args:
            file_content: File content to parse
            format_type: Format type (csv, txt, etc.)
            
        Returns:
            Number of cards imported
        """
        ...


@runtime_checkable
class CacheService(Protocol[K, V]):
    """Interface for caching services."""
    
    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """Get cached value.
        
        Args:
            key: Cache key
            default: Default value if not found
            
        Returns:
            Cached value or default
        """
        ...
    
    def set(self, key: K, value: V, ttl: Optional[int] = None) -> None:
        """Set cached value.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (None = no expiration)
        """
        ...
    
    def invalidate(self, key: Optional[K] = None) -> None:
        """Invalidate cache entry or entire cache.
        
        Args:
            key: Cache key (None = invalidate all)
        """
        ...
    
    def cleanup_expired(self) -> int:
        """Remove expired cache entries.
        
        Returns:
            Number of entries removed
        """
        ...


@runtime_checkable
class BuildOrchestratorService(Protocol):
    """Interface for deck build orchestration."""
    
    def orchestrate_build(
        self,
        session_id: str,
        commander_name: str,
        theme_tags: List[str],
        **options: Any
    ) -> Dict[str, Any]:
        """Orchestrate a deck build.
        
        Args:
            session_id: Session identifier
            commander_name: Commander card name
            theme_tags: List of theme tags
            **options: Additional build options
            
        Returns:
            Build result dictionary
        """
        ...
    
    def get_build_status(self, session_id: str) -> Dict[str, Any]:
        """Get build status for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Build status dictionary
        """
        ...


@runtime_checkable
class ValidationService(Protocol):
    """Interface for validation services."""
    
    def validate_commander(self, name: str) -> tuple[bool, Optional[str]]:
        """Validate commander name.
        
        Args:
            name: Card name
            
        Returns:
            (is_valid, error_message) tuple
        """
        ...
    
    def validate_themes(self, themes: List[str]) -> tuple[bool, List[str]]:
        """Validate theme tags.
        
        Args:
            themes: List of theme tags
            
        Returns:
            (is_valid, invalid_themes) tuple
        """
        ...
    
    def normalize_card_name(self, name: str) -> str:
        """Normalize card name for lookups.
        
        Args:
            name: Raw card name
            
        Returns:
            Normalized card name
        """
        ...


@runtime_checkable
class TelemetryService(Protocol):
    """Interface for telemetry/metrics services."""
    
    def record_event(self, event_type: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """Record a telemetry event.
        
        Args:
            event_type: Type of event
            properties: Event properties
        """
        ...
    
    def record_timing(self, operation: str, duration_ms: float) -> None:
        """Record operation timing.
        
        Args:
            operation: Operation name
            duration_ms: Duration in milliseconds
        """
        ...
    
    def increment_counter(self, counter_name: str, value: int = 1) -> None:
        """Increment a counter.
        
        Args:
            counter_name: Counter name
            value: Increment value
        """
        ...
