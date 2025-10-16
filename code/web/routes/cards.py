"""Card browsing and tag search API endpoints."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

# Import tag index from M3
try:
    from code.tagging.tag_index import get_tag_index
except ImportError:
    from tagging.tag_index import get_tag_index

# Import all cards loader
try:
    from code.services.all_cards_loader import AllCardsLoader
except ImportError:
    from services.all_cards_loader import AllCardsLoader

router = APIRouter(prefix="/api/cards", tags=["cards"])

# Cache for all_cards loader
_all_cards_loader: Optional[AllCardsLoader] = None


def _get_all_cards_loader() -> AllCardsLoader:
    """Get cached AllCardsLoader instance."""
    global _all_cards_loader
    if _all_cards_loader is None:
        _all_cards_loader = AllCardsLoader()
    return _all_cards_loader


@router.get("/by-tags")
async def search_by_tags(
    tags: str = Query(..., description="Comma-separated list of theme tags"),
    logic: str = Query("AND", description="Search logic: AND (intersection) or OR (union)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
) -> JSONResponse:
    """Search for cards by theme tags.
    
    Examples:
        /api/cards/by-tags?tags=tokens&logic=AND
        /api/cards/by-tags?tags=tokens,sacrifice&logic=AND
        /api/cards/by-tags?tags=lifegain,lifelink&logic=OR
    
    Args:
        tags: Comma-separated theme tags to search for
        logic: "AND" for cards with all tags, "OR" for cards with any tag
        limit: Maximum results to return
        
    Returns:
        JSON with matching cards and metadata
    """
    try:
        # Parse tags
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if not tag_list:
            return JSONResponse(
                status_code=400,
                content={"error": "No valid tags provided"}
            )
        
        # Get tag index and find matching cards
        tag_index = get_tag_index()
        
        if logic.upper() == "AND":
            card_names = tag_index.get_cards_with_all_tags(tag_list)
        elif logic.upper() == "OR":
            card_names = tag_index.get_cards_with_any_tags(tag_list)
        else:
            return JSONResponse(
                status_code=400,
                content={"error": f"Invalid logic: {logic}. Use AND or OR."}
            )
        
        # Load full card data
        all_cards = _get_all_cards_loader().load()
        matching_cards = all_cards[all_cards["name"].isin(card_names)]
        
        # Limit results
        matching_cards = matching_cards.head(limit)
        
        # Convert to dict
        results = matching_cards.to_dict("records")
        
        return JSONResponse(content={
            "tags": tag_list,
            "logic": logic.upper(),
            "total_matches": len(card_names),
            "returned": len(results),
            "limit": limit,
            "cards": results
        })
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Search failed: {str(e)}"}
        )


@router.get("/tags/search")
async def search_tags(
    q: str = Query(..., min_length=2, description="Tag prefix to search for"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of suggestions"),
) -> JSONResponse:
    """Autocomplete search for theme tags.
    
    Examples:
        /api/cards/tags/search?q=life
        /api/cards/tags/search?q=token&limit=5
    
    Args:
        q: Tag prefix (minimum 2 characters)
        limit: Maximum suggestions to return
        
    Returns:
        JSON with matching tags sorted by popularity
    """
    try:
        tag_index = get_tag_index()
        
        # Get all tags with counts - get_popular_tags returns all tags when given a high limit
        all_tags_with_counts = tag_index.get_popular_tags(limit=10000)
        
        # Filter by prefix (case-insensitive)
        prefix_lower = q.lower()
        matches = [
            (tag, count)
            for tag, count in all_tags_with_counts
            if tag.lower().startswith(prefix_lower)
        ]
        
        # Already sorted by popularity from get_popular_tags
        # Limit results
        matches = matches[:limit]
        
        return JSONResponse(content={
            "query": q,
            "matches": [
                {"tag": tag, "card_count": count}
                for tag, count in matches
            ]
        })
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Tag search failed: {str(e)}"}
        )


@router.get("/tags/popular")
async def get_popular_tags(
    limit: int = Query(50, ge=1, le=200, description="Number of popular tags to return"),
) -> JSONResponse:
    """Get the most popular theme tags by card count.
    
    Examples:
        /api/cards/tags/popular
        /api/cards/tags/popular?limit=20
    
    Args:
        limit: Maximum tags to return
        
    Returns:
        JSON with popular tags sorted by card count
    """
    try:
        tag_index = get_tag_index()
        popular = tag_index.get_popular_tags(limit=limit)
        
        return JSONResponse(content={
            "count": len(popular),
            "tags": [
                {"tag": tag, "card_count": count}
                for tag, count in popular
            ]
        })
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get popular tags: {str(e)}"}
        )
