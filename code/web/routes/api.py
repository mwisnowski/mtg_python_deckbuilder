"""API endpoints for web services."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from code.file_setup.image_cache import ImageCache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Global image cache instance
_image_cache = ImageCache()

# ---------------------------------------------------------------------------
# Scryfall fallback rate limiter
# /cards/named endpoint rate limit: 2 req/sec (500 ms between requests).
# We use a simple async token bucket so concurrent image requests are spread
# out rather than all firing at Scryfall simultaneously.
# ---------------------------------------------------------------------------
_SCRYFALL_MIN_INTERVAL = 0.50  # seconds between fallback redirects (2 req/s per Scryfall docs)
_scryfall_lock = asyncio.Lock()
_scryfall_last_redirect: float = 0.0
_SCRYFALL_USER_AGENT = "MTGPythonDeckbuilder/1.0 (contact via GitHub)"


async def _scryfall_rate_limit() -> None:
    """Throttle Scryfall API fallback redirects to ≤10 req/sec."""
    global _scryfall_last_redirect
    async with _scryfall_lock:
        now = time.monotonic()
        wait = _SCRYFALL_MIN_INTERVAL - (now - _scryfall_last_redirect)
        if wait > 0:
            await asyncio.sleep(wait)
        _scryfall_last_redirect = time.monotonic()


async def _resolve_scryfall_image_url(
    name: str, size: str, *, exact: bool = False, face: str = "front"
) -> Optional[str]:
    """Resolve a direct Scryfall CDN image URL server-side.

    api.scryfall.com requires a User-Agent and Accept header on every
    request; redirecting a client straight to it (the previous approach)
    fails with a 400 for clients that don't send those headers -- observed
    with the mobile app's HTTP client for basic lands, which always hit
    this fallback (not cached locally). Fetching the card JSON here (with
    proper headers) and returning the plain CDN image URL
    (cards.scryfall.io, no special headers required) sidesteps that.
    """
    params = {"exact": name} if exact else {"fuzzy": name}
    await _scryfall_rate_limit()
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _SCRYFALL_USER_AGENT, "Accept": "application/json"},
            timeout=10.0,
        ) as client:
            resp = await client.get("https://api.scryfall.com/cards/named", params=params)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        logger.warning(f"Scryfall image lookup failed for '{name}': {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error resolving Scryfall image for '{name}': {e}")
        return None

    image_uris = data.get("image_uris")
    if not image_uris:
        faces = data.get("card_faces") or []
        face_index = 1 if face == "back" and len(faces) > 1 else 0
        if face_index < len(faces):
            image_uris = faces[face_index].get("image_uris")
    if not image_uris:
        return None
    return image_uris.get(size) or image_uris.get("normal")


@router.get("/images/status")
async def get_download_status():
    """
    Get current image download status.
    
    Returns:
        JSON response with download status
    """
    import json
    
    status_file = Path("card_files/images/.download_status.json")
    last_result_file = Path("card_files/images/.last_download_result.json")
    
    if not status_file.exists():
        # No active download - return cache stats plus last download result if available
        stats = _image_cache.cache_statistics()
        last_download = None
        if last_result_file.exists():
            try:
                with last_result_file.open('r', encoding='utf-8') as f:
                    last_download = json.load(f)
            except Exception:
                pass
        return JSONResponse({
            "running": False,
            "last_download": last_download,
            "stats": stats
        })
    
    try:
        with status_file.open('r', encoding='utf-8') as f:
            status = json.load(f)
        
        # If download is complete (or errored), persist result, clean up status file
        if not status.get("running", False):
            try:
                with last_result_file.open('w', encoding='utf-8') as f:
                    json.dump(status, f)
            except Exception:
                pass
            try:
                status_file.unlink()
            except Exception:
                pass
            cache_stats = _image_cache.cache_statistics()
            return JSONResponse({
                "running": False,
                "last_download": status,
                "stats": cache_stats
            })
        
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
        size: Image size ('small', 'normal', or 'art_crop')
        card_name: Name of the card
        face: Which face to show ('front' or 'back') for DFC cards
        
    Returns:
        FileResponse if cached locally, RedirectResponse to Scryfall API otherwise
    """
    # Validate size parameter
    if size not in ["small", "normal", "art_crop"]:
        size = "normal"
    
    # Check if caching is enabled (local cache only stores small/normal; art_crop always redirects)
    cache_enabled = _image_cache.is_enabled() and size != "art_crop"
    
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
            logger.debug(f"Serving cached image: {card_name} ({size}, {face})")
            return FileResponse(
                image_path,
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "public, max-age=31536000",  # 1 year
                }
            )
        else:
            logger.debug(f"No cached image found for: {card_name} (face: {face})")
    
    # Fallback to Scryfall, resolved server-side (api.scryfall.com rejects
    # requests missing headers most simple HTTP clients don't send -- see
    # _resolve_scryfall_image_url).
    scryfall_card_name = card_name
    use_exact = False

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
                    scryfall_card_name = dfc_matches.iloc[0]['name']
                    use_exact = True
        except Exception as e:
            logger.warning(f"Could not lookup full card name for back face '{card_name}': {e}")

    image_url = await _resolve_scryfall_image_url(scryfall_card_name, size, exact=use_exact, face=face)
    if image_url:
        return RedirectResponse(image_url)

    # Last resort -- redirect straight to the Scryfall API; works for
    # clients that do send the headers it requires (e.g. browsers).
    scryfall_params = f"fuzzy={quote_plus(card_name)}&format=image&version={size}"
    return RedirectResponse(f"https://api.scryfall.com/cards/named?{scryfall_params}")


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
