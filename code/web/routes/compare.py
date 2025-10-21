"""
Comparison Routes - Side-by-side deck comparison for batch builds.
"""

from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from typing import Any, Dict, List
from ..app import templates
from ..services.build_cache import BuildCache
from ..services.tasks import get_session, new_sid
from ..services.synergy_builder import analyze_and_build_synergy_deck
from code.logging_util import get_logger
import time

logger = get_logger(__name__)
router = APIRouter()


def _is_guaranteed_card(card_name: str) -> bool:
    """
    Check if a card is guaranteed/staple (should be filtered from interesting variance).
    
    Filters:
    - Basic lands (Plains, Island, Swamp, Mountain, Forest, Wastes, Snow-Covered variants)
    - Staple lands (Command Tower, Reliquary Tower, etc.)
    - Kindred lands
    - Generic fetch lands
    
    Args:
        card_name: Card name to check
        
    Returns:
        True if card should be filtered from "Most Common Cards"
    """
    try:
        from code.deck_builder import builder_constants as bc
        
        # Basic lands
        basic_lands = set(getattr(bc, 'BASIC_LANDS', []))
        if card_name in basic_lands:
            return True
        
        # Snow-covered basics
        if card_name.startswith('Snow-Covered '):
            base_name = card_name.replace('Snow-Covered ', '')
            if base_name in basic_lands:
                return True
        
        # Staple lands (keys from STAPLE_LAND_CONDITIONS)
        staple_conditions = getattr(bc, 'STAPLE_LAND_CONDITIONS', {})
        if card_name in staple_conditions:
            return True
        
        # Kindred lands
        kindred_lands = set(getattr(bc, 'KINDRED_LAND_NAMES', []))
        if card_name in kindred_lands:
            return True
        
        # Generic fetch lands
        generic_fetches = set(getattr(bc, 'GENERIC_FETCH_LANDS', []))
        if card_name in generic_fetches:
            return True
        
        # Color-specific fetch lands
        color_fetches = getattr(bc, 'COLOR_TO_FETCH_LANDS', {})
        for fetch_list in color_fetches.values():
            if card_name in fetch_list:
                return True
        
        return False
    except Exception as e:
        logger.debug(f"Error checking guaranteed card status for {card_name}: {e}")
        return False


@router.get("/compare/{batch_id}", response_class=HTMLResponse)
async def compare_batch(request: Request, batch_id: str) -> HTMLResponse:
    """Main comparison view for batch builds."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    
    # Get batch data
    batch_status = BuildCache.get_batch_status(sess, batch_id)
    if not batch_status:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Batch {batch_id} not found. It may have expired.",
            "back_link": "/build"
        })
    
    builds = BuildCache.get_batch_builds(sess, batch_id)
    config = BuildCache.get_batch_config(sess, batch_id)
    
    if not builds:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "No completed builds found in this batch.",
            "back_link": "/build"
        })
    
    # Calculate card overlap statistics
    overlap_stats = _calculate_overlap(builds)
    
    # Prepare deck summaries
    summaries = []
    for build in builds:
        summary = _build_summary(build["result"], build["index"])
        summaries.append(summary)
    
    ctx = {
        "request": request,
        "batch_id": batch_id,
        "batch_status": batch_status,
        "config": config,
        "builds": summaries,
        "overlap_stats": overlap_stats,
        "build_count": len(summaries),
        "synergy_exported": BuildCache.is_synergy_exported(sess, batch_id)
    }
    
    resp = templates.TemplateResponse("compare/index.html", ctx)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


def _calculate_overlap(builds: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate card overlap statistics across builds.
    
    Args:
        builds: List of build result dicts
        
    Returns:
        Dict with overlap statistics
    """
    from collections import Counter
    
    # Collect all cards with their appearance counts
    card_counts: Counter = Counter()
    total_builds = len(builds)
    
    # Collect include cards (must-includes) from first build as they should be in all
    include_cards_set = set()
    if builds:
        first_result = builds[0].get("result", {})
        first_summary = first_result.get("summary", {})
        if isinstance(first_summary, dict):
            include_exclude = first_summary.get("include_exclude_summary", {})
            if isinstance(include_exclude, dict):
                includes = include_exclude.get("include_cards", [])
                if isinstance(includes, list):
                    include_cards_set = set(includes)
    
    for build in builds:
        result = build.get("result", {})
        summary = result.get("summary", {})
        if not isinstance(summary, dict):
            continue
            
        type_breakdown = summary.get("type_breakdown", {})
        if not isinstance(type_breakdown, dict):
            continue
        
        # Track unique cards per build (from type_breakdown cards dict)
        unique_cards = set()
        type_cards = type_breakdown.get("cards", {})
        if isinstance(type_cards, dict):
            for card_list in type_cards.values():
                if isinstance(card_list, list):
                    for card in card_list:
                        if isinstance(card, dict):
                            card_name = card.get("name")
                            if card_name:
                                unique_cards.add(card_name)
        
        # Increment counter for each unique card
        for card_name in unique_cards:
            card_counts[card_name] += 1
    
    # Calculate statistics
    total_unique_cards = len(card_counts)
    cards_in_all = sum(1 for count in card_counts.values() if count == total_builds)
    cards_in_most = sum(1 for count in card_counts.values() if count >= total_builds * 0.8)
    cards_in_some = sum(1 for count in card_counts.values() if total_builds * 0.2 < count < total_builds * 0.8)
    cards_in_few = sum(1 for count in card_counts.values() if count <= total_builds * 0.2)
    
    # Most common cards - filter out guaranteed/staple cards to highlight interesting variance
    # Filter before taking top 20 to show random selections rather than guaranteed hits
    filtered_counts = {
        name: count for name, count in card_counts.items()
        if not _is_guaranteed_card(name) and name not in include_cards_set
    }
    most_common = Counter(filtered_counts).most_common(20)
    
    return {
        "total_unique_cards": total_unique_cards,
        "cards_in_all": cards_in_all,
        "cards_in_most": cards_in_most,
        "cards_in_some": cards_in_some,
        "cards_in_few": cards_in_few,
        "most_common": most_common,
        "total_builds": total_builds
    }


