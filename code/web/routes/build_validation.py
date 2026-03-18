"""Validation endpoints for card name validation and include/exclude lists.

This module handles validation of card names and include/exclude lists for the deck builder,
including fuzzy matching, color identity validation, and limit enforcement.
"""

import os
from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

from path_util import csv_dir as _csv_dir

router = APIRouter()

# Read configuration directly to avoid circular import with app.py
def _as_bool(val: str | bool | None, default: bool = False) -> bool:
    """Convert environment variable to boolean."""
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    s = str(val).strip().lower()
    return s in ("1", "true", "yes", "on")

ALLOW_MUST_HAVES = _as_bool(os.getenv("ALLOW_MUST_HAVES"), True)

# Cache for available card names used by validation endpoints
_AVAILABLE_CARDS_CACHE: set[str] | None = None
_AVAILABLE_CARDS_NORM_SET: set[str] | None = None
_AVAILABLE_CARDS_NORM_MAP: dict[str, str] | None = None


def _available_cards() -> set[str]:
    """Fast load of available card names using the csv module (no pandas).

    Reads only once and caches results in memory.
    """
    global _AVAILABLE_CARDS_CACHE
    if _AVAILABLE_CARDS_CACHE is not None:
        return _AVAILABLE_CARDS_CACHE
    try:
        import csv
        path = f"{_csv_dir()}/cards.csv"
        with open(path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
            name_col = None
            for col in ['name', 'Name', 'card_name', 'CardName']:
                if col in fields:
                    name_col = col
                    break
            if name_col is None and fields:
                # Heuristic: pick first field containing 'name'
                for col in fields:
                    if 'name' in col.lower():
                        name_col = col
                        break
            if name_col is None:
                raise ValueError(f"No name-like column found in {path}: {fields}")
            names: set[str] = set()
            for row in reader:
                try:
                    v = row.get(name_col)
                    if v:
                        names.add(str(v))
                except Exception:
                    continue
            _AVAILABLE_CARDS_CACHE = names
            return _AVAILABLE_CARDS_CACHE
    except Exception:
        _AVAILABLE_CARDS_CACHE = set()
        return _AVAILABLE_CARDS_CACHE


def _available_cards_normalized() -> tuple[set[str], dict[str, str]]:
    """Return cached normalized card names and mapping to originals."""
    global _AVAILABLE_CARDS_NORM_SET, _AVAILABLE_CARDS_NORM_MAP
    if _AVAILABLE_CARDS_NORM_SET is not None and _AVAILABLE_CARDS_NORM_MAP is not None:
        return _AVAILABLE_CARDS_NORM_SET, _AVAILABLE_CARDS_NORM_MAP
    # Build from available cards set
    names = _available_cards()
    try:
        from code.deck_builder.include_exclude_utils import normalize_punctuation
    except Exception:
        # Fallback: identity normalization
        def normalize_punctuation(x: str) -> str:
            return str(x).strip().casefold()
    norm_map: dict[str, str] = {}
    for name in names:
        try:
            n = normalize_punctuation(name)
            if n not in norm_map:
                norm_map[n] = name
        except Exception:
            continue
    _AVAILABLE_CARDS_NORM_MAP = norm_map
    _AVAILABLE_CARDS_NORM_SET = set(norm_map.keys())
    return _AVAILABLE_CARDS_NORM_SET, _AVAILABLE_CARDS_NORM_MAP


def warm_validation_name_cache() -> None:
    """Pre-populate the available-cards caches to avoid first-call latency."""
    try:
        _ = _available_cards()
        _ = _available_cards_normalized()
    except Exception:
        # Best-effort warmup; proceed silently on failure
        pass


@router.post("/validate/exclude_cards")
async def validate_exclude_cards(
    request: Request,
    exclude_cards: str = Form(default=""),
    commander: str = Form(default="")
):
    """Legacy exclude cards validation endpoint - redirect to new unified endpoint."""
    if not ALLOW_MUST_HAVES:
        return JSONResponse({"error": "Feature not enabled"}, status_code=404)
    
    # Call new unified endpoint
    result = await validate_include_exclude_cards(
        request=request,
        include_cards="",
        exclude_cards=exclude_cards,
        commander=commander,
        enforcement_mode="warn",
        allow_illegal=False,
        fuzzy_matching=True
    )
    
    # Transform to legacy format for backward compatibility
    if hasattr(result, 'body'):
        import json
        data = json.loads(result.body)
        if 'excludes' in data:
            excludes = data['excludes']
            return JSONResponse({
                "count": excludes.get("count", 0),
                "limit": excludes.get("limit", 15),
                "over_limit": excludes.get("over_limit", False),
                "cards": excludes.get("cards", []),
                "duplicates": excludes.get("duplicates", {}),
                "warnings": excludes.get("warnings", [])
            })
    
    return result


@router.post("/validate/include_exclude")
async def validate_include_exclude_cards(
    request: Request,
    include_cards: str = Form(default=""),
    exclude_cards: str = Form(default=""),
    commander: str = Form(default=""),
    enforcement_mode: str = Form(default="warn"),
    allow_illegal: bool = Form(default=False),
    fuzzy_matching: bool = Form(default=True)
):
    """Validate include/exclude card lists with comprehensive diagnostics."""
    if not ALLOW_MUST_HAVES:
        return JSONResponse({"error": "Feature not enabled"}, status_code=404)
    
    try:
        from code.deck_builder.include_exclude_utils import (
            parse_card_list_input, collapse_duplicates,
            fuzzy_match_card_name, MAX_INCLUDES, MAX_EXCLUDES
        )
        from code.deck_builder.builder import DeckBuilder
        
        # Parse inputs
        include_list = parse_card_list_input(include_cards) if include_cards.strip() else []
        exclude_list = parse_card_list_input(exclude_cards) if exclude_cards.strip() else []
        
        # Collapse duplicates
        include_unique, include_dupes = collapse_duplicates(include_list)
        exclude_unique, exclude_dupes = collapse_duplicates(exclude_list)
        
        # Initialize result structure
        result = {
            "includes": {
                "count": len(include_unique),
                "limit": MAX_INCLUDES,
                "over_limit": len(include_unique) > MAX_INCLUDES,
                "duplicates": include_dupes,
                "cards": include_unique[:10] if len(include_unique) <= 10 else include_unique[:7] + ["..."],
                "warnings": [],
                "legal": [],
                "illegal": [],
                "color_mismatched": [],
                "fuzzy_matches": {}
            },
            "excludes": {
                "count": len(exclude_unique),
                "limit": MAX_EXCLUDES,
                "over_limit": len(exclude_unique) > MAX_EXCLUDES,
                "duplicates": exclude_dupes,
                "cards": exclude_unique[:10] if len(exclude_unique) <= 10 else exclude_unique[:7] + ["..."],
                "warnings": [],
                "legal": [],
                "illegal": [],
                "fuzzy_matches": {}
            },
            "conflicts": [],  # Cards that appear in both lists
            "confirmation_needed": [],  # Cards needing fuzzy match confirmation
            "overall_warnings": []
        }
        
        # Check for conflicts (cards in both lists)
        conflicts = set(include_unique) & set(exclude_unique)
        if conflicts:
            result["conflicts"] = list(conflicts)
            result["overall_warnings"].append(f"Cards appear in both lists: {', '.join(list(conflicts)[:3])}{'...' if len(conflicts) > 3 else ''}")
        
        # Size warnings based on actual counts
        if result["includes"]["over_limit"]:
            result["includes"]["warnings"].append(f"Too many includes: {len(include_unique)}/{MAX_INCLUDES}")
        elif len(include_unique) > MAX_INCLUDES * 0.8:  # 80% capacity warning
            result["includes"]["warnings"].append(f"Approaching limit: {len(include_unique)}/{MAX_INCLUDES}")
            
        if result["excludes"]["over_limit"]:
            result["excludes"]["warnings"].append(f"Too many excludes: {len(exclude_unique)}/{MAX_EXCLUDES}")
        elif len(exclude_unique) > MAX_EXCLUDES * 0.8:  # 80% capacity warning
            result["excludes"]["warnings"].append(f"Approaching limit: {len(exclude_unique)}/{MAX_EXCLUDES}")
        
        # If we have a commander, do advanced validation (color identity, etc.)
        if commander and commander.strip():
            try:
                # Create a temporary builder
                builder = DeckBuilder()
                
                # Set up commander FIRST (before setup_dataframes)
                df = builder.load_commander_data()
                commander_rows = df[df["name"] == commander.strip()]
                
                if not commander_rows.empty:
                    # Apply commander selection (this sets commander_row properly)
                    builder._apply_commander_selection(commander_rows.iloc[0])
                
                # Now setup dataframes (this will use the commander info)
                builder.setup_dataframes()
                
                # Get available card names for fuzzy matching
                name_col = 'name' if 'name' in builder._full_cards_df.columns else 'Name'
                available_cards = set(builder._full_cards_df[name_col].tolist())
                
                # Validate includes with fuzzy matching
                for card_name in include_unique:
                    if fuzzy_matching:
                        match_result = fuzzy_match_card_name(card_name, available_cards)
                        if match_result.matched_name:
                            if match_result.auto_accepted:
                                result["includes"]["fuzzy_matches"][card_name] = match_result.matched_name
                                result["includes"]["legal"].append(match_result.matched_name)
                            else:
                                # Needs confirmation
                                result["confirmation_needed"].append({
                                    "input": card_name,
                                    "suggestions": match_result.suggestions,
                                    "confidence": match_result.confidence,
                                    "type": "include"
                                })
                        else:
                            result["includes"]["illegal"].append(card_name)
                    else:
                        # Exact match only
                        if card_name in available_cards:
                            result["includes"]["legal"].append(card_name)
                        else:
                            result["includes"]["illegal"].append(card_name)
                
                # Validate excludes with fuzzy matching
                for card_name in exclude_unique:
                    if fuzzy_matching:
                        match_result = fuzzy_match_card_name(card_name, available_cards)
                        if match_result.matched_name:
                            if match_result.auto_accepted:
                                result["excludes"]["fuzzy_matches"][card_name] = match_result.matched_name
                                result["excludes"]["legal"].append(match_result.matched_name)
                            else:
                                # Needs confirmation
                                result["confirmation_needed"].append({
                                    "input": card_name,
                                    "suggestions": match_result.suggestions,
                                    "confidence": match_result.confidence,
                                    "type": "exclude"
                                })
                        else:
                            result["excludes"]["illegal"].append(card_name)
                    else:
                        # Exact match only
                        if card_name in available_cards:
                            result["excludes"]["legal"].append(card_name)
                        else:
                            result["excludes"]["illegal"].append(card_name)
                
                # Color identity validation for includes (only if we have a valid commander with colors)
                commander_colors = getattr(builder, 'color_identity', [])
                if commander_colors:
                    color_validated_includes = []
                    for card_name in result["includes"]["legal"]:
                        if builder._validate_card_color_identity(card_name):
                            color_validated_includes.append(card_name)
                        else:
                            # Add color-mismatched cards to illegal instead of separate category
                            result["includes"]["illegal"].append(card_name)
                    
                    # Update legal includes to only those that pass color identity
                    result["includes"]["legal"] = color_validated_includes
                            
            except Exception as validation_error:
                # Advanced validation failed, but return basic validation
                result["overall_warnings"].append(f"Advanced validation unavailable: {str(validation_error)}")
        else:
            # No commander provided, do basic fuzzy matching only
            if fuzzy_matching and (include_unique or exclude_unique):
                try:
                    # Use cached available cards set (1st call populates cache)
                    available_cards = _available_cards()
                    
                    # Fast path: normalized exact matches via cached sets
                    norm_set, norm_map = _available_cards_normalized()
                    # Validate includes with fuzzy matching
                    for card_name in include_unique:
                        from code.deck_builder.include_exclude_utils import normalize_punctuation
                        n = normalize_punctuation(card_name)
                        if n in norm_set:
                            result["includes"]["fuzzy_matches"][card_name] = norm_map[n]
                            result["includes"]["legal"].append(norm_map[n])
                            continue
                        match_result = fuzzy_match_card_name(card_name, available_cards)
                        
                        if match_result.matched_name and match_result.auto_accepted:
                            # Exact or high-confidence match
                            result["includes"]["fuzzy_matches"][card_name] = match_result.matched_name
                            result["includes"]["legal"].append(match_result.matched_name)
                        elif not match_result.auto_accepted and match_result.suggestions:
                            # Needs confirmation - has suggestions but low confidence
                            result["confirmation_needed"].append({
                                "input": card_name,
                                "suggestions": match_result.suggestions,
                                "confidence": match_result.confidence,
                                "type": "include"
                            })
                        else:
                            # No match found at all, add to illegal
                            result["includes"]["illegal"].append(card_name)
                    # Validate excludes with fuzzy matching
                    for card_name in exclude_unique:
                        from code.deck_builder.include_exclude_utils import normalize_punctuation
                        n = normalize_punctuation(card_name)
                        if n in norm_set:
                            result["excludes"]["fuzzy_matches"][card_name] = norm_map[n]
                            result["excludes"]["legal"].append(norm_map[n])
                            continue
                        match_result = fuzzy_match_card_name(card_name, available_cards)
                        if match_result.matched_name:
                            if match_result.auto_accepted:
                                result["excludes"]["fuzzy_matches"][card_name] = match_result.matched_name
                                result["excludes"]["legal"].append(match_result.matched_name)
                            else:
                                # Needs confirmation
                                result["confirmation_needed"].append({
                                    "input": card_name,
                                    "suggestions": match_result.suggestions,
                                    "confidence": match_result.confidence,
                                    "type": "exclude"
                                })
                        else:
                            # No match found, add to illegal
                            result["excludes"]["illegal"].append(card_name)
                            
                except Exception as fuzzy_error:
                    result["overall_warnings"].append(f"Fuzzy matching unavailable: {str(fuzzy_error)}")
        
        return JSONResponse(result)
        
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
