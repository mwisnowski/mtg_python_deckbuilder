"""
Card browser web UI routes (HTML views with HTMX).

Provides paginated card browsing with filters, search, and cursor-based pagination.
Complements the existing API routes in cards.py for tag-based card queries.
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

import pandas as pd
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from ..app import templates

# Import existing services
try:
    from code.services.all_cards_loader import AllCardsLoader
    from code.deck_builder.builder_utils import parse_theme_tags
except ImportError:
    from services.all_cards_loader import AllCardsLoader
    from deck_builder.builder_utils import parse_theme_tags

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cards", tags=["card-browser"])

# Cached loader instance and theme index
_loader: AllCardsLoader | None = None
_theme_index: dict[str, set[int]] | None = None  # theme_lower -> set of card indices
_theme_catalog: list[str] | None = None  # cached list of all theme names from catalog


def get_loader() -> AllCardsLoader:
    """Get cached AllCardsLoader instance."""
    global _loader
    if _loader is None:
        _loader = AllCardsLoader()
    return _loader


def get_theme_catalog() -> list[str]:
    """
    Get cached list of all theme names from theme_catalog.csv.
    
    Reads from the catalog CSV which includes all themes from all_cards.parquet
    (not just commander themes). Much faster than parsing themes from 26k+ cards.
    Used for autocomplete suggestions.
    
    Returns ~900+ themes (as of latest generation).
    """
    global _theme_catalog
    if _theme_catalog is None:
        import csv
        from pathlib import Path
        import os
        
        print("Loading theme catalog...", flush=True)
        
        # Try multiple possible paths (local dev vs Docker)
        possible_paths = [
            Path(__file__).parent.parent.parent / "config" / "themes" / "theme_catalog.csv",  # Local dev
            Path("/app/config/themes/theme_catalog.csv"),  # Docker
            Path(os.environ.get("CONFIG_DIR", "/app/config")) / "themes" / "theme_catalog.csv",  # Env var
        ]
        
        themes = []
        loaded = False
        
        for catalog_path in possible_paths:
            print(f"Checking path: {catalog_path} (exists: {catalog_path.exists()})", flush=True)
            if catalog_path.exists():
                try:
                    with open(catalog_path, 'r', encoding='utf-8') as f:
                        # Skip comment lines starting with #
                        lines = [line for line in f if not line.strip().startswith('#')]
                    
                    # Parse CSV from non-comment lines
                    from io import StringIO
                    csv_content = StringIO(''.join(lines))
                    reader = csv.DictReader(csv_content)
                    
                    for row in reader:
                        if 'theme' in row and row['theme']:
                            themes.append(row['theme'])
                    
                    _theme_catalog = themes
                    print(f"Loaded {len(themes)} themes from catalog: {catalog_path}", flush=True)
                    logger.info(f"Loaded {len(themes)} themes from catalog: {catalog_path}")
                    loaded = True
                    break
                except Exception as e:
                    print(f"❌ Failed to load from {catalog_path}: {e}", flush=True)  # Debug log
                    logger.warning(f"Failed to load theme catalog from {catalog_path}: {e}")
        
        if not loaded:
            print("⚠️ No catalog found, falling back to parsing cards", flush=True)  # Debug log
            logger.warning("Failed to load theme catalog from all paths, falling back to parsing cards")
            # Fallback: extract from theme index
            theme_index = get_theme_index()
            _theme_catalog = [theme.title() for theme in theme_index.keys()]
    
    return _theme_catalog


def get_theme_index() -> dict[str, set[int]]:
    """
    Get cached theme-to-card-index mapping for fast lookups.
    
    Returns dict mapping lowercase theme names to sets of card indices.
    Built once on first access and reused for all subsequent theme queries.
    """
    global _theme_index
    if _theme_index is None:
        logger.info("Building theme index for fast lookups...")
        _theme_index = {}
        loader = get_loader()
        df = loader.load()
        
        for idx, row in enumerate(df.itertuples()):
            themes = parse_theme_tags(row.themeTags if hasattr(row, 'themeTags') else '')
            for theme in themes:
                theme_lower = theme.lower()
                if theme_lower not in _theme_index:
                    _theme_index[theme_lower] = set()
                _theme_index[theme_lower].add(idx)
        
        logger.info(f"Theme index built with {len(_theme_index)} unique themes")
    
    return _theme_index


@router.get("/", response_class=HTMLResponse)
async def card_browser_index(
    request: Request,
    search: str = Query("", description="Card name search query"),
    themes: list[str] = Query([], description="Theme tag filters (AND logic)"),
    color: str = Query("", description="Color identity filter"),
    card_type: str = Query("", description="Card type filter"),
    rarity: str = Query("", description="Rarity filter"),
    sort: str = Query("name_asc", description="Sort order"),
    cmc_min: int = Query(None, description="Minimum CMC filter", ge=0, le=16),
    cmc_max: int = Query(None, description="Maximum CMC filter", ge=0, le=16),
    power_min: int = Query(None, description="Minimum power filter", ge=0, le=99),
    power_max: int = Query(None, description="Maximum power filter", ge=0, le=99),
    tough_min: int = Query(None, description="Minimum toughness filter", ge=0, le=99),
    tough_max: int = Query(None, description="Maximum toughness filter", ge=0, le=99),
):
    """
    Main card browser page.
    
    Displays initial grid of cards with filters and search bar.
    Uses HTMX for dynamic updates (pagination, filtering, search).
    """
    try:
        loader = get_loader()
        df = loader.load()
        
        # Apply filters
        filtered_df = df.copy()
        
        if search:
            # Prioritize exact matches first, then word-count matches, then fuzzy
            query_lower = search.lower().strip()
            query_words = set(query_lower.split())
            
            # 1. Check for exact match (case-insensitive)
            # For double-faced cards, check both full name and name before " //"
            exact_matches = []
            word_count_matches = []
            fuzzy_candidates = []
            fuzzy_indices = []
            
            for idx, card_name in enumerate(filtered_df['name']):
                card_lower = card_name.lower()
                # For double-faced cards, get the front face name
                front_name = card_lower.split(' // ')[0].strip() if ' // ' in card_lower else card_lower
                
                # Exact match (full name or front face)
                if card_lower == query_lower or front_name == query_lower:
                    exact_matches.append(idx)
                # Word count match (same number of words + high similarity)
                elif len(query_lower.split()) == len(front_name.split()) and (
                    query_lower in card_lower or any(word in card_lower for word in query_words)
                ):
                    word_count_matches.append((idx, card_name))
                # Fuzzy candidate
                elif query_lower in card_lower or any(word in card_lower for word in query_words):
                    fuzzy_candidates.append(card_name)
                    fuzzy_indices.append(idx)
            
            # Build final match list
            final_matches = []
            
            # If we have exact matches, ONLY return those (don't add fuzzy results)
            if exact_matches:
                final_matches = exact_matches
            else:
                # 2. Add word-count matches with fuzzy scoring
                if word_count_matches:
                    scored_wc = [(idx, _fuzzy_card_name_score(search, name), name) 
                                 for idx, name in word_count_matches]
                    scored_wc.sort(key=lambda x: -x[1])  # Sort by score desc
                    final_matches.extend([idx for idx, score, name in scored_wc if score >= 0.3])
                
                # 3. Add fuzzy matches
                if fuzzy_candidates:
                    scored_fuzzy = [(fuzzy_indices[i], _fuzzy_card_name_score(search, name), name)
                                   for i, name in enumerate(fuzzy_candidates)]
                    scored_fuzzy.sort(key=lambda x: -x[1])  # Sort by score desc
                    final_matches.extend([idx for idx, score, name in scored_fuzzy if score >= 0.3])
            
            # Apply matches
            if final_matches:
                # Remove duplicates while preserving order
                seen = set()
                unique_matches = []
                for idx in final_matches:
                    if idx not in seen:
                        seen.add(idx)
                        unique_matches.append(idx)
                filtered_df = filtered_df.iloc[unique_matches]
            else:
                filtered_df = filtered_df.iloc[0:0]
        
        # Multi-select theme filtering (AND logic: card must have ALL selected themes)
        if themes:
            theme_index = get_theme_index()
            
            # For each theme, get matching card indices
            all_theme_matches = []
            for theme in themes:
                theme_lower = theme.lower().strip()
                
                # Try exact match first (instant lookup)
                if theme_lower in theme_index:
                    # Direct index lookup - O(1) instead of O(n)
                    matching_indices = theme_index[theme_lower]
                    all_theme_matches.append(matching_indices)
                else:
                    # Fuzzy match: check all themes in index for similarity
                    matching_indices = set()
                    for indexed_theme, card_indices in theme_index.items():
                        if _fuzzy_theme_match_score(theme, indexed_theme) >= 0.5:
                            matching_indices.update(card_indices)
                    all_theme_matches.append(matching_indices)
            
            # Apply AND logic: card must be in ALL theme match sets
            if all_theme_matches:
                # Start with first theme's matches
                intersection = all_theme_matches[0]
                # Intersect with all other theme matches
                for theme_matches in all_theme_matches[1:]:
                    intersection = intersection & theme_matches
                
                # Intersect with current filtered_df indices
                current_indices = set(filtered_df.index)
                valid_indices = intersection & current_indices
                if valid_indices:
                    filtered_df = filtered_df.loc[list(valid_indices)]
                else:
                    filtered_df = filtered_df.iloc[0:0]

        if color:
            filtered_df = filtered_df[
                filtered_df['colorIdentity'] == color
            ]
        
        if card_type:
            filtered_df = filtered_df[
                filtered_df['type'].str.contains(card_type, case=False, na=False)
            ]
        
        if rarity and 'rarity' in filtered_df.columns:
            filtered_df = filtered_df[
                filtered_df['rarity'].str.lower() == rarity.lower()
            ]
        
        # CMC range filter
        if cmc_min is not None and 'manaValue' in filtered_df.columns:
            filtered_df = filtered_df[
                filtered_df['manaValue'] >= cmc_min
            ]
        
        if cmc_max is not None and 'manaValue' in filtered_df.columns:
            filtered_df = filtered_df[
                filtered_df['manaValue'] <= cmc_max
            ]
        
        # Power range filter (only applies to cards with power values)
        if power_min is not None and 'power' in filtered_df.columns:
            # Filter: either no power (NaN) OR power >= min
            filtered_df = filtered_df[
                filtered_df['power'].isna() | (filtered_df['power'] >= str(power_min))
            ]
        
        if power_max is not None and 'power' in filtered_df.columns:
            # Filter: either no power (NaN) OR power <= max
            filtered_df = filtered_df[
                filtered_df['power'].isna() | (filtered_df['power'] <= str(power_max))
            ]
        
        # Toughness range filter (only applies to cards with toughness values)
        if tough_min is not None and 'toughness' in filtered_df.columns:
            filtered_df = filtered_df[
                filtered_df['toughness'].isna() | (filtered_df['toughness'] >= str(tough_min))
            ]
        
        if tough_max is not None and 'toughness' in filtered_df.columns:
            filtered_df = filtered_df[
                filtered_df['toughness'].isna() | (filtered_df['toughness'] <= str(tough_max))
            ]
        
        # Apply sorting
        if sort == "name_desc":
            # Name Z-A
            filtered_df['_sort_key'] = filtered_df['name'].str.replace('"', '', regex=False).str.replace("'", '', regex=False)
            filtered_df['_sort_key'] = filtered_df['_sort_key'].apply(
                lambda x: x.replace('_', ' ') if x.startswith('_') else x
            )
            filtered_df = filtered_df.sort_values('_sort_key', key=lambda col: col.str.lower(), ascending=False)
            filtered_df = filtered_df.drop('_sort_key', axis=1)
        elif sort == "cmc_asc":
            # CMC Low-High, then name
            filtered_df = filtered_df.sort_values(['manaValue', 'name'], ascending=[True, True])
        elif sort == "cmc_desc":
            # CMC High-Low, then name
            filtered_df = filtered_df.sort_values(['manaValue', 'name'], ascending=[False, True])
        elif sort == "power_desc":
            # Power High-Low (creatures first, then non-creatures)
            # Convert power to numeric, NaN becomes -1 for sorting
            filtered_df['_power_sort'] = pd.to_numeric(filtered_df['power'], errors='coerce').fillna(-1)
            filtered_df = filtered_df.sort_values(['_power_sort', 'name'], ascending=[False, True])
            filtered_df = filtered_df.drop('_power_sort', axis=1)
        elif sort == "edhrec_asc":
            # EDHREC rank (low number = popular)
            if 'edhrecRank' in filtered_df.columns:
                # NaN goes to end (high value)
                filtered_df['_edhrec_sort'] = filtered_df['edhrecRank'].fillna(999999)
                filtered_df = filtered_df.sort_values(['_edhrec_sort', 'name'], ascending=[True, True])
                filtered_df = filtered_df.drop('_edhrec_sort', axis=1)
            else:
                # Fallback to name sort
                filtered_df = filtered_df.sort_values('name')
        else:
            # Default: Name A-Z (name_asc)
            filtered_df['_sort_key'] = filtered_df['name'].str.replace('"', '', regex=False).str.replace("'", '', regex=False)
            filtered_df['_sort_key'] = filtered_df['_sort_key'].apply(
                lambda x: x.replace('_', ' ') if x.startswith('_') else x
            )
            filtered_df = filtered_df.sort_values('_sort_key', key=lambda col: col.str.lower())
            filtered_df = filtered_df.drop('_sort_key', axis=1)
        
        total_cards = len(filtered_df)
        
        # Get first page (20 cards)
        per_page = 20
        cards_page = filtered_df.head(per_page)
        
        # Convert to list of dicts
        cards_list = cards_page.to_dict('records')
        
        # Parse theme tags and color identity for each card
        for card in cards_list:
            card['themeTags_parsed'] = parse_theme_tags(card.get('themeTags', ''))
            # Parse colorIdentity which can be:
            # - "Colorless" -> [] (but mark as colorless)
            # - "W" -> ['W']
            # - "B, R, U" -> ['B', 'R', 'U']
            # - "['W', 'U']" -> ['W', 'U']
            # - empty/None -> []
            raw_color = card.get('colorIdentity', '')
            is_colorless = False
            if raw_color and isinstance(raw_color, str):
                if raw_color.lower() == 'colorless':
                    card['colorIdentity'] = []
                    is_colorless = True
                elif raw_color.startswith('['):
                    # Parse list-like strings e.g. "['W', 'U']"
                    card['colorIdentity'] = parse_theme_tags(raw_color)
                elif ', ' in raw_color:
                    # Parse comma-separated e.g. "B, R, U"
                    card['colorIdentity'] = [c.strip() for c in raw_color.split(',')]
                else:
                    # Single color e.g. "W"
                    card['colorIdentity'] = [raw_color.strip()]
            elif not raw_color:
                card['colorIdentity'] = []
            card['is_colorless'] = is_colorless
            # TODO: Add owned card checking when integrated
            card['is_owned'] = False
        
        # Get unique values for filters
        # Build structured color identity list with proper names
        unique_color_ids = df['colorIdentity'].dropna().unique().tolist()
        
        # Define color identity groups with proper names
        color_groups = {
            'Colorless': ['Colorless'],
            'Mono-Color': ['W', 'U', 'B', 'R', 'G'],
            'Two-Color': [
                ('W, U', 'Azorius'),
                ('U, B', 'Dimir'),
                ('B, R', 'Rakdos'),
                ('R, G', 'Gruul'),
                ('G, W', 'Selesnya'),
                ('W, B', 'Orzhov'),
                ('U, R', 'Izzet'),
                ('B, G', 'Golgari'),
                ('R, W', 'Boros'),
                ('G, U', 'Simic'),
            ],
            'Three-Color': [
                ('B, G, U', 'Sultai'),
                ('G, U, W', 'Bant'),
                ('B, U, W', 'Esper'),
                ('B, R, U', 'Grixis'),
                ('B, G, R', 'Jund'),
                ('G, R, W', 'Naya'),
                ('B, G, W', 'Abzan'),
                ('R, U, W', 'Jeskai'),
                ('B, R, W', 'Mardu'),
                ('G, R, U', 'Temur'),
            ],
            'Four-Color': [
                ('B, G, R, U', 'Non-White'),
                ('B, G, R, W', 'Non-Blue'),
                ('B, G, U, W', 'Non-Red'),
                ('B, R, U, W', 'Non-Green'),
                ('G, R, U, W', 'Non-Black'),
            ],
            'Five-Color': ['B, G, R, U, W'],
        }
        
        # Flatten and filter to only include combinations present in data
        all_colors = []
        for group_name, entries in color_groups.items():
            group_colors = []
            for entry in entries:
                if isinstance(entry, tuple):
                    color_id, display_name = entry
                    if color_id in unique_color_ids:
                        group_colors.append((color_id, display_name))
                else:
                    color_id = entry
                    if color_id in unique_color_ids:
                        group_colors.append((color_id, color_id))
            if group_colors:
                all_colors.append((group_name, group_colors))
        
        all_types = sorted(
            set(
                df['type'].dropna().str.extract(r'([A-Za-z]+)', expand=False).dropna().unique().tolist()
            )
        )[:20]  # Limit to top 20 types
        
        all_rarities = []
        if 'rarity' in df.columns:
            all_rarities = sorted(df['rarity'].dropna().unique().tolist())
        
        # Calculate pagination info
        per_page = 20
        total_filtered = len(filtered_df)
        total_pages = (total_filtered + per_page - 1) // per_page  # Ceiling division
        current_page = 1  # Always page 1 on initial load (cursor-based makes exact page tricky)
        
        # Determine if there's a next page
        has_next = total_cards > per_page
        last_card_name = cards_list[-1]['name'] if cards_list else ""
        
        return templates.TemplateResponse(
            "browse/cards/index.html",
            {
                "request": request,
                "cards": cards_list,
                "total_cards": len(df),  # Original unfiltered count
                "filtered_count": total_filtered,  # After filters applied
                "has_next": has_next,
                "last_card": last_card_name,
                "search": search,
                "themes": themes,
                "color": color,
                "card_type": card_type,
                "rarity": rarity,
                "sort": sort,
                "cmc_min": cmc_min,
                "cmc_max": cmc_max,
                "power_min": power_min,
                "power_max": power_max,
                "tough_min": tough_min,
                "tough_max": tough_max,
                "all_colors": all_colors,
                "all_types": all_types,
                "all_rarities": all_rarities,
                "per_page": per_page,
                "current_page": current_page,
                "total_pages": total_pages,
            },
        )
    
    except FileNotFoundError as e:
        logger.error(f"Card data not found: {e}")
        return templates.TemplateResponse(
            "browse/cards/index.html",
            {
                "request": request,
                "cards": [],
                "total_cards": 0,
                "has_next": False,
                "last_card": "",
                "search": "",
                "color": "",
                "card_type": "",
                "rarity": "",
                "all_colors": [],
                "all_types": [],
                "all_rarities": [],
                "per_page": 20,
                "error": "Card data not available. Please run setup to generate all_cards.parquet.",
            },
        )
    except Exception as e:
        logger.error(f"Error loading card browser: {e}", exc_info=True)
        return templates.TemplateResponse(
            "browse/cards/index.html",
            {
                "request": request,
                "cards": [],
                "total_cards": 0,
                "has_next": False,
                "last_card": "",
                "search": "",
                "color": "",
                "card_type": "",
                "rarity": "",
                "all_colors": [],
                "all_types": [],
                "all_rarities": [],
                "per_page": 20,
                "error": f"Error loading cards: {str(e)}",
            },
        )


@router.get("/grid", response_class=HTMLResponse)
async def card_browser_grid(
    request: Request,
    cursor: str = Query("", description="Last card name from previous page"),
    search: str = Query("", description="Card name search query"),
    themes: list[str] = Query([], description="Theme tag filters (AND logic)"),
    color: str = Query("", description="Color identity filter"),
    card_type: str = Query("", description="Card type filter"),
    rarity: str = Query("", description="Rarity filter"),
    sort: str = Query("name_asc", description="Sort order"),
    cmc_min: int = Query(None, description="Minimum CMC filter", ge=0, le=16),
    cmc_max: int = Query(None, description="Maximum CMC filter", ge=0, le=16),
    power_min: int = Query(None, description="Minimum power filter", ge=0, le=99),
    power_max: int = Query(None, description="Maximum power filter", ge=0, le=99),
    tough_min: int = Query(None, description="Minimum toughness filter", ge=0, le=99),
    tough_max: int = Query(None, description="Maximum toughness filter", ge=0, le=99),
):
    """
    HTMX endpoint for paginated card grid.
    
    Returns only the grid partial HTML for seamless pagination.
    Uses cursor-based pagination (last_card_name) for performance.
    """
    try:
        loader = get_loader()
        df = loader.load()
        
        # Apply filters
        filtered_df = df.copy()
        
        if search:
            # Prioritize exact matches first, then word-count matches, then fuzzy
            query_lower = search.lower().strip()
            query_words = set(query_lower.split())
            
            # 1. Check for exact match (case-insensitive)
            # For double-faced cards, check both full name and name before " //"
            exact_matches = []
            word_count_matches = []
            fuzzy_candidates = []
            fuzzy_indices = []
            
            for idx, card_name in enumerate(filtered_df['name']):
                card_lower = card_name.lower()
                # For double-faced cards, get the front face name
                front_name = card_lower.split(' // ')[0].strip() if ' // ' in card_lower else card_lower
                
                # Exact match (full name or front face)
                if card_lower == query_lower or front_name == query_lower:
                    exact_matches.append(idx)
                # Word count match (same number of words + high similarity)
                elif len(query_lower.split()) == len(front_name.split()) and (
                    query_lower in card_lower or any(word in card_lower for word in query_words)
                ):
                    word_count_matches.append((idx, card_name))
                # Fuzzy candidate
                elif query_lower in card_lower or any(word in card_lower for word in query_words):
                    fuzzy_candidates.append(card_name)
                    fuzzy_indices.append(idx)
            
            # Build final match list
            final_matches = []
            
            # If we have exact matches, ONLY return those (don't add fuzzy results)
            if exact_matches:
                final_matches = exact_matches
            else:
                # 2. Add word-count matches with fuzzy scoring
                if word_count_matches:
                    scored_wc = [(idx, _fuzzy_card_name_score(search, name), name) 
                                 for idx, name in word_count_matches]
                    scored_wc.sort(key=lambda x: -x[1])  # Sort by score desc
                    final_matches.extend([idx for idx, score, name in scored_wc if score >= 0.3])
                
                # 3. Add fuzzy matches
                if fuzzy_candidates:
                    scored_fuzzy = [(fuzzy_indices[i], _fuzzy_card_name_score(search, name), name)
                                   for i, name in enumerate(fuzzy_candidates)]
                    scored_fuzzy.sort(key=lambda x: -x[1])  # Sort by score desc
                    final_matches.extend([idx for idx, score, name in scored_fuzzy if score >= 0.3])
            
            # Apply matches
            if final_matches:
                # Remove duplicates while preserving order
                seen = set()
                unique_matches = []
                for idx in final_matches:
                    if idx not in seen:
                        seen.add(idx)
                        unique_matches.append(idx)
                filtered_df = filtered_df.iloc[unique_matches]
            else:
                filtered_df = filtered_df.iloc[0:0]
        
        # Multi-select theme filtering (AND logic: card must have ALL selected themes)
        if themes:
            theme_index = get_theme_index()
            
            # For each theme, get matching card indices
            all_theme_matches = []
            for theme in themes:
                theme_lower = theme.lower().strip()
                
                # Try exact match first (instant lookup)
                if theme_lower in theme_index:
                    # Direct index lookup - O(1) instead of O(n)
                    matching_indices = theme_index[theme_lower]
                    all_theme_matches.append(matching_indices)
                else:
                    # Fuzzy match: check all themes in index for similarity
                    matching_indices = set()
                    for indexed_theme, card_indices in theme_index.items():
                        if _fuzzy_theme_match_score(theme, indexed_theme) >= 0.5:
                            matching_indices.update(card_indices)
                    all_theme_matches.append(matching_indices)
            
            # Apply AND logic: card must be in ALL theme match sets
            if all_theme_matches:
                # Start with first theme's matches
                intersection = all_theme_matches[0]
                # Intersect with all other theme matches
                for theme_matches in all_theme_matches[1:]:
                    intersection = intersection & theme_matches
                
                # Intersect with current filtered_df indices
                current_indices = set(filtered_df.index)
                valid_indices = intersection & current_indices
                if valid_indices:
                    filtered_df = filtered_df.loc[list(valid_indices)]
                else:
                    filtered_df = filtered_df.iloc[0:0]
        
        if color:
            filtered_df = filtered_df[
                filtered_df['colorIdentity'] == color
            ]
        
        if card_type:
            filtered_df = filtered_df[
                filtered_df['type'].str.contains(card_type, case=False, na=False)
            ]
        
        if rarity and 'rarity' in filtered_df.columns:
            filtered_df = filtered_df[
                filtered_df['rarity'].str.lower() == rarity.lower()
            ]
        
        # CMC range filter (grid endpoint)
        if cmc_min is not None and 'manaValue' in filtered_df.columns:
            filtered_df = filtered_df[
                filtered_df['manaValue'] >= cmc_min
            ]
        
        if cmc_max is not None and 'manaValue' in filtered_df.columns:
            filtered_df = filtered_df[
                filtered_df['manaValue'] <= cmc_max
            ]
        
        # Power range filter (grid endpoint)
        if power_min is not None and 'power' in filtered_df.columns:
            filtered_df = filtered_df[
                filtered_df['power'].isna() | (filtered_df['power'] >= str(power_min))
            ]
        
        if power_max is not None and 'power' in filtered_df.columns:
            filtered_df = filtered_df[
                filtered_df['power'].isna() | (filtered_df['power'] <= str(power_max))
            ]
        
        # Toughness range filter (grid endpoint)
        if tough_min is not None and 'toughness' in filtered_df.columns:
            filtered_df = filtered_df[
                filtered_df['toughness'].isna() | (filtered_df['toughness'] >= str(tough_min))
            ]
        
        if tough_max is not None and 'toughness' in filtered_df.columns:
            filtered_df = filtered_df[
                filtered_df['toughness'].isna() | (filtered_df['toughness'] <= str(tough_max))
            ]
        
        # Apply sorting (same logic as main endpoint)
        if sort == "name_desc":
            filtered_df['_sort_key'] = filtered_df['name'].str.replace('"', '', regex=False).str.replace("'", '', regex=False)
            filtered_df['_sort_key'] = filtered_df['_sort_key'].apply(
                lambda x: x.replace('_', ' ') if x.startswith('_') else x
            )
            filtered_df = filtered_df.sort_values('_sort_key', key=lambda col: col.str.lower(), ascending=False)
            filtered_df = filtered_df.drop('_sort_key', axis=1)
        elif sort == "cmc_asc":
            filtered_df = filtered_df.sort_values(['manaValue', 'name'], ascending=[True, True])
        elif sort == "cmc_desc":
            filtered_df = filtered_df.sort_values(['manaValue', 'name'], ascending=[False, True])
        elif sort == "power_desc":
            filtered_df['_power_sort'] = pd.to_numeric(filtered_df['power'], errors='coerce').fillna(-1)
            filtered_df = filtered_df.sort_values(['_power_sort', 'name'], ascending=[False, True])
            filtered_df = filtered_df.drop('_power_sort', axis=1)
        elif sort == "edhrec_asc":
            if 'edhrecRank' in filtered_df.columns:
                filtered_df['_edhrec_sort'] = filtered_df['edhrecRank'].fillna(999999)
                filtered_df = filtered_df.sort_values(['_edhrec_sort', 'name'], ascending=[True, True])
                filtered_df = filtered_df.drop('_edhrec_sort', axis=1)
            else:
                filtered_df = filtered_df.sort_values('name')
        else:
            # Default: Name A-Z
            filtered_df['_sort_key'] = filtered_df['name'].str.replace('"', '', regex=False).str.replace("'", '', regex=False)
            filtered_df['_sort_key'] = filtered_df['_sort_key'].apply(
                lambda x: x.replace('_', ' ') if x.startswith('_') else x
            )
            filtered_df = filtered_df.sort_values('_sort_key', key=lambda col: col.str.lower())
            filtered_df = filtered_df.drop('_sort_key', axis=1)
        
        # Cursor-based pagination
        if cursor:
            filtered_df = filtered_df[filtered_df['name'] > cursor]
        
        per_page = 20
        cards_page = filtered_df.head(per_page)
        cards_list = cards_page.to_dict('records')
        
        # Parse theme tags and color identity
        for card in cards_list:
            card['themeTags_parsed'] = parse_theme_tags(card.get('themeTags', ''))
            # Parse colorIdentity which can be:
            # - "Colorless" -> [] (but mark as colorless)
            # - "W" -> ['W']
            # - "B, R, U" -> ['B', 'R', 'U']
            # - "['W', 'U']" -> ['W', 'U']
            # - empty/None -> []
            raw_color = card.get('colorIdentity', '')
            is_colorless = False
            if raw_color and isinstance(raw_color, str):
                if raw_color.lower() == 'colorless':
                    card['colorIdentity'] = []
                    is_colorless = True
                elif raw_color.startswith('['):
                    # Parse list-like strings e.g. "['W', 'U']"
                    card['colorIdentity'] = parse_theme_tags(raw_color)
                elif ', ' in raw_color:
                    # Parse comma-separated e.g. "B, R, U"
                    card['colorIdentity'] = [c.strip() for c in raw_color.split(',')]
                else:
                    # Single color e.g. "W"
                    card['colorIdentity'] = [raw_color.strip()]
            elif not raw_color:
                card['colorIdentity'] = []
            card['is_colorless'] = is_colorless
            card['is_owned'] = False  # TODO: Add owned card checking
        
        has_next = len(filtered_df) > per_page
        last_card_name = cards_list[-1]['name'] if cards_list else ""
        
        return templates.TemplateResponse(
            "browse/cards/_card_grid.html",
            {
                "request": request,
                "cards": cards_list,
                "has_next": has_next,
                "last_card": last_card_name,
                "search": search,
                "themes": themes,
                "color": color,
                "card_type": card_type,
                "rarity": rarity,
                "sort": sort,
                "cmc_min": cmc_min,
                "cmc_max": cmc_max,
                "power_min": power_min,
                "power_max": power_max,
                "tough_min": tough_min,
                "tough_max": tough_max,
            },
        )
    
    except Exception as e:
        logger.error(f"Error loading card grid: {e}", exc_info=True)
        return HTMLResponse(
            f'<div class="error">Error loading cards: {str(e)}</div>',
            status_code=500,
        )


def _fuzzy_theme_match_score(query: str, theme: str) -> float:
    """
    Calculate fuzzy match score between query and theme name.
    Handles typos in the middle of words.
    
    Returns score from 0.0 to 1.0, higher is better match.
    """
    query_lower = query.lower()
    theme_lower = theme.lower()
    
    # Use sequence matcher for proper fuzzy matching (handles typos)
    base_score = SequenceMatcher(None, query_lower, theme_lower).ratio()
    
    # Bonus for substring match
    substring_bonus = 0.0
    if theme_lower.startswith(query_lower):
        substring_bonus = 0.3  # Strong bonus for prefix
    elif query_lower in theme_lower:
        substring_bonus = 0.2  # Moderate bonus for substring
    
    # Word overlap bonus (for multi-word themes)
    query_words = set(query_lower.split())
    theme_words = set(theme_lower.split())
    word_overlap = 0.0
    if query_words and theme_words:
        overlap_ratio = len(query_words & theme_words) / len(query_words)
        word_overlap = overlap_ratio * 0.2
    
    # Combine scores
    return min(1.0, base_score + substring_bonus + word_overlap)


@router.get("/search", response_class=HTMLResponse)
async def card_browser_search(
    request: Request,
    q: str = Query("", description="Search query"),
):
    """
    Live search autocomplete endpoint.
    
    Returns matching card names for autocomplete suggestions.
    """
    try:
        if not q or len(q) < 2:
            return HTMLResponse("<ul></ul>")
        
        loader = get_loader()
        df = loader.load()
        
        # Search by card name (case-insensitive)
        matches = df[df['name'].str.contains(q, case=False, na=False)]
        matches = matches.sort_values('name').head(10)
        
        card_names = matches['name'].tolist()
        
        # Return as simple HTML list
        html = "<ul>"
        for name in card_names:
            html += f'<li><a href="/cards?search={name}">{name}</a></li>'
        html += "</ul>"
        
        return HTMLResponse(html)
    
    except Exception as e:
        logger.error(f"Error in card search: {e}", exc_info=True)
        return HTMLResponse("<ul></ul>")


def _normalize_search_text(value: str | None) -> str:
    """Normalize search text for fuzzy matching (lowercase, alphanumeric only)."""
    if not value:
        return ""
    # Keep letters, numbers, spaces; convert to lowercase
    import re
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    return " ".join(tokens) if tokens else ""


def _fuzzy_card_name_score(query: str, card_name: str) -> float:
    """
    Calculate fuzzy match score between query and card name.
    
    Uses multiple scoring methods similar to commanders.py:
    - Base sequence matching
    - Partial ratio (substring matching)
    - Token matching
    - Word count matching bonus
    - Substring bonuses
    
    Returns score from 0.0 to 1.0, higher is better match.
    """
    normalized_query = _normalize_search_text(query)
    normalized_card = _normalize_search_text(card_name)
    
    if not normalized_query or not normalized_card:
        return 0.0
    
    # Base sequence matching
    base_score = SequenceMatcher(None, normalized_query, normalized_card).ratio()
    
    # Partial ratio - best matching substring
    query_len = len(normalized_query)
    if query_len <= len(normalized_card):
        best_partial = 0.0
        for i in range(len(normalized_card) - query_len + 1):
            substr = normalized_card[i:i + query_len]
            ratio = SequenceMatcher(None, normalized_query, substr).ratio()
            if ratio > best_partial:
                best_partial = ratio
    else:
        best_partial = base_score
    
    # Token matching
    query_tokens = normalized_query.split()
    card_tokens = normalized_card.split()
    
    if query_tokens and card_tokens:
        # Average token score
        token_scores = []
        for q_token in query_tokens:
            best_token_match = max(
                (SequenceMatcher(None, q_token, c_token).ratio() for c_token in card_tokens),
                default=0.0
            )
            token_scores.append(best_token_match)
        token_avg = sum(token_scores) / len(token_scores) if token_scores else 0.0
        
        # Word count bonus: prioritize same number of words
        # "peer parker" (2 words) should match "peter parker" (2 words) over "peter parker amazing" (3 words)
        word_count_bonus = 0.0
        if len(query_tokens) == len(card_tokens):
            word_count_bonus = 0.15  # Significant bonus for same word count
    else:
        token_avg = 0.0
        word_count_bonus = 0.0
    
    # Substring bonuses
    substring_bonus = 0.0
    if normalized_card.startswith(normalized_query):
        substring_bonus = 1.0
    elif normalized_query in normalized_card:
        substring_bonus = 0.9
    elif query_tokens and all(token in card_tokens for token in query_tokens):
        substring_bonus = 0.85
    
    # Combine scores with word count bonus
    base_result = max(base_score, best_partial, token_avg, substring_bonus)
    return min(1.0, base_result + word_count_bonus)  # Cap at 1.0



@router.get("/search-autocomplete", response_class=HTMLResponse)
async def card_search_autocomplete(
    request: Request,
    q: str = Query(..., min_length=2, description="Card name search query"),
    limit: int = Query(10, ge=1, le=50),
) -> HTMLResponse:
    """
    HTMX endpoint for card name autocomplete with fuzzy matching.
    
    Similar to commanders theme autocomplete, returns HTML suggestions
    with keyboard navigation support.
    """
    try:
        loader = get_loader()
        df = loader.load()
        
        # Quick filter: prioritize exact match, then word count match, then fuzzy
        query_lower = q.lower()
        query_words = set(query_lower.split())
        query_word_count = len(query_lower.split())
        
        # Fast categorization
        exact_matches = []
        word_count_candidates = []
        fuzzy_candidates = []
        
        for card_name in df['name'].unique():
            card_lower = card_name.lower()
            
            # Exact match
            if card_lower == query_lower:
                exact_matches.append(card_name)
            # Same word count with substring/word overlap
            elif len(card_lower.split()) == query_word_count and (
                query_lower in card_lower or any(word in card_lower for word in query_words)
            ):
                word_count_candidates.append(card_name)
            # Fuzzy candidate
            elif query_lower in card_lower or any(word in card_lower for word in query_words):
                fuzzy_candidates.append(card_name)
        
        # Build final scored list
        scored_cards: list[tuple[float, str, int]] = []  # (score, name, priority)
        
        # 1. Exact matches (priority 0 = highest)
        for card_name in exact_matches[:limit]:  # Take top N exact matches
            scored_cards.append((1.0, card_name, 0))
        
        # 2. Word count matches (priority 1)
        if len(scored_cards) < limit and word_count_candidates:
            # Limit word count candidates before fuzzy scoring
            if len(word_count_candidates) > 200:
                word_count_candidates.sort(key=lambda n: (not n.lower().startswith(query_lower), len(n), n.lower()))
                word_count_candidates = word_count_candidates[:200]
            
            for card_name in word_count_candidates:
                score = _fuzzy_card_name_score(q, card_name)
                if score >= 0.3:
                    scored_cards.append((score, card_name, 1))
        
        # 3. Fuzzy matches (priority 2)
        if len(scored_cards) < limit and fuzzy_candidates:
            # Limit fuzzy candidates before scoring
            if len(fuzzy_candidates) > 200:
                fuzzy_candidates.sort(key=lambda n: (not n.lower().startswith(query_lower), len(n), n.lower()))
                fuzzy_candidates = fuzzy_candidates[:200]
            
            for card_name in fuzzy_candidates:
                score = _fuzzy_card_name_score(q, card_name)
                if score >= 0.3:
                    scored_cards.append((score, card_name, 2))
        
        # Sort by priority first, then score desc, then name asc
        scored_cards.sort(key=lambda x: (x[2], -x[0], x[1].lower()))
        
        # Take top matches
        top_matches = scored_cards[:limit]
        
        # Generate HTML suggestions with ARIA attributes
        html_parts = []
        for score, card_name, priority in top_matches:
            # Escape HTML special characters
            safe_name = card_name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
            html_parts.append(
                f'<div class="autocomplete-item" data-value="{safe_name}" role="option">'
                f'{safe_name}</div>'
            )
        
        html = "\n".join(html_parts) if html_parts else '<div class="autocomplete-empty">No matching cards</div>'
        
        return HTMLResponse(content=html)
        
    except Exception as e:
        logger.error(f"Error in card autocomplete: {e}", exc_info=True)
        return HTMLResponse(content=f'<div class="autocomplete-error">Error: {str(e)}</div>')


@router.get("/theme-autocomplete", response_class=HTMLResponse)
async def card_theme_autocomplete(
    request: Request,
    q: str = Query(..., min_length=2, description="Theme search query"),
    limit: int = Query(10, ge=1, le=20),
) -> HTMLResponse:
    """
    HTMX endpoint for theme tag autocomplete with fuzzy matching.
    
    Uses theme catalog for instant lookups (no card parsing required).
    """
    try:
        # Use cached theme catalog (loaded from CSV, not parsed from cards)
        all_themes = get_theme_catalog()
        
        # Fuzzy match themes using helper function
        scored_themes: list[tuple[float, str]] = []
        
        # Only check against theme names from catalog (~575 themes)
        for theme in all_themes:
            score = _fuzzy_theme_match_score(q, theme)
            # Only include if score is reasonable (0.5+ = 50%+ match)
            if score >= 0.5:
                scored_themes.append((score, theme))
        
        # Sort by score (desc), then alphabetically
        scored_themes.sort(key=lambda x: (-x[0], x[1].lower()))
        top_matches = scored_themes[:limit]
        
        # Generate HTML suggestions
        html_parts = []
        for score, theme in top_matches:
            safe_theme = theme.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
            html_parts.append(
                f'<div class="autocomplete-item" data-value="{safe_theme}" role="option">'
                f'{safe_theme}</div>'
            )
        
        html = "\n".join(html_parts) if html_parts else '<div class="autocomplete-empty">No matching themes</div>'
        
        return HTMLResponse(content=html)
        
    except Exception as e:
        logger.error(f"Error in theme autocomplete: {e}", exc_info=True)
        return HTMLResponse(content=f'<div class="autocomplete-error">Error: {str(e)}</div>')

