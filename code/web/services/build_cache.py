"""
Build Cache - Session-based storage for multi-build batch results.

Stores completed deck builds in session for comparison view.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import time
import uuid


class BuildCache:
    """Manages storage and retrieval of batch build results in session."""
    
    @staticmethod
    def create_batch(sess: Dict[str, Any], config: Dict[str, Any], count: int) -> str:
        """
        Create a new batch build entry in session.
        
        Args:
            sess: Session dictionary
            config: Deck configuration (commander, themes, ideals, etc.)
            count: Number of builds in batch
            
        Returns:
            batch_id: Unique identifier for this batch
        """
        batch_id = f"batch_{uuid.uuid4().hex[:12]}"
        
        if "batch_builds" not in sess:
            sess["batch_builds"] = {}
        
        sess["batch_builds"][batch_id] = {
            "batch_id": batch_id,
            "config": config,
            "count": count,
            "completed": 0,
            "builds": [],
            "started_at": time.time(),
            "completed_at": None,
            "status": "running",  # running, completed, error
            "errors": []
        }
        
        return batch_id
    
    @staticmethod
    def store_build(sess: Dict[str, Any], batch_id: str, build_index: int, result: Dict[str, Any]) -> None:
        """
        Store a completed build result in the batch.
        
        Args:
            sess: Session dictionary
            batch_id: Batch identifier
            build_index: Index of this build (0-based)
            result: Deck build result from orchestrator
        """
        if "batch_builds" not in sess or batch_id not in sess["batch_builds"]:
            raise ValueError(f"Batch {batch_id} not found in session")
        
        batch = sess["batch_builds"][batch_id]
        
        # Ensure builds list has enough slots
        while len(batch["builds"]) <= build_index:
            batch["builds"].append(None)
        
        # Store build result with minimal data for comparison
        batch["builds"][build_index] = {
            "index": build_index,
            "result": result,
            "completed_at": time.time()
        }
        
        batch["completed"] += 1
        
        # Mark batch as completed if all builds done
        if batch["completed"] >= batch["count"]:
            batch["status"] = "completed"
            batch["completed_at"] = time.time()
    
    @staticmethod
    def store_build_error(sess: Dict[str, Any], batch_id: str, build_index: int, error: str) -> None:
        """
        Store an error for a failed build.
        
        Args:
            sess: Session dictionary
            batch_id: Batch identifier
            build_index: Index of this build (0-based)
            error: Error message
        """
        if "batch_builds" not in sess or batch_id not in sess["batch_builds"]:
            raise ValueError(f"Batch {batch_id} not found in session")
        
        batch = sess["batch_builds"][batch_id]
        
        batch["errors"].append({
            "build_index": build_index,
            "error": error,
            "timestamp": time.time()
        })
        
        batch["completed"] += 1
        
        # Mark batch as completed if all builds done (even with errors)
        if batch["completed"] >= batch["count"]:
            batch["status"] = "completed" if not batch["errors"] else "error"
            batch["completed_at"] = time.time()
    
    @staticmethod
    def get_batch_status(sess: Dict[str, Any], batch_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current status of a batch build.
        
        Args:
            sess: Session dictionary
            batch_id: Batch identifier
            
        Returns:
            Status dict with progress info, or None if not found
        """
        if "batch_builds" not in sess or batch_id not in sess["batch_builds"]:
            return None
        
        batch = sess["batch_builds"][batch_id]
        
        return {
            "batch_id": batch_id,
            "status": batch["status"],
            "count": batch["count"],
            "completed": batch["completed"],
            "progress_pct": int((batch["completed"] / batch["count"]) * 100) if batch["count"] > 0 else 0,
            "has_errors": len(batch["errors"]) > 0,
            "error_count": len(batch["errors"]),
            "elapsed_time": time.time() - batch["started_at"]
        }
    
    @staticmethod
    def get_batch_builds(sess: Dict[str, Any], batch_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get all completed builds for a batch.
        
        Args:
            sess: Session dictionary
            batch_id: Batch identifier
            
        Returns:
            List of build results, or None if batch not found
        """
        if "batch_builds" not in sess or batch_id not in sess["batch_builds"]:
            return None
        
        batch = sess["batch_builds"][batch_id]
        return [b for b in batch["builds"] if b is not None]
    
    @staticmethod
    def get_batch_config(sess: Dict[str, Any], batch_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the original configuration for a batch.
        
        Args:
            sess: Session dictionary
            batch_id: Batch identifier
            
        Returns:
            Config dict, or None if batch not found
        """
        if "batch_builds" not in sess or batch_id not in sess["batch_builds"]:
            return None
        
        return sess["batch_builds"][batch_id]["config"]
    
    @staticmethod
    def clear_batch(sess: Dict[str, Any], batch_id: str) -> bool:
        """
        Remove a batch from session.
        
        Args:
            sess: Session dictionary
            batch_id: Batch identifier
            
        Returns:
            True if batch was found and removed, False otherwise
        """
        if "batch_builds" not in sess or batch_id not in sess["batch_builds"]:
            return False
        
        del sess["batch_builds"][batch_id]
        return True
    
    @staticmethod
    def list_batches(sess: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        List all batches in session with summary info.
        
        Args:
            sess: Session dictionary
            
        Returns:
            List of batch summary dicts
        """
        if "batch_builds" not in sess:
            return []
        
        summaries = []
        for batch_id, batch in sess["batch_builds"].items():
            summaries.append({
                "batch_id": batch_id,
                "status": batch["status"],
                "count": batch["count"],
                "completed": batch["completed"],
                "commander": batch["config"].get("commander", "Unknown"),
                "started_at": batch["started_at"],
                "completed_at": batch.get("completed_at")
            })
        
        # Sort by start time, most recent first
        summaries.sort(key=lambda x: x["started_at"], reverse=True)
        return summaries
    
    @staticmethod
    def mark_synergy_exported(sess: Dict[str, Any], batch_id: str) -> bool:
        """
        Mark a batch as having its synergy deck exported (disables batch export).
        
        Args:
            sess: Session dictionary
            batch_id: Batch identifier
            
        Returns:
            True if batch was found and marked, False otherwise
        """
        if "batch_builds" not in sess or batch_id not in sess["batch_builds"]:
            return False
        
        sess["batch_builds"][batch_id]["synergy_exported"] = True
        sess["batch_builds"][batch_id]["synergy_exported_at"] = time.time()
        return True
    
    @staticmethod
    def is_synergy_exported(sess: Dict[str, Any], batch_id: str) -> bool:
        """
        Check if a batch's synergy deck has been exported.
        
        Args:
            sess: Session dictionary
            batch_id: Batch identifier
            
        Returns:
            True if synergy has been exported, False otherwise
        """
        if "batch_builds" not in sess or batch_id not in sess["batch_builds"]:
            return False
        
        return sess["batch_builds"][batch_id].get("synergy_exported", False)
