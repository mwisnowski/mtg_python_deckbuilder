"""
Multi-Build Orchestrator - Parallel execution of identical deck builds.

Runs the same deck configuration N times in parallel to analyze variance.
"""

from __future__ import annotations
from typing import Any, Dict
from concurrent.futures import ThreadPoolExecutor
from .build_cache import BuildCache
from .tasks import get_session
from ..services import orchestrator as orch
from code.logging_util import get_logger

logger = get_logger(__name__)


class MultiBuildOrchestrator:
    """Manages parallel execution of multiple identical deck builds."""
    
    def __init__(self, max_parallel: int = 5):
        """
        Initialize orchestrator.
        
        Args:
            max_parallel: Maximum number of builds to run concurrently (default 5)
        """
        self.max_parallel = max_parallel
    
    def run_batch_parallel(self, batch_id: str, sid: str) -> None:
        """
        Run a batch of builds in parallel (blocking call).
        
        This should be called from a background task.
        
        Args:
            batch_id: Batch identifier
            sid: Session ID
        """
        logger.info(f"[Multi-Build] Starting parallel batch {batch_id} for session {sid}")
        
        sess = get_session(sid)
        batch_status = BuildCache.get_batch_status(sess, batch_id)
        
        if not batch_status:
            logger.error(f"[Multi-Build] Batch {batch_id} not found in session")
            return
        
        count = batch_status["count"]
        config = BuildCache.get_batch_config(sess, batch_id)
        
        if not config:
            logger.error(f"[Multi-Build] Config not found for batch {batch_id}")
            return
        
        logger.info(f"[Multi-Build] Running {count} builds in parallel (max {self.max_parallel} concurrent)")
        
        # Use ThreadPoolExecutor for parallel execution
        # Each build runs in its own thread to avoid blocking
        with ThreadPoolExecutor(max_workers=min(count, self.max_parallel)) as executor:
            futures = []
            
            for i in range(count):
                future = executor.submit(self._run_single_build, batch_id, i, config, sid)
                futures.append(future)
            
            # Wait for all builds to complete
            for i, future in enumerate(futures):
                try:
                    future.result()  # This will raise if the build failed
                    logger.info(f"[Multi-Build] Build {i+1}/{count} completed successfully")
                except Exception as e:
                    logger.error(f"[Multi-Build] Build {i+1}/{count} failed: {e}")
                    # Error already stored in _run_single_build
        
        logger.info(f"[Multi-Build] Batch {batch_id} completed")
    
    def _run_single_build(self, batch_id: str, build_index: int, config: Dict[str, Any], sid: str) -> None:
        """
        Run a single build and store the result.
        
        Args:
            batch_id: Batch identifier
            build_index: Index of this build (0-based)
            config: Deck configuration
            sid: Session ID
        """
        try:
            logger.info(f"[Multi-Build] Build {build_index}: Starting for batch {batch_id}")
            
            # Get a fresh session reference for this thread
            sess = get_session(sid)
            
            logger.debug(f"[Multi-Build] Build {build_index}: Creating build context")
            
            # Create a temporary build context for this specific build
            # We need to ensure each build has isolated state
            build_ctx = self._create_build_context(config, sess, build_index)
            
            logger.debug(f"[Multi-Build] Build {build_index}: Running all stages")
            
            # Run all stages to completion
            result = self._run_all_stages(build_ctx, build_index)
            
            logger.debug(f"[Multi-Build] Build {build_index}: Storing result")
            
            # Store the result
            BuildCache.store_build(sess, batch_id, build_index, result)
            
            logger.info(f"[Multi-Build] Build {build_index}: Completed, stored in batch {batch_id}")
            
        except Exception as e:
            logger.exception(f"[Multi-Build] Build {build_index}: Error - {e}")
            sess = get_session(sid)
            BuildCache.store_build_error(sess, batch_id, build_index, str(e))
    
    def _create_build_context(self, config: Dict[str, Any], sess: Dict[str, Any], build_index: int) -> Dict[str, Any]:
        """
        Create a build context from configuration.
        
        Args:
            config: Deck configuration
            sess: Session dictionary
            build_index: Index of this build
            
        Returns:
            Build context dict ready for orchestrator
        """
        # Import here to avoid circular dependencies
        from .build_utils import start_ctx_from_session
        
        # Create a temporary session-like dict with the config
        temp_sess = {
            "commander": config.get("commander"),
            "tags": config.get("tags", []),
            "tag_mode": config.get("tag_mode", "AND"),
            "bracket": config.get("bracket", 3),
            "ideals": config.get("ideals", {}),
            "prefer_combos": config.get("prefer_combos", False),
            "combo_target_count": config.get("combo_target_count"),
            "combo_balance": config.get("combo_balance"),
            "multi_copy": config.get("multi_copy"),
            "use_owned_only": config.get("use_owned_only", False),
            "prefer_owned": config.get("prefer_owned", False),
            "swap_mdfc_basics": config.get("swap_mdfc_basics", False),
            "include_cards": config.get("include_cards", []),
            "exclude_cards": config.get("exclude_cards", []),
            "enforcement_mode": config.get("enforcement_mode", "warn"),
            "allow_illegal": config.get("allow_illegal", False),
            "fuzzy_matching": config.get("fuzzy_matching", True),
            "locks": set(config.get("locks", [])),
            "replace_mode": True,
            # Add build index to context for debugging
            "batch_build_index": build_index
        }
        
        # Handle partner mechanics if present
        if config.get("partner_enabled"):
            temp_sess["partner_enabled"] = True
            if config.get("secondary_commander"):
                temp_sess["secondary_commander"] = config["secondary_commander"]
            if config.get("background"):
                temp_sess["background"] = config["background"]
            if config.get("partner_mode"):
                temp_sess["partner_mode"] = config["partner_mode"]
            if config.get("combined_commander"):
                temp_sess["combined_commander"] = config["combined_commander"]
        
        # Generate build context using existing utility
        ctx = start_ctx_from_session(temp_sess)
        
        return ctx
    
    def _run_all_stages(self, ctx: Dict[str, Any], build_index: int = 0) -> Dict[str, Any]:
        """
        Run all build stages to completion.
        
        Args:
            ctx: Build context
            build_index: Index of this build for logging
            
        Returns:
            Final result dict from orchestrator
        """
        stages = ctx.get("stages", [])
        result = None
        
        logger.debug(f"[Multi-Build] Build {build_index}: Starting stage loop ({len(stages)} stages)")
        
        iteration = 0
        max_iterations = 100  # Safety limit to prevent infinite loops
        
        while iteration < max_iterations:
            current_idx = ctx.get("idx", 0)
            if current_idx >= len(stages):
                logger.debug(f"[Multi-Build] Build {build_index}: All stages completed (idx={current_idx}/{len(stages)})")
                break
            
            stage_name = stages[current_idx].get("name", f"Stage {current_idx}") if current_idx < len(stages) else "Unknown"
            logger.debug(f"[Multi-Build] Build {build_index}: Running stage {current_idx}/{len(stages)}: {stage_name}")
            
            # Run stage with show_skipped=False for clean output
            result = orch.run_stage(ctx, rerun=False, show_skipped=False)
            
            # Check if build is done
            if result.get("done"):
                logger.debug(f"[Multi-Build] Build {build_index}: Build marked as done after stage {stage_name}")
                break
            
            iteration += 1
        
        if iteration >= max_iterations:
            logger.warning(f"[Multi-Build] Build {build_index}: Hit max iterations ({max_iterations}), possible infinite loop. Last stage: {stage_name}")
        
        logger.debug(f"[Multi-Build] Build {build_index}: Stage loop completed after {iteration} iterations")
        return result or {}


# Global orchestrator instance
_orchestrator = MultiBuildOrchestrator(max_parallel=5)


def queue_builds(config: Dict[str, Any], count: int, sid: str) -> str:
    """
    Queue a batch of builds for parallel execution.
    
    Args:
        config: Deck configuration
        count: Number of builds to run
        sid: Session ID
        
    Returns:
        batch_id: Unique identifier for this batch
    """
    sess = get_session(sid)
    batch_id = BuildCache.create_batch(sess, config, count)
    return batch_id


def run_batch_async(batch_id: str, sid: str) -> None:
    """
    Run a batch of builds in parallel (blocking call for background task).
    
    Args:
        batch_id: Batch identifier
        sid: Session ID
    """
    _orchestrator.run_batch_parallel(batch_id, sid)


def get_batch_status(batch_id: str, sid: str) -> Dict[str, Any]:
    """
    Get current status of a batch build.
    
    Args:
        batch_id: Batch identifier
        sid: Session ID
        
    Returns:
        Status dict with progress info
    """
    sess = get_session(sid)
    status = BuildCache.get_batch_status(sess, batch_id)
    return status or {"error": "Batch not found"}
