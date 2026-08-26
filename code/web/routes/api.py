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


async def _resolve_scryfall_token_image_url(name: str, size: str) -> Optional[str]:
    """Resolve a token image via Scryfall's search API, restricted to tokens.

    Token face names frequently collide with unrelated real cards (e.g. the
    "Start Your Engines!" token vs. the real Aetherdrift sorcery), so the
    plain `/cards/named` fuzzy lookup used by `_resolve_scryfall_image_url()`
    is unsafe here -- it can resolve to the wrong (non-token) card. This
    restricts the search to `is:token` results.
    """
    query = f'!"{name}" is:token'
    await _scryfall_rate_limit()
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _SCRYFALL_USER_AGENT, "Accept": "application/json"},
            timeout=10.0,
        ) as client:
            resp = await client.get(
                "https://api.scryfall.com/cards/search",
                params={"q": query, "unique": "prints", "order": "released"},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        logger.warning(f"Scryfall token image search failed for '{name}': {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error resolving Scryfall token image for '{name}': {e}")
        return None

    results = data.get("data") or []
    if not results:
        return None
    card = results[0]
    image_uris = card.get("image_uris")
    if not image_uris:
        faces = card.get("card_faces") or []
        if faces:
            image_uris = faces[0].get("image_uris")
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
        # cache_statistics() scans every per-card image folder and can take tens of
        # seconds; run it off the event loop so it doesn't stall every other request.
        stats = await asyncio.to_thread(_image_cache.cache_statistics)
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
            cache_stats = await asyncio.to_thread(_image_cache.cache_statistics)
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


@router.get("/printings/{card_name}")
async def get_card_printings(card_name: str):
    """
    List known paper printings for a card, from the printings metadata
    index (`card_files/processed/card_printings.parquet`). Returns an
    empty list if the index hasn't been built yet (see
    `ImageCache.build_printings_index()`).

    Args:
        card_name: Name of the card (or a single face's name for DFCs). The
            printings index is keyed per-face, so a combined double-faced/
            split/flip/meld name ("A // B") is resolved to its front face
            ("A") before lookup -- both faces of a physical printing share
            the same set of printings, so this works regardless of which
            face a caller (e.g. the mobile app) is currently displaying.

    Returns:
        JSON with a list of printings (set, set_name, collector_number,
        released_at, scryfall_id, is_default, ...) and the default printing's
        scryfall_id.
    """
    face_name = card_name.split(" // ")[0].strip() if " // " in card_name else card_name
    printings = _image_cache.get_printings(face_name)
    default_id = _image_cache.get_default_printing_id(face_name)
    return JSONResponse({
        "card_name": card_name,
        "default_scryfall_id": default_id,
        "printings": printings,
    })


@router.get("/images/tokens/status")
async def get_token_download_status():
    """Get current token/emblem image download status (mirrors /images/status)."""
    import json

    status_file = Path("card_files/images/tokens/.download_status.json")
    last_result_file = Path("card_files/images/tokens/.last_download_result.json")

    if not status_file.exists():
        stats = await asyncio.to_thread(_image_cache.token_cache_statistics)
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
            cache_stats = await asyncio.to_thread(_image_cache.token_cache_statistics)
            return JSONResponse({
                "running": False,
                "last_download": status,
                "stats": cache_stats
            })

        return JSONResponse(status)
    except Exception as e:
        logger.warning(f"Could not read token status file: {e}")
        return JSONResponse({
            "running": False,
            "error": str(e)
        })


@router.post("/images/download-tokens")
async def download_token_images():
    """
    Start downloading token/emblem images in background (separate from real
    card images -- see roadmap_39, Milestone 3).

    Returns:
        JSON response with status
    """
    if not _image_cache.is_enabled():
        return JSONResponse({
            "ok": False,
            "message": "Image caching is disabled. Set CACHE_CARD_IMAGES=1 to enable."
        }, status_code=400)

    tokens_path = Path("card_files/processed/tokens.parquet")
    if not tokens_path.exists():
        return JSONResponse({
            "ok": False,
            "message": "Token/emblem catalog not found. Run the full setup pipeline first."
        }, status_code=400)

    try:
        status_dir = Path("card_files/images/tokens")
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
        logger.warning(f"Could not write initial token status: {e}")

    def _download_task():
        import json
        import pandas as pd
        status_file = Path("card_files/images/tokens/.download_status.json")

        try:
            logger.info("[TOKEN IMAGE DOWNLOAD] Starting bulk data download...")

            def bulk_progress(downloaded: int, total: int):
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
                    logger.warning(f"Could not update token bulk progress: {e}")

            if not _image_cache.bulk_data_path.exists():
                _image_cache.download_bulk_data(progress_callback=bulk_progress)

            logger.info("[TOKEN IMAGE DOWNLOAD] Building token printings index...")
            with status_file.open('w', encoding='utf-8') as f:
                json.dump({
                    "running": True,
                    "phase": "index",
                    "message": "Building token/emblem printings index...",
                    "current": 0,
                    "total": 0,
                    "percentage": 0
                }, f)

            tokens_df = pd.read_parquet(tokens_path)
            _image_cache.build_token_printings_index(tokens_df)

            logger.info("[TOKEN IMAGE DOWNLOAD] Starting image downloads...")

            def image_progress(current: int, total: int, face_name: str):
                try:
                    percentage = int(current / total * 100) if total > 0 else 0
                    with status_file.open('w', encoding='utf-8') as f:
                        json.dump({
                            "running": True,
                            "phase": "images",
                            "message": f"Downloading images: {face_name}",
                            "current": current,
                            "total": total,
                            "percentage": percentage
                        }, f)
                    if current % 200 == 0:
                        logger.info(f"[TOKEN IMAGE DOWNLOAD] Progress: {current}/{total} ({percentage}%)")
                except Exception as e:
                    logger.warning(f"Could not update token image progress: {e}")

            stats = _image_cache.download_all_token_printings(progress_callback=image_progress)

            with status_file.open('w', encoding='utf-8') as f:
                json.dump({
                    "running": False,
                    "phase": "complete",
                    "message": f"Download complete: {stats.get('downloaded', 0)} new images",
                    "stats": stats,
                    "percentage": 100
                }, f)

            logger.info(f"[TOKEN IMAGE DOWNLOAD] Complete: {stats}")

        except Exception as e:
            logger.error(f"[TOKEN IMAGE DOWNLOAD] Failed: {e}", exc_info=True)
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

    thread = threading.Thread(target=_download_task, daemon=True)
    thread.start()

    return JSONResponse({
        "ok": True,
        "message": "Token/emblem image download started in background"
    }, status_code=202)


# NOTE: The two routes above (/images/tokens/status, /images/download-tokens) must be
# registered before the generic /images/{size}/{card_name} route below, otherwise
# FastAPI matches "tokens" as {size} and "status"/"download-tokens" as {card_name}.
@router.get("/images/token/{size}/{token_name}")
async def get_token_image(
    size: str,
    token_name: str,
    power: Optional[str] = Query(default=None),
    toughness: Optional[str] = Query(default=None),
    type_line: Optional[str] = Query(default=None),
    colors: Optional[str] = Query(default=None),
    text_hash: Optional[str] = Query(
        default=None,
        description="Fingerprint of the identity's ability text (see TokenRef.text_hash()), disambiguates same name/type/pt/colors variants",
    ),
    printing: Optional[str] = Query(
        default=None,
        description="Scryfall ID of a specific printing to show, instead of the identity's default printing",
    ),
):
    """Serve a cached token/emblem image (roadmap_39, Milestone 5).

    Token identity is name + type + power/toughness + colors + ability text
    (multiple distinct tokens can share a name, type, and even power/toughness
    -- e.g. a plain white 1/1 Soldier vs. a red/white 1/1 Soldier, or a
    vanilla 1/1 Fish vs. one that "can't be blocked") -- see
    `ImageCache.get_default_token_printing_id()`. Falls back to an on-demand
    single-image download if the token/emblem printings index has a row but
    the image hasn't been downloaded to disk yet, then to a live Scryfall
    token search if the token isn't in the index at all (e.g. image cache
    disabled, or the token image download step hasn't been run).
    """
    if size not in ("small", "normal", "art_crop"):
        size = "normal"

    if _image_cache.is_enabled() and size != "art_crop":
        target_id = printing or _image_cache.get_default_token_printing_id(token_name, power, toughness, type_line, colors, text_hash)
        if target_id:
            image_path = _image_cache.get_token_printing_image_path(token_name, target_id, size)
            if not image_path.exists():
                matches = [
                    row for row in _image_cache.get_token_printings(token_name, power, toughness, type_line, colors, text_hash)
                    if str(row.get("scryfall_id")) == target_id
                ]
                if matches:
                    image_url = matches[0].get(f"image_url_{size}") or matches[0].get("image_url_normal")
                    if image_url:
                        _image_cache._download_image(image_url, image_path)
            if image_path.exists():
                return FileResponse(
                    image_path,
                    media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=31536000"},
                )

    # No cached/downloadable token image -- best-effort live Scryfall token search
    # (restricted to is:token results to avoid colliding with unrelated real cards
    # that share the same name, e.g. "Start Your Engines!").
    image_url = await _resolve_scryfall_token_image_url(token_name, size)
    if image_url:
        return RedirectResponse(image_url)
    query = quote_plus(f'!"{token_name}" is:token')
    return RedirectResponse(f"https://api.scryfall.com/cards/search?q={query}&format=image&version={size}")


@router.get("/token-printings/{token_name}")
async def get_token_printings(
    token_name: str,
    power: Optional[str] = Query(default=None),
    toughness: Optional[str] = Query(default=None),
    type_line: Optional[str] = Query(default=None),
    colors: Optional[str] = Query(default=None),
    text_hash: Optional[str] = Query(
        default=None,
        description="Fingerprint of the identity's ability text (see TokenRef.text_hash()), disambiguates same name/type/pt/colors variants",
    ),
):
    """List known paper printings for a token/emblem identity, mirroring
    `/printings/{card_name}` for real cards but keyed by the token's full
    identity (name + type + power/toughness + colors + ability text) since
    multiple distinct tokens can share just a name -- see
    `ImageCache.get_default_token_printing_id()`. Returns an empty list if
    the token printings index has no entry for this identity.
    """
    face_name = token_name.split(" // ")[0].strip() if " // " in token_name else token_name
    printings = _image_cache.get_token_printings(face_name, power, toughness, type_line, colors, text_hash)
    default_id = _image_cache.get_default_token_printing_id(face_name, power, toughness, type_line, colors, text_hash)
    return JSONResponse({
        "card_name": token_name,
        "default_scryfall_id": default_id,
        "printings": printings,
    })


@router.get("/images/{size}/{card_name}")
async def get_card_image(
    size: str,
    card_name: str,
    face: str = Query(default="front"),
    printing: Optional[str] = Query(
        default=None,
        description="Scryfall ID of a specific printing to show, instead of the default printing",
    ),
):
    """
    Serve card image from cache or redirect to Scryfall API.
    
    Args:
        size: Image size ('small', 'normal', or 'art_crop')
        card_name: Name of the card
        face: Which face to show ('front' or 'back') for DFC cards
        printing: Optional Scryfall ID of a specific printing to show
        
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

        # Resolve which face's name to use for lookups (DFCs).
        face_name = card_name
        if " // " in card_name:
            idx = 1 if face == "back" else 0
            face_name = card_name.split(" // ")[idx].strip()

        # Determine which printing to serve: an explicitly requested one,
        # or the printings index's default (highest-scoring) printing for
        # this face. Falls through to the legacy flat-file layout below if
        # the index has no rows for this card (e.g. not built yet, or a
        # token/emblem with no printings-index entry).
        effective_printing = printing or _image_cache.get_default_printing_id(face_name)

        if effective_printing:
            # New per-card/per-printing layout. Works independently of
            # IMAGE_CACHE_MODE -- if the printing isn't on disk yet
            # (e.g. `default` mode cached a different printing, or a
            # `full`-mode backfill is still in progress), download just
            # that one image on demand instead of falling back to a live
            # Scryfall name search that may resolve to a different
            # printing than the one this app considers "default".
            candidate_path = _image_cache.get_printing_image_path(face_name, effective_printing, size)
            if candidate_path.exists():
                image_path = candidate_path
            else:
                matches = [
                    row for row in _image_cache.get_printings(face_name)
                    if str(row.get("scryfall_id")) == effective_printing
                ]
                if matches:
                    image_url = matches[0].get(f"image_url_{size}") or matches[0].get("image_url_normal")
                    if image_url and _image_cache._download_image(image_url, candidate_path):
                        image_path = candidate_path

        if image_path is None:
            # Legacy flat-file layout (cards with no printings-index row).
            image_path = _image_cache.get_image_path(face_name, size)
        
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

            # Refresh the printings index so newly released sets/printings
            # are picked up (cheap relative to the image downloads below).
            logger.info("[IMAGE DOWNLOAD] Building printings index...")
            with status_file.open('w', encoding='utf-8') as f:
                json.dump({
                    "running": True,
                    "phase": "index",
                    "message": "Building printings index...",
                    "current": 0,
                    "total": 0,
                    "percentage": 0
                }, f)
            _image_cache.build_printings_index()

            # Download images into the per-card/per-printing layout. This
            # matches get_card_image()'s lookup order, so already-cached
            # printings are correctly skipped instead of being re-downloaded
            # into the legacy flat layout that lookup no longer prefers.
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
            
            stats = _image_cache.download_all_printings(progress_callback=image_progress)
            
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