def _build_summary(result: Dict[str, Any], index: int) -> Dict[str, Any]:
    """
    Create a summary of a single build for comparison display.
    
    Args:
        result: Build result from orchestrator
        index: Build index
        
    Returns:
        Summary dict
    """
    # Get summary from result
    summary = result.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    
    # Get type breakdown which contains card counts
    type_breakdown = summary.get("type_breakdown", {})
    if not isinstance(type_breakdown, dict):
        type_breakdown = {}
    
    # Get counts directly from type breakdown
    counts = type_breakdown.get("counts", {})
    
    # Use standardized keys from type breakdown
    creatures = counts.get("Creature", 0)
    lands = counts.get("Land", 0)
    artifacts = counts.get("Artifact", 0)
    enchantments = counts.get("Enchantment", 0)
    instants = counts.get("Instant", 0)
    sorceries = counts.get("Sorcery", 0)
    planeswalkers = counts.get("Planeswalker", 0)
    
    # Get total from type breakdown
    total_cards = type_breakdown.get("total", 0)
    
    # Get all cards from type breakdown cards dict
    all_cards = []
    type_cards = type_breakdown.get("cards", {})
    if isinstance(type_cards, dict):
        for card_list in type_cards.values():
            if isinstance(card_list, list):
                all_cards.extend(card_list)
    
    return {
        "index": index,
        "build_number": index + 1,
        "total_cards": total_cards,
        "creatures": creatures,
        "lands": lands,
        "artifacts": artifacts,
        "enchantments": enchantments,
        "instants": instants,
        "sorceries": sorceries,
        "planeswalkers": planeswalkers,
        "cards": all_cards,
        "result": result
    }


@router.post("/compare/{batch_id}/export")
async def export_batch(request: Request, batch_id: str):
    """
    Export all decks in a batch as a ZIP archive.
    
    Args:
        request: FastAPI request object
        batch_id: Batch identifier
        
    Returns:
        ZIP file with all deck CSV/TXT files + summary JSON
    """
    import zipfile
    import io
    import json
    from pathlib import Path
    from fastapi.responses import StreamingResponse
    from datetime import datetime
    
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    
    # Get batch data
    batch_status = BuildCache.get_batch_status(sess, batch_id)
    if not batch_status:
        return {"error": f"Batch {batch_id} not found"}
    
    builds = BuildCache.get_batch_builds(sess, batch_id)
    config = BuildCache.get_batch_config(sess, batch_id)
    
    if not builds:
        return {"error": "No completed builds found in this batch"}
    
    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Collect all deck files
        commander_name = config.get("commander", "Unknown").replace("/", "-")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for i, build in enumerate(builds):
            result = build.get("result", {})
            csv_path = result.get("csv_path")
            txt_path = result.get("txt_path")
            
            # Add CSV file
            if csv_path and Path(csv_path).exists():
                filename = f"Build_{i+1}_{commander_name}.csv"
                with open(csv_path, 'rb') as f:
                    zip_file.writestr(filename, f.read())
            
            # Add TXT file
            if txt_path and Path(txt_path).exists():
                filename = f"Build_{i+1}_{commander_name}.txt"
                with open(txt_path, 'rb') as f:
                    zip_file.writestr(filename, f.read())
        
        # Add batch summary JSON
        summary_data = {
            "batch_id": batch_id,
            "commander": config.get("commander"),
            "themes": config.get("tags", []),
            "bracket": config.get("bracket"),
            "build_count": len(builds),
            "exported_at": timestamp,
            "builds": [
                {
                    "build_number": i + 1,
                    "csv_file": f"Build_{i+1}_{commander_name}.csv",
                    "txt_file": f"Build_{i+1}_{commander_name}.txt"
                }
                for i in range(len(builds))
            ]
        }
        zip_file.writestr("batch_summary.json", json.dumps(summary_data, indent=2))
    
    # Prepare response
    zip_buffer.seek(0)
    zip_filename = f"{commander_name}_Batch_{timestamp}.zip"
    
    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"'
        }
    )


