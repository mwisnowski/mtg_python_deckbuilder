"""Routes for user documentation viewer."""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from code.web.services.docs_service import DocsService, NotFoundError, ServiceError
from ..app import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/help", tags=["help"])

# Initialize service
_docs_service = DocsService()


def _is_docs_enabled() -> bool:
    """Check if docs feature is enabled.
    
    Returns:
        True if ENABLE_WEB_DOCS=1
    """
    return os.getenv("ENABLE_WEB_DOCS", "1") == "1"


@router.get("/", response_class=HTMLResponse, name="docs_index")
async def docs_index(request: Request):
    """Display documentation index page.
    
    Lists all available user guides with titles and descriptions.
    """
    if not _is_docs_enabled():
        raise HTTPException(status_code=404, detail="Documentation not available")
    
    try:
        guides = _docs_service.list_guides()
        
        return templates.TemplateResponse(
            request,
            "docs/index.html",
            {
                "guides": guides,
                "page_title": "Documentation"
            }
        )
        
    except ServiceError as e:
        logger.error(f"Failed to load docs index: {e}")
        raise HTTPException(status_code=500, detail="Failed to load documentation")


@router.get("/{guide_name}", response_class=HTMLResponse, name="docs_guide")
async def docs_guide(request: Request, guide_name: str, reload: Optional[bool] = False):
    """Display a specific documentation guide.
    
    Args:
        guide_name: Name of guide (without .md extension)
        reload: Force reload from disk (admin/debug)
    """
    if not _is_docs_enabled():
        raise HTTPException(status_code=404, detail="Documentation not available")
    
    try:
        # Get metadata
        metadata = _docs_service.get_metadata(guide_name)
        
        # Get rendered content (HTML + TOC)
        content = _docs_service.get_guide(guide_name, force_reload=bool(reload))
        
        # Get all guides for sidebar navigation
        all_guides = _docs_service.list_guides()
        
        return templates.TemplateResponse(
            request,
            "docs/guide.html",
            {
                "guide_name": guide_name,
                "guide_title": metadata.title,
                "guide_description": metadata.description,
                "html_content": content.html,
                "toc_html": content.toc_html,
                "all_guides": all_guides,
                "page_title": metadata.title
            }
        )
        
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Guide not found: {guide_name}")
    except ServiceError as e:
        logger.error(f"Failed to load guide {guide_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load guide")


@router.post("/invalidate", name="docs_invalidate")
async def invalidate_cache(guide_name: Optional[str] = None):
    """Invalidate documentation cache (admin/debug).
    
    Args:
        guide_name: Specific guide to invalidate (None = all)
    """
    if not _is_docs_enabled():
        raise HTTPException(status_code=404, detail="Documentation not available")
    
    try:
        _docs_service.invalidate_guide(guide_name)
        return {"status": "ok", "invalidated": guide_name or "all"}
    except Exception as e:
        logger.error(f"Failed to invalidate cache: {e}")
        raise HTTPException(status_code=500, detail="Cache invalidation failed")
