"""API endpoints for web services."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from code.file_setup.image_cache import ImageCache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Global image cache instance
_image_cache = ImageCache()


@router.get("/images/status")
async def get_download_status():
    """
    Get current image download status.
    
    Returns:
        JSON response with download status
    """
    import json
    
    status_file = Path("card_files/images/.download_status.json")
    
    if not status_file.exists():
        # Check cache statistics if no download in progress
        stats = _image_cache.cache_statistics()
        return JSONResponse({
            "running": False,
            "stats": stats
        })
    
    try:
        with status_file.open('r', encoding='utf-8') as f:
            status = json.load(f)
        return JSONResponse(status)
    except Exception as e:
        logger.warning(f"Could not read status file: {e}")
        return JSONResponse({
            "running": False,
            "error": str(e)
        })


@router.get("/images/debug")
async def get_image_debug():
    """
    Debug endpoint to check image cache configuration.
    
    Returns:
        JSON with debug information
    """
    import os
    from pathlib import Path
    
    base_dir = Path(_image_cache.base_dir)
    
    debug_info = {
        "cache_enabled": _image_cache.is_enabled(),
        "env_var": os.getenv("CACHE_CARD_IMAGES", "not set"),
        "base_dir": str(base_dir),
        "base_dir_exists": base_dir.exists(),
        "small_dir": str(base_dir / "small"),
        "small_dir_exists": (base_dir / "small").exists(),
        "normal_dir": str(base_dir / "normal"),
        "normal_dir_exists": (base_dir / "normal").exists(),
    }
    
    # Count files if directories exist
    if (base_dir / "small").exists():
        debug_info["small_count"] = len(list((base_dir / "small").glob("*.jpg")))
    if (base_dir / "normal").exists():
        debug_info["normal_count"] = len(list((base_dir / "normal").glob("*.jpg")))
    
    # Test with a sample card name
    test_card = "Lightning Bolt"
    debug_info["test_card"] = test_card
    test_path_small = _image_cache.get_image_path(test_card, "small")
    test_path_normal = _image_cache.get_image_path(test_card, "normal")
    debug_info["test_path_small"] = str(test_path_small) if test_path_small else None
    debug_info["test_path_normal"] = str(test_path_normal) if test_path_normal else None
    debug_info["test_exists_small"] = test_path_small.exists() if test_path_small else False
    debug_info["test_exists_normal"] = test_path_normal.exists() if test_path_normal else False
    
    return JSONResponse(debug_info)


@router.get("/images/{size}/{card_name}")
async def get_card_image(size: str, card_name: str, face: str = Query(default="front")):
    """
    Serve card image from cache or redirect to Scryfall API.
    
    Args:
        size: Image size ('small' or 'normal')
        card_name: Name of the card
        face: Which face to show ('front' or 'back') for DFC cards
        
    Returns:
        FileResponse if cached locally, RedirectResponse to Scryfall API otherwise
    """
    # Validate size parameter
    if size not in ["small", "normal"]:
        size = "normal"
    
    # Check if caching is enabled
    cache_enabled = _image_cache.is_enabled()
    
    # Check if image exists in cache
    if cache_enabled:
        image_path = None
        
        # For DFC cards, handle front/back faces differently
        if " // " in card_name:
            if face == "back":
                # For back face, ONLY try the back face name
                back_face = card_name.split(" // ")[1].strip()
                logger.debug(f"DFC back face requested: {back_face}")
                image_path = _image_cache.get_image_path(back_face, size)
            else:
                # For front face (or unspecified), try front face name
                front_face = card_name.split(" // ")[0].strip()
                logger.debug(f"DFC front face requested: {front_face}")
                image_path = _image_cache.get_image_path(front_face, size)
        else:
            # Single-faced card, try exact name
            image_path = _image_cache.get_image_path(card_name, size)
        
        if image_path and image_path.exists():
            logger.info(f"Serving cached image: {card_name} ({size}, {face})")
            return FileResponse(
                image_path,
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "public, max-age=31536000",  # 1 year
                }
            )
        else:
            logger.debug(f"No cached image found for: {card_name} (face: {face})")
    
    # Fallback to Scryfall API
    # For back face requests of DFC cards, we need the full card name
    scryfall_card_name = card_name
    scryfall_params = f"fuzzy={quote_plus(scryfall_card_name)}&format=image&version={size}"
    
    # If this is a back face request, try to find the full DFC name
    if face == "back":
        try:
            from code.services.all_cards_loader import AllCardsLoader
            loader = AllCardsLoader()
            df = loader.load()
            
            # Look for cards where this face name appears in the card_faces
            # The card name format is "Front // Back"
            matching = df[df['name'].str.contains(card_name, case=False, na=False, regex=False)]
            if not matching.empty:
                # Find DFC cards (containing ' // ')
                dfc_matches = matching[matching['name'].str.contains(' // ', na=False, regex=False)]
                if not dfc_matches.empty:
                    # Use the first matching DFC card's full name
                    full_name = dfc_matches.iloc[0]['name']
                    scryfall_card_name = full_name
                    # Add face parameter to Scryfall request
                    scryfall_params = f"exact={quote_plus(full_name)}&format=image&version={size}&face=back"
        except Exception as e:
            logger.warning(f"Could not lookup full card name for back face '{card_name}': {e}")
    
    scryfall_url = f"https://api.scryfall.com/cards/named?{scryfall_params}"
    return RedirectResponse(scryfall_url)


@router.post("/images/download")
async def download_images():
    """
    Start downloading card images in background.
    
    Returns:
        JSON response with status
    """
    if not _image_cache.is_enabled():
        return JSONResponse({
            "ok": False,
            "message": "Image caching is disabled. Set CACHE_CARD_IMAGES=1 to enable."
        }, status_code=400)
    
    # Write initial status
    try:
        status_dir = Path("card_files/images")
        status_dir.mkdir(parents=True, exist_ok=True)
        status_file = status_dir / ".download_status.json"
        
        import json
        with status_file.open('w', encoding='utf-8') as f:
            json.dump({
                "running": True,
                "phase": "bulk_data",
                "message": "Downloading Scryfall bulk data...",
                "current": 0,
                "total": 0,
                "percentage": 0
            }, f)
    except Exception as e:
        logger.warning(f"Could not write initial status: {e}")
    
    # Start download in background thread
    def _download_task():
        import json
        status_file = Path("card_files/images/.download_status.json")
        
        try:
            # Download bulk data first
            logger.info("[IMAGE DOWNLOAD] Starting bulk data download...")
            
            def bulk_progress(downloaded: int, total: int):
                """Progress callback for bulk data download."""
                try:
                    percentage = int(downloaded / total * 100) if total > 0 else 0
                    with status_file.open('w', encoding='utf-8') as f:
                        json.dump({
                            "running": True,
                            "phase": "bulk_data",
                            "message": f"Downloading bulk data: {percentage}%",
                            "current": downloaded,
                            "total": total,
                            "percentage": percentage
                        }, f)
                except Exception as e:
                    logger.warning(f"Could not update bulk progress: {e}")
            
            _image_cache.download_bulk_data(progress_callback=bulk_progress)
            
            # Download images
            logger.info("[IMAGE DOWNLOAD] Starting image downloads...")
            
            def image_progress(current: int, total: int, card_name: str):
                """Progress callback for image downloads."""
                try:
                    percentage = int(current / total * 100) if total > 0 else 0
                    with status_file.open('w', encoding='utf-8') as f:
                        json.dump({
                            "running": True,
                            "phase": "images",
                            "message": f"Downloading images: {card_name}",
                            "current": current,
                            "total": total,
                            "percentage": percentage
                        }, f)
                    
                    # Log progress every 100 cards
                    if current % 100 == 0:
                        logger.info(f"[IMAGE DOWNLOAD] Progress: {current}/{total} ({percentage}%)")
                        
                except Exception as e:
                    logger.warning(f"Could not update image progress: {e}")
            
            stats = _image_cache.download_images(progress_callback=image_progress)
            
            # Write completion status
            with status_file.open('w', encoding='utf-8') as f:
                json.dump({
                    "running": False,
                    "phase": "complete",
                    "message": f"Download complete: {stats.get('downloaded', 0)} new images",
                    "stats": stats,
                    "percentage": 100
                }, f)
            
            logger.info(f"[IMAGE DOWNLOAD] Complete: {stats}")
            
        except Exception as e:
            logger.error(f"[IMAGE DOWNLOAD] Failed: {e}", exc_info=True)
            try:
                with status_file.open('w', encoding='utf-8') as f:
                    json.dump({
                        "running": False,
                        "phase": "error",
                        "message": f"Download failed: {str(e)}",
                        "percentage": 0
                    }, f)
            except Exception:
                pass
    
    # Start background thread
    thread = threading.Thread(target=_download_task, daemon=True)
    thread.start()
    
    return JSONResponse({
        "ok": True,
        "message": "Image download started in background"
    }, status_code=202)