@router.post("/compare/{batch_id}/rebuild")
async def rebuild_batch(request: Request, batch_id: str):
    """
    Rebuild the same configuration with the same build count.
    Creates a new batch with identical settings and redirects to batch progress.
    
    Args:
        request: FastAPI request object
        batch_id: Original batch identifier
        
    Returns:
        Redirect to new batch progress page
    """
    from fastapi.responses import RedirectResponse
    from ..services.multi_build_orchestrator import MultiBuildOrchestrator
    
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    
    # Get original config and build count
    config = BuildCache.get_batch_config(sess, batch_id)
    batch_status = BuildCache.get_batch_status(sess, batch_id)
    
    if not config or not batch_status:
        return RedirectResponse(url="/build", status_code=302)
    
    # Get build count from original batch
    build_count = batch_status.get("total_builds", 1)
    
    # Create new batch with same config
    orchestrator = MultiBuildOrchestrator()
    new_batch_id = orchestrator.queue_builds(config, build_count, sid)
    
    # Start builds in background
    import asyncio
    asyncio.create_task(orchestrator.run_batch_parallel(new_batch_id))
    
    # Redirect to new batch progress
    response = RedirectResponse(url=f"/build/batch/{new_batch_id}/progress", status_code=302)
    response.set_cookie("sid", sid, httponly=True, samesite="lax")
    return response


@router.post("/compare/{batch_id}/build-synergy")
async def build_synergy_deck(request: Request, batch_id: str) -> HTMLResponse:
    """
    Build a synergy deck from batch builds.
    
    Analyzes all builds in the batch and creates an optimized "best-of" deck
    by scoring cards based on frequency, EDHREC rank, and theme alignment.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    
    # Get batch data
    builds = BuildCache.get_batch_builds(sess, batch_id)
    config = BuildCache.get_batch_config(sess, batch_id)
    batch_status = BuildCache.get_batch_status(sess, batch_id)
    
    if not builds or not config or not batch_status:
        return HTMLResponse(
            content=f'<div class="error-message">Batch {batch_id} not found or has no builds</div>',
            status_code=404
        )
    
    start_time = time.time()
    
    try:
        # Analyze and build synergy deck
        synergy_deck = analyze_and_build_synergy_deck(builds, config)
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        logger.info(
            f"[Synergy] Built deck for batch {batch_id}: "
            f"{synergy_deck['total_cards']} cards, "
            f"avg_score={synergy_deck['avg_score']}, "
            f"elapsed={elapsed_ms}ms"
        )
        
        # Prepare cards_by_category for template
        cards_by_category = {
            category: [
                {
                    "name": card.name,
                    "frequency": card.frequency,
                    "synergy_score": card.synergy_score,
                    "appearance_count": card.appearance_count,
                    "role": card.role,
                    "tags": card.tags,
                    "type_line": card.type_line,
                    "count": card.count
                }
                for card in cards
            ]
            for category, cards in synergy_deck["by_category"].items()
        }
        
        # Render preview template
        return templates.TemplateResponse("compare/_synergy_preview.html", {
            "request": request,
            "batch_id": batch_id,
            "synergy_deck": {
                "total_cards": synergy_deck["total_cards"],
                "avg_frequency": synergy_deck["avg_frequency"],
                "avg_score": synergy_deck["avg_score"],
                "high_frequency_count": synergy_deck["high_frequency_count"],
                "cards_by_category": cards_by_category
            },
            "total_builds": len(builds),
            "build_time_ms": elapsed_ms
        })
    
    except Exception as e:
        logger.error(f"[Synergy] Error building synergy deck: {e}", exc_info=True)
        return HTMLResponse(
            content=f'<div class="error-message">Failed to build synergy deck: {str(e)}</div>',
            status_code=500
        )


@router.post("/compare/{batch_id}/export-synergy")
async def export_synergy_deck(request: Request, batch_id: str):
    """
    Export the synergy deck as CSV and TXT files in a ZIP archive.
    
    Args:
        request: FastAPI request object
        batch_id: Batch identifier
        
    Returns:
        ZIP file with synergy deck CSV/TXT files
    """
    import io
    import csv
    import zipfile
    import json
    from fastapi.responses import StreamingResponse
    from datetime import datetime
    
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    
    # Get batch data
    batch_status = BuildCache.get_batch_status(sess, batch_id)
    if not batch_status:
        return {"error": f"Batch {batch_id} not found"}
    
    builds = BuildCache.get_batch_builds(sess, batch_id)
    config = BuildCache.get_batch_config(sess, batch_id)
    
    if not builds:
        return {"error": "No completed builds found in this batch"}
    
    # Build synergy deck (reuse the existing logic)
    from code.web.services.synergy_builder import analyze_and_build_synergy_deck
    
    try:
        synergy_deck = analyze_and_build_synergy_deck(
            builds=builds,
            config=config
        )
    except Exception as e:
        logger.error(f"[Export Synergy] Error building synergy deck: {e}", exc_info=True)
        return {"error": f"Failed to build synergy deck: {str(e)}"}
    
    # Prepare file names
    commander_name = config.get("commander", "Unknown").replace("/", "-").replace(" ", "")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_filename = f"{commander_name}_Synergy_{timestamp}"
    
    # Prepare deck_files directory
    from pathlib import Path
    deck_files_dir = Path("deck_files")
    deck_files_dir.mkdir(parents=True, exist_ok=True)
    
    # Create CSV content
    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer)
    
    # CSV Header
    csv_writer.writerow([
        "Name", "Count", "Category", "Role", "Frequency", "Synergy Score",
        "Appearance Count", "Tags", "Type"
    ])
    
    # CSV Rows - sort by category
    category_order = ["Land", "Creature", "Artifact", "Enchantment", "Instant", "Sorcery", "Planeswalker", "Battle"]
    by_category = synergy_deck.get("by_category", {})
    
    for category in category_order:
        cards = by_category.get(category, [])
        for card in cards:
            csv_writer.writerow([
                card.name,
                card.count,
                card.category,
                card.role,
                f"{card.frequency:.2%}",
                f"{card.synergy_score:.2f}",
                card.appearance_count,
                "|".join(card.tags) if card.tags else "",
                card.type_line
            ])
    
    csv_content = csv_buffer.getvalue()
    
    # Create TXT content (Moxfield/EDHREC format)
    txt_buffer = io.StringIO()
    
    # TXT Header
    txt_buffer.write(f"# Synergy Deck - {commander_name}\n")
    txt_buffer.write(f"# Commander: {config.get('commander', 'Unknown')}\n")
    txt_buffer.write(f"# Colors: {', '.join(config.get('colors', []))}\n")
    txt_buffer.write(f"# Themes: {', '.join(config.get('tags', []))}\n")
    txt_buffer.write(f"# Generated from {len(builds)} builds\n")
    txt_buffer.write(f"# Total Cards: {synergy_deck['total_cards']}\n")
    txt_buffer.write(f"# Avg Frequency: {synergy_deck['avg_frequency']:.1%}\n")
    txt_buffer.write(f"# Avg Synergy Score: {synergy_deck['avg_score']:.2f}\n")
    txt_buffer.write("\n")
    
    # TXT Card list
    for category in category_order:
        cards = by_category.get(category, [])
        if not cards:
            continue
        
        for card in cards:
            line = f"{card.count} {card.name}"
            if card.count > 1:
                # Show count prominently for multi-copy cards
                txt_buffer.write(f"{line}\n")
            else:
                txt_buffer.write(f"1 {card.name}\n")
    
    txt_content = txt_buffer.getvalue()
    
    # Save CSV and TXT to deck_files directory
    csv_path = deck_files_dir / f"{base_filename}.csv"
    txt_path = deck_files_dir / f"{base_filename}.txt"
    summary_path = deck_files_dir / f"{base_filename}.summary.json"
    compliance_path = deck_files_dir / f"{base_filename}_compliance.json"
    
    try:
        csv_path.write_text(csv_content, encoding='utf-8')
        txt_path.write_text(txt_content, encoding='utf-8')
        
        # Create summary JSON (similar to individual builds)
        summary_data = {
            "commander": config.get("commander", "Unknown"),
            "tags": config.get("tags", []),
            "colors": config.get("colors", []),
            "bracket_level": config.get("bracket"),
            "csv": str(csv_path),
            "txt": str(txt_path),
            "synergy_stats": {
                "total_cards": synergy_deck["total_cards"],
                "unique_cards": synergy_deck.get("unique_cards", len(synergy_deck["cards"])),
                "avg_frequency": synergy_deck["avg_frequency"],
                "avg_score": synergy_deck["avg_score"],
                "high_frequency_count": synergy_deck["high_frequency_count"],
                "source_builds": len(builds)
            },
            "exported_at": timestamp
        }
        summary_path.write_text(json.dumps(summary_data, indent=2), encoding='utf-8')
        
        # Create compliance JSON (basic compliance for synergy deck)
        compliance_data = {
            "overall": "N/A",
            "message": "Synergy deck - compliance checking not applicable",
            "deck_size": synergy_deck["total_cards"],
            "commander": config.get("commander", "Unknown"),
            "source": "synergy_builder",
            "build_count": len(builds)
        }
        compliance_path.write_text(json.dumps(compliance_data, indent=2), encoding='utf-8')
        
        logger.info(f"[Export Synergy] Saved synergy deck to {csv_path} and {txt_path}")
    except Exception as e:
        logger.error(f"[Export Synergy] Failed to save files to disk: {e}", exc_info=True)
    
    # Delete batch build files to avoid clutter
    deleted_files = []
    for build in builds:
        result = build.get("result", {})
        csv_file = result.get("csv_path")
        txt_file = result.get("txt_path")
        summary_file = result.get("summary_path")
        
        # Delete CSV file
        if csv_file:
            csv_p = Path(csv_file)
            if csv_p.exists():
                try:
                    csv_p.unlink()
                    deleted_files.append(csv_p.name)
                except Exception as e:
                    logger.warning(f"[Export Synergy] Failed to delete {csv_file}: {e}")
        
        # Delete TXT file
        if txt_file:
            txt_p = Path(txt_file)
            if txt_p.exists():
                try:
                    txt_p.unlink()
                    deleted_files.append(txt_p.name)
                except Exception as e:
                    logger.warning(f"[Export Synergy] Failed to delete {txt_file}: {e}")
        
        # Delete summary JSON file
        if summary_file:
            summary_p = Path(summary_file)
            if summary_p.exists():
                try:
                    summary_p.unlink()
                    deleted_files.append(summary_p.name)
                except Exception as e:
                    logger.warning(f"[Export Synergy] Failed to delete {summary_file}: {e}")
    
    if deleted_files:
        logger.info(f"[Export Synergy] Cleaned up {len(deleted_files)} batch build files")
    
    # Mark batch as having synergy exported (to disable batch export button)
    BuildCache.mark_synergy_exported(sess, batch_id)
    
    # Create ZIP in memory for download
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add CSV to ZIP
        zip_file.writestr(f"{base_filename}.csv", csv_content)
        
        # Add TXT to ZIP
        zip_file.writestr(f"{base_filename}.txt", txt_content)
        
        # Add summary JSON to ZIP
        summary_json = json.dumps(summary_data, indent=2)
        zip_file.writestr(f"{base_filename}.summary.json", summary_json)
        
        # Add compliance JSON to ZIP
        compliance_json = json.dumps(compliance_data, indent=2)
        zip_file.writestr(f"{base_filename}_compliance.json", compliance_json)
        
        # Add metadata JSON (export-specific info)
        metadata = {
            "batch_id": batch_id,
            "commander": config.get("commander"),
            "themes": config.get("tags", []),
            "colors": config.get("colors", []),
            "bracket": config.get("bracket"),
            "build_count": len(builds),
            "exported_at": timestamp,
            "synergy_stats": {
                "total_cards": synergy_deck["total_cards"],
                "avg_frequency": synergy_deck["avg_frequency"],
                "avg_score": synergy_deck["avg_score"],
                "high_frequency_count": synergy_deck["high_frequency_count"]
            },
            "cleaned_up_files": len(deleted_files)
        }
        zip_file.writestr("synergy_metadata.json", json.dumps(metadata, indent=2))
    
    # Prepare response
    zip_buffer.seek(0)
    zip_filename = f"{base_filename}.zip"
    
    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"'
        }
    )
