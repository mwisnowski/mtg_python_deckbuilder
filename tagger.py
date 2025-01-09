from __future__ import annotations

import logging
import os
import pprint # type: ignore
import re
from typing import Dict, List, Optional, Set, Union

import pandas as pd # type: ignore

import settings
import utility
import setup_utility

from settings import csv_directory, multiple_copy_cards, num_to_search, triggers
from setup import regenerate_csv_by_color, regenerate_csvs_all

# Constants for common tag groupings
TAG_GROUPS = {
    "Cantrips": ["Cantrips", "Card Draw", "Spellslinger", "Spells Matter"],
    "Tokens": ["Token Creation", "Tokens Matter"],
    "Counters": ["Counters Matter"],
    "Combat": ["Combat Matters", "Combat Tricks"],
    "Artifacts": ["Artifacts Matter", "Artifact Tokens"],
    "Enchantments": ["Enchantments Matter", "Enchantment Tokens"],
    "Lands": ["Lands Matter"],
    "Spells": ["Spellslinger", "Spells Matter"]
}

# Common regex patterns
PATTERN_GROUPS = {
    "draw": r"draw[s]? a card|draw[s]? one card",
    "combat": r"attack[s]?|block[s]?|combat damage",
    "tokens": r"create[s]? .* token|put[s]? .* token",
    "counters": r"\+1/\+1 counter|\-1/\-1 counter|loyalty counter",
    "sacrifice": r"sacrifice[s]? .*|sacrificed",
    "exile": r"exile[s]? .*|exiled",
    "cost_reduction": r"cost[s]? \{[\d\w]\} less|affinity for|cost[s]? less to cast|chosen type cost|copy cost|from exile cost|from exile this turn cost|from your graveyard cost|has undaunted|have affinity for artifacts|other than your hand cost|spells cost|spells you cast cost|that target .* cost|those spells cost|you cast cost|you pay cost"
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('tagger.log', mode='w')
    ]
)

### Setup
## Load the dataframe
def load_dataframe(color: str):
    """
    Load and validate the card dataframe for a given color.

    Args:
        color (str): The color of cards to load ('white', 'blue', etc)

    Raises:
        FileNotFoundError: If CSV file doesn't exist and can't be regenerated
        ValueError: If required columns are missing
    """
    try:
        filepath = f'{csv_directory}/{color}_cards.csv'

        # Check if file exists, regenerate if needed
        if not os.path.exists(filepath):
            logging.warning(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"Failed to generate {filepath}")

        # Load initial dataframe for validation
        check_df = pd.read_csv(filepath)
        
        # Validate DataFrame structure
        try:
            setup_utility.validate_card_dataframe(check_df)
        except ValueError as e:
            logging.error(f'DataFrame validation failed: {e}')
            raise

        # Check for required columns
        # Validate required columns
        required_columns = ['creatureTypes', 'themeTags'] 
        missing_columns = [col for col in required_columns if col not in check_df.columns]

        # Handle missing columns
        if missing_columns:
            logging.warning(f"Missing columns: {missing_columns}")
            if 'creatureTypes' not in check_df.columns:
                kindred_tagging(check_df, color)
            if 'themeTags' not in check_df.columns:
                create_theme_tags(check_df, color)

            # Verify columns were added successfully
            check_df = pd.read_csv(filepath)
            still_missing = [col for col in required_columns if col not in check_df.columns]
            if still_missing:
                raise ValueError(f"Failed to add required columns: {still_missing}")

        # Load final dataframe with proper converters
        df = setup_utility.process_card_dataframe(pd.read_csv(filepath, converters={'themeTags': pd.eval, 'creatureTypes': pd.eval}))

        # Process the dataframe
        tag_by_color(df, color)

    except FileNotFoundError as e:
        logging.error(f'Error: {e}')
        raise
    except pd.errors.ParserError as e:
        logging.error(f'Error parsing the CSV file: {e}')
        raise
    except Exception as e:
        logging.error(f'An unexpected error occurred: {e}')
        raise

## Tag cards on a color-by-color basis
def tag_by_color(df, color):
    
    #load_dataframe()
    #answer = input('Would you like to regenerate the CSV file?\n')
    #if answer.lower() in ['yes', 'y']:
    #    regenerate_csv_by_color(color)
    #    kindred_tagging(df, color)
    #    create_theme_tags(df, color)
    #else:
    #    pass
    kindred_tagging(df, color)
    print('\n====================\n')
    create_theme_tags(df, color)
    print('\n====================\n')
    
    # Go through each type of tagging
    add_creatures_to_tags(df, color)
    print('\n====================\n')
    tag_for_card_types(df, color)
    print('\n====================\n')
    tag_for_keywords(df, color)
    print('\n====================\n')
    
    ## Tag for various effects
    tag_for_cost_reduction(df, color)
    print('\n====================\n')
    tag_for_card_draw(df, color)
    print('\n====================\n')
    tag_for_artifacts(df, color)
    print('\n====================\n')
    tag_for_enchantments(df, color)
    print('\n====================\n')
    tag_for_exile_matters(df, color)
    print('\n====================\n')
    tag_for_tokens(df, color)
    print('\n====================\n')
    tag_for_life_matters(df, color)
    print('\n====================\n')
    tag_for_counters(df, color)
    print('\n====================\n')
    tag_for_voltron(df, color)
    print('\n====================\n')
    tag_for_lands_matter(df, color)
    print('\n====================\n')
    tag_for_spellslinger(df, color)
    print('\n====================\n')
    tag_for_ramp(df, color)
    print('\n====================\n')
    tag_for_themes(df, color)
    print('\n====================\n')
    tag_for_interaction(df, color)
    print('\n====================\n')
    
    # Lastly, sort all theme tags for easier reading
    sort_theme_tags(df, color)
    try:
        setup_utility.filter_card_dataframe(df, 'colorIdentity', color, f'{csv_directory}/{color}_cards.csv')
    except Exception as e:
        logging.error(f'Error saving {color}_cards.csv: {e}')
        raise
    #print(df)
    print('\n====================\n')
    logging.info(f'Tags are done being set on {color}_cards.csv')
    #keyboard.wait('esc')

## Determine any non-creature cards that have creature types mentioned
def kindred_tagging(df: pd.DataFrame, color: str) -> None:
    """Tag cards with creature types and related types.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Setting creature type tags on {color}_cards.csv')

    try:
        # Initialize creatureTypes column vectorized
        df['creatureTypes'] = pd.Series([[] for _ in range(len(df))])
    
        # Detect creature types using mask
        creature_mask = utility.create_type_mask(df, 'Creature')
        if creature_mask.any():
            creature_rows = df[creature_mask]
            for idx, row in creature_rows.iterrows():
                types = utility.extract_creature_types(
                    row['type'],
                    settings.creature_types,
                    settings.non_creature_types
                )
                if types:
                    df.at[idx, 'creatureTypes'] = types

        creature_time = pd.Timestamp.now()
        logging.info(f'Creature type detection completed in {(creature_time - start_time).total_seconds():.2f}s')
        print('\n==========\n')
        
        logging.info(f'Setting Outlaw creature type tags on {color}_cards.csv')
        # Process outlaw types
        outlaws = settings.OUTLAW_TYPES
        df['creatureTypes'] = df.apply(
            lambda row: utility.add_outlaw_type(row['creatureTypes'], outlaws)
            if isinstance(row['creatureTypes'], list) else row['creatureTypes'],
            axis=1
        )

        outlaw_time = pd.Timestamp.now()
        logging.info(f'Outlaw type processing completed in {(outlaw_time - creature_time).total_seconds():.2f}s')

        # Find creature types in text
        logging.info('Checking for creature types in card text')
        # Check for creature types in text (i.e. how 'Voja, Jaws of the Conclave' cares about Elves)
        logging.info(f'Checking for and setting creature types found in the text of cards in {color}_cards.csv')
        ignore_list = [
            'Elite Inquisitor', 'Breaker of Armies',
            'Cleopatra, Exiled Pharaoh', 'Nath\'s Buffoon'
        ]

        for idx, row in df.iterrows():
            if row['name'] not in ignore_list:
                text_types = utility.find_types_in_text(
                    row['text'],
                    row['name'], 
                    settings.creature_types
                )
                if text_types:
                    current_types = row['creatureTypes']
                    if isinstance(current_types, list):
                        df.at[idx, 'creatureTypes'] = sorted(
                            list(set(current_types + text_types))
                        )

        text_time = pd.Timestamp.now()
        logging.info(f'Text-based type detection completed in {(text_time - outlaw_time).total_seconds():.2f}s')

        # Save results
        try:
            columns_to_keep = [
                'name', 'faceName', 'edhrecRank', 'colorIdentity',
                'colors', 'manaCost', 'manaValue', 'type',
                'creatureTypes', 'text', 'power', 'toughness',
                'keywords', 'layout', 'side'
            ]
            df = df[columns_to_keep]
            df.to_csv(f'{settings.csv_directory}/{color}_cards.csv', index=False)
            total_time = pd.Timestamp.now() - start_time
            logging.info(f'Creature type tagging completed in {total_time.total_seconds():.2f}s')

        except Exception as e:
            logging.error(f'Error saving results: {e}')

    # Overwrite file with creature type tags
    except Exception as e:
        logging.error(f'Error in kindred_tagging: {e}')
        raise
    
def create_theme_tags(df: pd.DataFrame, color: str) -> None:
    """Initialize and configure theme tags for a card DataFrame.

    This function initializes the themeTags column, validates the DataFrame structure,
    and reorganizes columns in an efficient manner. It uses vectorized operations
    for better performance.

    Args:
        df: DataFrame containing card data to process
        color: Color identifier for logging purposes (e.g. 'white', 'blue')

    Returns:
        The processed DataFrame with initialized theme tags and reorganized columns

    Raises:
        ValueError: If required columns are missing or color is invalid
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info('Initializing theme tags for %s cards', color)

    # Validate inputs
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")
    if not isinstance(color, str):
        raise TypeError("color must be a string")
    if color not in settings.colors:
        raise ValueError(f"Invalid color: {color}")

    try:
        # Initialize themeTags column using vectorized operation
        df['themeTags'] = pd.Series([[] for _ in range(len(df))], index=df.index)

        # Define expected columns
        required_columns = {
            'name', 'text', 'type', 'keywords',
            'creatureTypes', 'power', 'toughness'
        }

        # Validate required columns
        missing = required_columns - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Define column order
        columns_to_keep = settings.REQUIRED_COLUMNS

        # Reorder columns efficiently
        available_cols = [col for col in columns_to_keep if col in df.columns]
        df = df.reindex(columns=available_cols)
        
        # Save results
        try:
            df.to_csv(f'{settings.csv_directory}/{color}_cards.csv', index=False)
            total_time = pd.Timestamp.now() - start_time
            logging.info(f'Creature type tagging completed in {total_time.total_seconds():.2f}s')

            # Log performance metrics
            end_time = pd.Timestamp.now()
            duration = (end_time - start_time).total_seconds()
            logging.info('Theme tags initialized in %.2f seconds', duration)

        except Exception as e:
            logging.error(f'Error saving results: {e}')
            
    except Exception as e:
        logging.error('Error initializing theme tags: %s', str(e))
        raise

def tag_for_card_types(df: pd.DataFrame, color: str) -> None:
    """Tag cards based on their types using vectorized operations.

    This function efficiently applies tags based on card types using vectorized operations.
    It handles special cases for different card types and maintains compatibility with
    the existing tagging system.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info('Setting card type tags on %s_cards.csv', color)

    try:
        # Validate required columns
        required_cols = {'type', 'themeTags'}
        if not required_cols.issubset(df.columns):
            raise ValueError(f"Missing required columns: {required_cols - set(df.columns)}")

        # Define type-to-tag mapping
        type_tag_map = settings.TYPE_TAG_MAPPING

        # Process each card type
        for card_type, tags in type_tag_map.items():
            mask = utility.create_type_mask(df, card_type)
            if mask.any():
                utility.apply_tag_vectorized(df, mask, tags)
                logging.info('Tagged %d cards with %s type', mask.sum(), card_type)

        # Log completion
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Card type tagging completed in %.2fs', duration)

    except Exception as e:
        logging.error('Error in tag_for_card_types: %s', str(e))
        raise
    # Overwrite file with artifact tag added
    logging.info(f'Card type tags set on {color}_cards.csv.')

## Add creature types to the theme tags
def add_creatures_to_tags(df: pd.DataFrame, color: str) -> None:
    """Add kindred tags to theme tags based on creature types using vectorized operations.

    This function efficiently processes creature types and adds corresponding kindred tags
    using pandas vectorized operations instead of row-by-row iteration.

    Args:
        df: DataFrame containing card data with creatureTypes and themeTags columns
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Adding creature types to theme tags in {color}_cards.csv')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'creatureTypes', 'themeTags'}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Create mask for rows with non-empty creature types
        has_creatures_mask = df['creatureTypes'].apply(lambda x: bool(x) if isinstance(x, list) else False)

        if has_creatures_mask.any():
            # Get rows with creature types
            creature_rows = df[has_creatures_mask]

            # Generate kindred tags vectorized
            def add_kindred_tags(row):
                current_tags = row['themeTags']
                kindred_tags = [f"{ct} Kindred" for ct in row['creatureTypes']]
                return sorted(list(set(current_tags + kindred_tags)))

            # Update tags for matching rows
            df.loc[has_creatures_mask, 'themeTags'] = creature_rows.apply(add_kindred_tags, axis=1)

            duration = (pd.Timestamp.now() - start_time).total_seconds()
            logging.info(f'Added kindred tags to {has_creatures_mask.sum()} cards in {duration:.2f}s')

        else:
            logging.info('No cards with creature types found')

    except Exception as e:
        logging.error(f'Error in add_creatures_to_tags: {str(e)}')
        raise

    logging.info(f'Creature types added to theme tags in {color}_cards.csv')

## Add keywords to theme tags
def tag_for_keywords(df: pd.DataFrame, color: str) -> None:
    """Tag cards based on their keywords using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info('Tagging cards with keywords in %s_cards.csv', color)
    start_time = pd.Timestamp.now()

    try:
        # Create mask for valid keywords
        has_keywords = pd.notna(df['keywords'])

        if has_keywords.any():
            # Process cards with keywords
            keywords_df = df[has_keywords].copy()
            
            # Split keywords into lists
            keywords_df['keyword_list'] = keywords_df['keywords'].str.split(', ')
            
            # Add each keyword as a tag
            for idx, row in keywords_df.iterrows():
                if isinstance(row['keyword_list'], list):
                    current_tags = df.at[idx, 'themeTags']
                    new_tags = sorted(list(set(current_tags + row['keyword_list'])))
                    df.at[idx, 'themeTags'] = new_tags

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Tagged %d cards with keywords in %.2f seconds', has_keywords.sum(), duration)

    except Exception as e:
        logging.error('Error tagging keywords: %s', str(e))
        raise

## Sort any set tags
def sort_theme_tags(df, color):
    logging.info(f'Alphabetically sorting theme tags in {color}_cards.csv.')
    
    df['themeTags'] = df['themeTags'].apply(utility.sort_list)
    
    columns_to_keep = ['name', 'faceName','edhrecRank', 'colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'creatureTypes', 'text', 'power', 'toughness', 'keywords', 'themeTags', 'layout', 'side']
    df = df[columns_to_keep]
    logging.info(f'Theme tags alphabetically sorted in {color}_cards.csv.')

### Cost reductions
def tag_for_cost_reduction(df: pd.DataFrame, color: str) -> None:
    """Tag cards that reduce spell costs using vectorized operations.

    This function identifies cards that reduce casting costs through various means including:
    - General cost reduction effects
    - Artifact cost reduction
    - Enchantment cost reduction 
    - Affinity and similar mechanics

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info('Tagging cost reduction cards in %s_cards.csv', color)
    start_time = pd.Timestamp.now()

    try:
        # Create masks for different cost reduction patterns
        cost_mask = utility.create_text_mask(df, PATTERN_GROUPS['cost_reduction'])

        # Add specific named cards
        named_cards = [
            'Ancient Cellarspawn', 'Beluna Grandsquall', 'Cheering Fanatic',
            'Cloud Key', 'Conduit of Ruin', 'Eluge, the Shoreless Sea',
            'Goblin Anarchomancer', 'Goreclaw, Terror of Qal Sisma',
            'Helm of Awakening', 'Hymn of the Wilds', 'It that Heralds the End',
            'K\'rrik, Son of Yawgmoth', 'Killian, Ink Duelist', 'Krosan Drover',
            'Memory Crystal', 'Myth Unbound', 'Mistform Warchief',
            'Ranar the Ever-Watchful', 'Rowan, Scion of War', 'Semblence Anvil',
            'Spectacle Mage', 'Spellwild Ouphe', 'Strong Back',
            'Thryx, the Sudden Storm', 'Urza\'s Filter', 'Will, Scion of Peace',
            'Will Kenrith'
        ]
        named_mask = utility.create_name_mask(df, named_cards)

        # Combine masks
        final_mask = cost_mask | named_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Cost Reduction'])

        # Add spellslinger tags for noncreature spell cost reduction
        spell_mask = final_mask & utility.create_text_mask(df, r"Sorcery|Instant|noncreature")
        utility.apply_tag_vectorized(df, spell_mask, ['Spellslinger', 'Spells Matter'])

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Tagged %d cost reduction cards in %.2fs', final_mask.sum(), duration)

    except Exception as e:
        logging.error('Error tagging cost reduction cards: %s', str(e))
        raise

### Card draw/advantage
## General card draw/advantage
def tag_for_card_draw(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have card draw effects or care about drawing cards.

    This function identifies and tags cards with various types of card draw effects including:
    - Conditional draw (triggered/activated abilities)
    - Looting effects (draw + discard)
    - Cost-based draw (pay life/sacrifice)
    - Replacement draw effects
    - Wheel effects
    - Unconditional draw

    The function maintains proper tag hierarchy and ensures consistent application
    of related tags like 'Card Draw', 'Spellslinger', etc.

    Args:
        df: DataFrame containing card data to process
        color: Color identifier for logging purposes (e.g. 'white', 'blue')

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting card draw effect tagging for {color}_cards.csv')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags'}
        utility.validate_dataframe_columns(df, required_cols)

        # Process each type of draw effect
        tag_for_conditional_draw(df, color)
        logging.info('Completed conditional draw tagging')
        print('\n==========\n')

        tag_for_loot_effects(df, color)
        logging.info('Completed loot effects tagging')
        print('\n==========\n')

        tag_for_cost_draw(df, color)
        logging.info('Completed cost-based draw tagging')
        print('\n==========\n')

        tag_for_replacement_draw(df, color)
        logging.info('Completed replacement draw tagging')
        print('\n==========\n')

        tag_for_wheels(df, color)
        logging.info('Completed wheel effects tagging')
        print('\n==========\n')

        tag_for_unconditional_draw(df, color)
        logging.info('Completed unconditional draw tagging')
        print('\n==========\n')

        # Log completion and performance metrics
        duration = pd.Timestamp.now() - start_time
        logging.info(f'Completed all card draw tagging in {duration.total_seconds():.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_card_draw: {str(e)}')
        raise

## Conditional card draw (i.e. Rhystic Study or Trouble In Pairs)    
def create_unconditional_draw_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with unconditional draw effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have unconditional draw effects
    """
    # Create pattern for draw effects using num_to_search
    draw_patterns = [f'draw {num} card' for num in num_to_search]
    draw_mask = utility.create_text_mask(df, draw_patterns)

    # Create exclusion mask for conditional effects
    excluded_tags = settings.DRAW_RELATED_TAGS
    tag_mask = utility.create_tag_mask(df, excluded_tags)

    # Create text-based exclusions
    text_patterns = settings.DRAW_EXCLUSION_PATTERNS
    text_mask = utility.create_text_mask(df, text_patterns)

    return draw_mask & ~(tag_mask | text_mask)

def tag_for_unconditional_draw(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have unconditional draw effects using vectorized operations.

    This function identifies and tags cards that draw cards without conditions or
    additional costs. It excludes cards that already have conditional draw tags
    or specific keywords.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging unconditional draw effects in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create mask for unconditional draw effects
        draw_mask = create_unconditional_draw_mask(df)

        # Apply tags
        utility.apply_tag_vectorized(df, draw_mask, ['Unconditional Draw', 'Card Draw'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {draw_mask.sum()} cards with unconditional draw effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging unconditional draw effects: {str(e)}')
        raise

## Conditional card draw (i.e. Rhystic Study or Trouble In Pairs)
def create_conditional_draw_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from conditional draw effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    # Create tag-based exclusions
    excluded_tags = settings.DRAW_RELATED_TAGS
    tag_mask = utility.create_tag_mask(df, excluded_tags)

    # Create text-based exclusions
    text_patterns = settings.DRAW_EXCLUSION_PATTERNS + ['whenever you draw a card']
    text_mask = utility.create_text_mask(df, text_patterns)

    # Create name-based exclusions
    excluded_names = ['relic vial', 'vexing bauble']
    name_mask = utility.create_name_mask(df, excluded_names)

    return tag_mask | text_mask | name_mask

def create_conditional_draw_trigger_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with conditional draw triggers.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have trigger patterns
    """
    # Build trigger patterns
    trigger_patterns = []
    for trigger in triggers:
        # Permanent/creature/player triggers
        trigger_patterns.extend([
            f'{trigger} a permanent',
            f'{trigger} a creature',
            f'{trigger} a player',
            f'{trigger} an opponent',
            f'{trigger} another creature',
            f'{trigger} enchanted player',
            f'{trigger} one or more creatures',
            f'{trigger} one or more other creatures',
            f'{trigger} you'
        ])
        
        # Name-based attack triggers
        trigger_patterns.append(f'{trigger} .* attacks')

    # Create trigger mask
    trigger_mask = utility.create_text_mask(df, trigger_patterns)

    # Add other trigger patterns
    other_patterns = ['created a token', 'draw a card for each']
    other_mask = utility.create_text_mask(df, other_patterns)

    return trigger_mask | other_mask

def create_conditional_draw_effect_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with draw effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have draw effects
    """
    # Create draw patterns using num_to_search
    draw_patterns = [f'draw {num} card' for num in num_to_search]
    
    # Add token and 'draw for each' patterns
    draw_patterns.extend([
        'created a token.*draw',
        'draw a card for each'
    ])

    return df['text'].str.contains('|'.join(draw_patterns), case=False, na=False)

def tag_for_conditional_draw(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have conditional draw effects using vectorized operations.

    This function identifies and tags cards that draw cards based on triggers or conditions.
    It handles various patterns including:
    - Permanent/creature triggers
    - Player-based triggers
    - Token creation triggers
    - 'Draw for each' effects

    The function excludes cards that:
    - Already have certain tags (Cycling, Imprint, etc.)
    - Contain specific text patterns (annihilator, ravenous)
    - Have specific names (relic vial, vexing bauble)

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging conditional draw effects in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create exclusion mask
        exclusion_mask = create_conditional_draw_exclusion_mask(df)

        # Create trigger mask
        trigger_mask = create_conditional_draw_trigger_mask(df)

        # Create draw effect mask
        draw_patterns = [f'draw {num} card' for num in num_to_search]
    
        # Add token and 'draw for each' patterns
        draw_patterns.extend([
            'created a token.*draw',
            'draw a card for each'
        ])

        draw_mask = utility.create_text_mask(df, draw_patterns)

        # Combine masks
        final_mask = trigger_mask & draw_mask & ~exclusion_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Conditional Draw', 'Card Draw'])

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with conditional draw effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging conditional draw effects: {str(e)}')
        raise

## Loot effects, I.E. draw a card, discard a card. Or discard a card, draw a card
def create_loot_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with standard loot effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have loot effects
    """
    # Exclude cards that already have other loot-like effects
    has_other_loot = utility.create_tag_mask(df, ['Cycling', 'Connive']) | df['text'].str.contains('blood token', case=False, na=False)
    
    # Match draw + discard patterns
    draw_patterns = [f'draw {num} card' for num in num_to_search]
    discard_patterns = [
        'discard the rest',
        'for each card drawn this way, discard',
        'if you do, discard',
        'then discard'
    ]
    
    has_draw = utility.create_text_mask(df, draw_patterns)
    has_discard = utility.create_text_mask(df, discard_patterns)
    
    return ~has_other_loot & has_draw & has_discard

def create_connive_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with connive effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have connive effects
    """
    has_keyword = utility.create_keyword_mask(df, 'Connive')
    has_text = utility.create_text_mask(df, 'connives?')
    return has_keyword | has_text

def create_cycling_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with cycling effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have cycling effects
    """
    has_keyword = utility.create_keyword_mask(df, 'Cycling')
    has_text = utility.create_text_mask(df, 'cycling')
    return has_keyword | has_text

def create_blood_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with blood token effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have blood token effects
    """
    return utility.create_text_mask(df, 'blood token')

def tag_for_loot_effects(df: pd.DataFrame, color: str) -> None:
    """Tag cards with loot-like effects using vectorized operations.

    This function handles tagging of all loot-like effects including:
    - Standard loot (draw + discard)
    - Connive
    - Cycling
    - Blood tokens

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging loot-like effects in {color}_cards.csv')

    # Create masks for each effect type
    loot_mask = create_loot_mask(df)
    connive_mask = create_connive_mask(df)
    cycling_mask = create_cycling_mask(df)
    blood_mask = create_blood_mask(df)

    # Apply tags based on masks
    if loot_mask.any():
        utility.apply_tag_vectorized(df, loot_mask, ['Loot', 'Card Draw'])
        logging.info(f'Tagged {loot_mask.sum()} cards with standard loot effects')

    if connive_mask.any():
        utility.apply_tag_vectorized(df, connive_mask, ['Connive', 'Loot', 'Card Draw'])
        logging.info(f'Tagged {connive_mask.sum()} cards with connive effects')

    if cycling_mask.any():
        utility.apply_tag_vectorized(df, cycling_mask, ['Cycling', 'Loot', 'Card Draw'])
        logging.info(f'Tagged {cycling_mask.sum()} cards with cycling effects')

    if blood_mask.any():
        utility.apply_tag_vectorized(df, blood_mask, ['Blood Tokens', 'Loot', 'Card Draw'])
        logging.info(f'Tagged {blood_mask.sum()} cards with blood token effects')

    logging.info('Completed tagging loot-like effects')

## Sacrifice or pay life to draw effects
def tag_for_cost_draw(df: pd.DataFrame, color: str) -> None:
    """Tag cards that draw cards by paying life or sacrificing permanents.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info('Tagging cost-based draw effects in %s_cards.csv', color)

    # Split into life and sacrifice patterns
    life_pattern = 'life: draw'
    life_mask = df['text'].str.contains(life_pattern, case=False, na=False)

    sac_patterns = [
        r'sacrifice (?:a|an) (?:artifact|creature|permanent)(?:[^,]*),?[^,]*draw',
        r'sacrifice [^:]+: draw',
        r'sacrificed[^,]+, draw'
    ]
    sac_mask = df['text'].str.contains('|'.join(sac_patterns), case=False, na=False, regex=True)

    # Apply life draw tags
    if life_mask.any():
        utility.apply_tag_vectorized(df, life_mask, ['Life to Draw', 'Card Draw'])
        logging.info('Tagged %d cards with life payment draw effects', life_mask.sum())

    # Apply sacrifice draw tags
    if sac_mask.any():
        utility.apply_tag_vectorized(df, sac_mask, ['Sacrifice to Draw', 'Card Draw'])
        logging.info('Tagged %d cards with sacrifice draw effects', sac_mask.sum())

    logging.info('Completed tagging cost-based draw effects')

## Replacement effects, that might have you draw more cards
def create_replacement_draw_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with replacement draw effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have replacement draw effects
    """
    # Create trigger patterns
    trigger_patterns = []
    for trigger in triggers:
        trigger_patterns.extend([
            f'{trigger} a player.*instead.*draw',
            f'{trigger} an opponent.*instead.*draw', 
            f'{trigger} the beginning of your draw step.*instead.*draw',
            f'{trigger} you.*instead.*draw'
        ])

    # Create other replacement patterns
    replacement_patterns = [
        'if a player would.*instead.*draw',
        'if an opponent would.*instead.*draw', 
        'if you would.*instead.*draw'
    ]

    # Combine all patterns
    all_patterns = '|'.join(trigger_patterns + replacement_patterns)
    
    # Create base mask for replacement effects
    base_mask = utility.create_text_mask(df, all_patterns)

    # Add mask for specific card numbers
    number_patterns = [f'draw {num} card' for num in num_to_search]
    number_mask = utility.create_text_mask(df, number_patterns)

    # Add mask for non-specific numbers
    nonspecific_mask = utility.create_text_mask(df, 'draw that many plus|draws that many plus') # df['text'].str.contains('draw that many plus|draws that many plus', case=False, na=False)

    return base_mask & (number_mask | nonspecific_mask)

def create_replacement_draw_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from replacement draw effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    # Create tag-based exclusions
    excluded_tags = settings.DRAW_RELATED_TAGS
    tag_mask = utility.create_tag_mask(df, excluded_tags)

    # Create text-based exclusions
    text_patterns = settings.DRAW_EXCLUSION_PATTERNS + ['skips that turn instead']
    text_mask = utility.create_text_mask(df, text_patterns)

    return tag_mask | text_mask

def tag_for_replacement_draw(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have replacement draw effects using vectorized operations.

    This function identifies and tags cards that modify or replace card draw effects,
    such as drawing additional cards or replacing normal draw effects with other effects.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Example patterns tagged:
        - Trigger-based replacement effects ("whenever you draw...instead")
        - Conditional replacement effects ("if you would draw...instead")
        - Specific card number replacements
        - Non-specific card number replacements ("draw that many plus")
    """
    logging.info(f'Tagging replacement draw effects in {color}_cards.csv')

    try:
        # Create replacement draw mask
        replacement_mask = create_replacement_draw_mask(df)

        # Create exclusion mask
        exclusion_mask = create_replacement_draw_exclusion_mask(df)

        # Add specific card names
        specific_cards_mask = utility.create_name_mask(df, 'sylvan library')

        # Combine masks
        final_mask = (replacement_mask & ~exclusion_mask) | specific_cards_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Replacement Draw', 'Card Draw'])

        logging.info(f'Tagged {final_mask.sum()} cards with replacement draw effects')

    except Exception as e:
        logging.error(f'Error tagging replacement draw effects: {str(e)}')
        raise

    logging.info(f'Completed tagging replacement draw effects in {color}_cards.csv')

## Wheels
def tag_for_wheels(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have wheel effects or care about drawing/discarding cards.

    This function identifies and tags cards that:
    - Force excess draw and discard
    - Have payoffs for drawing/discarding
    - Care about wheel effects

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging "Wheel" effects in {color}_cards.csv')

    try:
        # Create masks for different wheel conditions
        # Define text patterns for wheel effects
        wheel_patterns = [
            'an opponent draws a card',
            'cards you\'ve drawn',
            'draw your second card',
            'draw that many cards',
            'draws an additional card',
            'draws a card',
            'draws cards',
            'draws half that many cards',
            'draws their first second card',
            'draws their second second card',
            'draw two cards instead',
            'draws two additional cards',
            'discards that card',
            'discards their hand, then draws',
            'each card your opponents have drawn',
            'each draw a card',
            'each opponent draws a card',
            'each player draws',
            'has no cards in hand',
            'have no cards in hand',
            'may draw a card',
            'maximum hand size',
            'no cards in it, you win the game instead',
            'opponent discards',
            'you draw a card',
            'whenever you draw a card'
        ]
        wheel_cards = [
            'arcane denial', 'bloodchief ascension', 'dark deal', 'elenda and azor', 'elixir of immortality',
            'forced fruition', 'glunch, the bestower', 'kiora the rising tide', 'kynaios and tiro of meletis',
            'library of leng','loran of the third path', 'mr. foxglove', 'raffine, scheming seer',
            'sauron, the dark lord', 'seizan, perverter of truth', 'triskaidekaphile', 'twenty-toed toad',
            'waste not', 'wedding ring', 'whispering madness'
        ]
        
        text_mask = utility.create_text_mask(df, wheel_patterns)
        name_mask = utility.create_name_mask(df, wheel_cards)

        # Combine masks
        final_mask = text_mask | name_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Card Draw', 'Wheels'])

        # Add Draw Triggers tag for cards with trigger words
        trigger_pattern = '|'.join(triggers)
        trigger_mask = final_mask & df['text'].str.contains(trigger_pattern, case=False, na=False)
        utility.apply_tag_vectorized(df, trigger_mask, ['Draw Triggers'])

        logging.info(f'Tagged {final_mask.sum()} cards with "Wheel" effects')

    except Exception as e:
        logging.error(f'Error tagging "Wheel" effects: {str(e)}')
        raise

### Artifacts
def tag_for_artifacts(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about Artifacts or are specific kinds of Artifacts
    (i.e. Equipment or Vehicles).

    This function identifies and tags cards with Artifact-related effects including:
    - Creating Artifact tokens
    - Casting Artifact spells
    - Equipment
    - Vehicles

    The function maintains proper tag hierarchy and ensures consistent application
    of related tags like 'Card Draw', 'Spellslinger', etc.

    Args:
        df: DataFrame containing card data to process
        color: Color identifier for logging purposes (e.g. 'white', 'blue')

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting "Artifact" and "Artifacts Matter" tagging for {color}_cards.csv')
    print('\n==========\n')
    
    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags'}
        utility.validate_dataframe_columns(df, required_cols)

        # Process each type of draw effect
        tag_for_artifact_tokens(df, color)
        logging.info('Completed Artifact token tagging')
        print('\n==========\n')

        tag_equipment(df, color)
        logging.info('Completed Equipment tagging')
        print('\n==========\n')

        tag_vehicles(df, color)
        logging.info('Completed Vehicle tagging')
        print('\n==========\n')
        
        # Log completion and performance metrics
        duration = pd.Timestamp.now() - start_time
        logging.info(f'Completed all "Artifact" and "Artifacts Matter" tagging in {duration.total_seconds():.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_artifacts: {str(e)}')
        raise

## Artifact Tokens
def tag_for_artifact_tokens(df: pd.DataFrame, color: str) -> None:
    """Tag cards that create or care about artifact tokens using vectorized operations.

    This function handles tagging of:
    - Generic artifact token creation
    - Predefined artifact token types (Treasure, Food, etc)
    - Fabricate keyword

    The function applies both generic artifact token tags and specific token type tags
    (e.g., 'Treasure Token', 'Food Token') based on the tokens created.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info('Setting artifact token tags on %s_cards.csv', color)
    start_time = pd.Timestamp.now()

    try:
        # Tag generic artifact tokens
        generic_mask = create_generic_artifact_mask(df)
        if generic_mask.any():
            utility.apply_tag_vectorized(df, generic_mask, 
                ['Artifact Tokens', 'Artifacts Matter', 'Token Creation', 'Tokens Matter'])
            logging.info('Tagged %d cards with generic artifact token effects', generic_mask.sum())

        # Tag predefined artifact tokens
        predefined_mask, token_map = create_predefined_artifact_mask(df)
        if predefined_mask.any():
            # Apply base artifact token tags
            utility.apply_tag_vectorized(df, predefined_mask,
                ['Artifact Tokens', 'Artifacts Matter', 'Token Creation', 'Tokens Matter'])

            # Track token type counts
            token_counts = {} # type: dict

            # Apply specific token type tags
            for idx, token_type in token_map.items():
                specific_tag = f'{token_type} Token'
                utility.apply_tag_vectorized(df.loc[idx:idx], pd.Series([True], index=[idx]), [specific_tag])
                token_counts[token_type] = token_counts.get(token_type, 0) + 1

            # Log results with token type counts
            logging.info('Tagged %d cards with predefined artifact tokens:', predefined_mask.sum())
            for token_type, count in token_counts.items():
                logging.info('  - %s: %d cards', token_type, count)

        # Tag fabricate cards
        fabricate_mask = create_fabricate_mask(df)
        if fabricate_mask.any():
            utility.apply_tag_vectorized(df, fabricate_mask,
                ['Artifact Tokens', 'Artifacts Matter', 'Token Creation', 'Tokens Matter'])
            logging.info('Tagged %d cards with Fabricate', fabricate_mask.sum())

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Completed artifact token tagging in %.2fs', duration)

    except Exception as e:
        logging.error('Error in tag_for_artifact_tokens: %s', str(e))
        raise

# Generic Artifact tokens, such as karnstructs, or artifact soldiers
def create_generic_artifact_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that create non-predefined artifact tokens.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards create generic artifact tokens
    """
    # Exclude specific cards
    excluded_cards = [
        'diabolical salvation',
        'lifecraft awakening',
        'sandsteppe war riders',
        'transmutation font'
    ]
    name_exclusions = utility.create_name_mask(df, excluded_cards)

    # Create text pattern matches
    create_pattern = r'create|put'
    has_create = utility.create_text_mask(df, create_pattern)

    token_patterns = [
        'artifact creature token',
        'artifact token',
        'construct artifact',
        'copy of enchanted artifact',
        'copy of target artifact',
        'copy of that artifact'
    ]
    has_token = utility.create_text_mask(df, token_patterns)

    # Named cards that create artifact tokens
    named_cards = [
        'bloodforged battle-axe', 'court of vantress', 'elmar, ulvenwald informant',
        'faerie artisans', 'feldon of the third path', 'lenoardo da vinci',
        'march of progress', 'nexus of becoming', 'osgir, the reconstructor',
        'prototype portal', 'red sun\'s twilight', 'saheeli, the sun\'s brilliance',
        'season of weaving', 'shaun, father of synths', 'sophia, dogged detective',
        'vaultborn tyrant', 'wedding ring'
    ]
    named_matches = utility.create_name_mask(df, named_cards)

    # Exclude fabricate cards
    has_fabricate = utility.create_text_mask(df, 'fabricate')

    return (has_create & has_token & ~name_exclusions & ~has_fabricate) | named_matches

def create_predefined_artifact_mask(df: pd.DataFrame) -> tuple[pd.Series, dict[int, str]]:
    """Create a boolean mask for cards that create predefined artifact tokens and track token types.

    Args:
        df: DataFrame to search

    Returns:
        Tuple containing:
            - Boolean Series indicating which cards create predefined artifact tokens
            - Dictionary mapping row indices to their matched token types
    """
    # Create base mask for 'create' text
    create_pattern = r'create|put'
    has_create = utility.create_text_mask(df, create_pattern)

    # Initialize token mapping dictionary
    token_map = {}

    # Create masks for each token type
    token_masks = []
    
    for token in settings.artifact_tokens:
        token_mask = utility.create_text_mask(df, token.lower())

        # Handle exclusions
        if token == 'Blood':
            token_mask &= df['name'] != 'Bloodroot Apothecary'
        elif token == 'Gold':
            token_mask &= ~df['name'].isin(['Goldspan Dragon', 'The Golden-Gear Colossus'])
        elif token == 'Junk':
            token_mask &= df['name'] != 'Junkyard Genius'

        # Store token type for matching rows
        matching_indices = df[token_mask].index
        for idx in matching_indices:
            if idx not in token_map:  # Only store first match
                token_map[idx] = token

        token_masks.append(token_mask)

    # Combine all token masks
    final_mask = has_create & pd.concat(token_masks, axis=1).any(axis=1)

    return final_mask, token_map
def create_fabricate_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with fabricate keyword.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have fabricate
    """
    return utility.create_text_mask(df, 'fabricate')

## Artifact Triggers
def create_artifact_triggers_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that care about artifacts.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards care about artifacts
    """
    # Define artifact-related patterns
    ability_patterns = [
        'abilities of artifact', 'ability of artifact'
    ]

    artifact_state_patterns = [
        'are artifacts in addition', 'artifact enters', 'number of artifacts',
        'number of other artifacts', 'number of tapped artifacts',
        'number of artifact'
    ]

    artifact_type_patterns = [
        'all artifact', 'another artifact', 'another target artifact',
        'artifact card', 'artifact creature you control',
        'artifact creatures you control', 'artifact you control',
        'artifacts you control', 'each artifact', 'target artifact'
    ]

    casting_patterns = [
        'affinity for artifacts', 'artifact spells as though they had flash',
        'artifact spells you cast', 'cast an artifact', 'choose an artifact',
        'whenever you cast a noncreature', 'whenever you cast an artifact'
    ]

    counting_patterns = [
        'mana cost among artifact', 'mana value among artifact',
        'artifact with the highest mana value',
    ]

    search_patterns = [
        'search your library for an artifact'
    ]

    trigger_patterns = [
        'whenever a nontoken artifact', 'whenever an artifact',
        'whenever another nontoken artifact', 'whenever one or more artifact'
    ]

    # Combine all patterns
    all_patterns = (
        ability_patterns + artifact_state_patterns + artifact_type_patterns +
        casting_patterns + counting_patterns + search_patterns + trigger_patterns +
        ['metalcraft', 'prowess', 'copy of any artifact']
    )

    # Create pattern string
    pattern = '|'.join(all_patterns)

    # Create mask
    return df['text'].str.contains(pattern, case=False, na=False, regex=True)

def tag_for_artifact_triggers(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about artifacts using vectorized operations.

    This function identifies and tags cards that:
    - Have abilities that trigger off artifacts
    - Care about artifact states or counts
    - Interact with artifact spells or permanents
    - Have metalcraft or similar mechanics

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging cards that care about artifacts in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create artifact triggers mask
        triggers_mask = create_artifact_triggers_mask(df)

        # Apply tags
        utility.apply_tag_vectorized(df, triggers_mask, ['Artifacts Matter'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {triggers_mask.sum()} cards with artifact triggers in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging artifact triggers: {str(e)}')
        raise

    logging.info(f'Completed tagging cards that care about artifacts in {color}_cards.csv')

## Equipment
def create_equipment_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that are Equipment

    This function identifies cards that:
    - Have the Equipment subtype

    Args:
        df: DataFrame containing card data

    Returns:
        Boolean Series indicating which cards are Equipment
    """
    # Create type-based mask
    type_mask = utility.create_type_mask(df, 'Equipment')

    return type_mask

def create_equipment_cares_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that care about Equipment.

    This function identifies cards that:
    - Have abilities that trigger off Equipment
    - Care about equipped creatures
    - Modify Equipment or equipped creatures
    - Have Equipment-related keywords

    Args:
        df: DataFrame containing card data

    Returns:
        Boolean Series indicating which cards care about Equipment
    """
    # Create text pattern mask
    text_patterns = [
        'equipment you control',
        'equipped creature',
        'attach',
        'equip',
        'equipment spells',
        'equipment abilities',
        'modified',
        'reconfigure'
    ]
    text_mask = utility.create_text_mask(df, text_patterns)

    # Create keyword mask
    keyword_patterns = ['Modified', 'Equip', 'Reconfigure']
    keyword_mask = utility.create_keyword_mask(df, keyword_patterns)

    # Create specific cards mask
    specific_cards = settings.EQUIPMENT_SPECIFIC_CARDS
    name_mask = utility.create_name_mask(df, specific_cards)

    return text_mask | keyword_mask | name_mask

def tag_equipment(df: pd.DataFrame, color: str) -> None:
    """Tag cards that are Equipment or care about Equipment using vectorized operations.

    This function identifies and tags:
    - Equipment cards
    - Cards that care about Equipment
    - Cards with Equipment-related abilities
    - Cards that modify Equipment or equipped creatures

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    logging.info('Tagging Equipment cards in %s_cards.csv', color)
    start_time = pd.Timestamp.now()

    try:
        # Create equipment mask
        equipment_mask = create_equipment_mask(df)
        if equipment_mask.any():
            utility.apply_tag_vectorized(df, equipment_mask, ['Equipment', 'Equipment Matters', 'Voltron'])
            logging.info('Tagged %d Equipment cards', equipment_mask.sum())

        # Create equipment cares mask
        cares_mask = create_equipment_cares_mask(df)
        if cares_mask.any():
            utility.apply_tag_vectorized(df, cares_mask, 
                ['Artifacts Matter', 'Equipment Matters', 'Voltron'])
            logging.info('Tagged %d cards that care about Equipment', cares_mask.sum())

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Completed Equipment tagging in %.2fs', duration)

    except Exception as e:
        logging.error('Error tagging Equipment cards: %s', str(e))
        raise
    
## Vehicles
def create_vehicle_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that are Vehicles or care about Vehicles.

    This function identifies cards that:
    - Have the Vehicle subtype
    - Have crew abilities
    - Care about Vehicles or Pilots

    Args:
        df: DataFrame containing card data

    Returns:
        Boolean Series indicating which cards are Vehicles or care about them
    """
    # Create type-based mask
    type_mask = utility.create_type_mask(df, ['Vehicle', 'Pilot'])

    # Create text-based mask
    text_patterns = [
        'vehicle', 'crew', 'pilot',
    ]
    text_mask = utility.create_text_mask(df, text_patterns)

    return type_mask | text_mask

def tag_vehicles(df: pd.DataFrame, color: str) -> None:
    """Tag cards that are Vehicles or care about Vehicles using vectorized operations.

    This function identifies and tags:
    - Vehicle cards
    - Pilot cards
    - Cards that care about Vehicles
    - Cards with crew abilities

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    logging.info('Tagging Vehicle cards in %s_cards.csv', color)
    start_time = pd.Timestamp.now()

    try:
        # Create vehicle mask
        vehicle_mask = create_vehicle_mask(df)
        if vehicle_mask.any():
            utility.apply_tag_vectorized(df, vehicle_mask, 
                ['Artifacts Matter', 'Vehicles'])
            logging.info('Tagged %d Vehicle-related cards', vehicle_mask.sum())

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Completed Vehicle tagging in %.2fs', duration)

    except Exception as e:
        logging.error('Error tagging Vehicle cards: %s', str(e))
        raise
    
### Enchantments
def tag_for_enchantments(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about Enchantments or are specific kinds of Enchantments
    (i.e. Equipment or Vehicles).

    This function identifies and tags cards with Enchantment-related effects including:
    - Creating Enchantment tokens
    - Casting Enchantment spells
    - Auras
    - Constellation
    - Cases
    - Rooms
    - Classes
    - Backrounds
    - Shrines

    The function maintains proper tag hierarchy and ensures consistent application
    of related tags like 'Card Draw', 'Spellslinger', etc.

    Args:
        df: DataFrame containing card data to process
        color: Color identifier for logging purposes (e.g. 'white', 'blue')

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting "Enchantment" and "Enchantments Matter" tagging for {color}_cards.csv')
    print('\n==========\n')
    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags'}
        utility.validate_dataframe_columns(df, required_cols)

        # Process each type of enchantment effect
        tag_for_enchantment_tokens(df, color)
        logging.info('Completed Enchantment token tagging')
        print('\n==========\n')

        tag_for_enchantments_matter(df, color)
        logging.info('Completed "Enchantments Matter" tagging')
        print('\n==========\n')

        tag_auras(df, color)
        logging.info('Completed Aura tagging')
        print('\n==========\n')
        
        tag_constellation(df, color)
        logging.info('Completed Constellation tagging')
        print('\n==========\n')
        
        tag_sagas(df, color)
        logging.info('Completed Saga tagging')
        print('\n==========\n')
        
        tag_cases(df, color)
        logging.info('Completed Case tagging')
        print('\n==========\n')
        
        tag_rooms(df, color)
        logging.info('Completed Room tagging')
        print('\n==========\n')
        
        tag_backgrounds(df, color)
        logging.info('Completed Background tagging')
        print('\n==========\n')
        
        tag_shrines(df, color)
        logging.info('Completed Shrine tagging')
        print('\n==========\n')
        
        # Log completion and performance metrics
        duration = pd.Timestamp.now() - start_time
        logging.info(f'Completed all "Enchantment" and "Enchantments Matter" tagging in {duration.total_seconds():.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_artifacts: {str(e)}')
        raise

## Enchantment tokens
def tag_for_enchantment_tokens(df: pd.DataFrame, color: str) -> None:
    """Tag cards that create or care about enchantment tokens using vectorized operations.

    This function handles tagging of:
    - Generic enchantmeny token creation
    - Predefined enchantment token types (Roles, Shards, etc)

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info('Setting ehcantment token tags on %s_cards.csv', color)
    start_time = pd.Timestamp.now()

    try:
        # Tag generic artifact tokens
        generic_mask = create_generic_enchantment_mask(df)
        if generic_mask.any():
            utility.apply_tag_vectorized(df, generic_mask, 
                ['Enchantment Tokens', 'Enchantments Matter', 'Token Creation', 'Tokens Matter'])
            logging.info('Tagged %d cards with generic enchantment token effects', generic_mask.sum())

        # Tag predefined artifact tokens
        predefined_mask = create_predefined_enchantment_mask(df)
        if predefined_mask.any():
            utility.apply_tag_vectorized(df, predefined_mask,
                ['Enchantment Tokens', 'Enchantments Matter', 'Token Creation', 'Tokens Matter'])
            logging.info('Tagged %d cards with predefined enchantment tokens', predefined_mask.sum())

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Completed enchantment token tagging in %.2fs', duration)

    except Exception as e:
        logging.error('Error in tag_for_enchantment_tokens: %s', str(e))
        raise

def create_generic_enchantment_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that create non-predefined enchantment tokens.
    
    Args:
        df: DataFrame to search
    
    Returns:
        Boolean Series indicating which cards create generic enchantmnet tokens
    """
    # Create text pattern matches
    create_pattern = r'create|put'
    has_create = utility.create_text_mask(df, create_pattern)
    
    token_patterns = [
        'copy of enchanted enchantment',
        'copy of target enchantment',
        'copy of that enchantment',
        'enchantment creature token',
        'enchantment token'
    ]
    has_token = utility.create_text_mask(df, token_patterns)
    
    # Named cards that create enchantment tokens
    named_cards = [
        'court of vantress',
        'fellhide spiritbinder',
        'hammer of purphoros'
    ]
    named_matches = utility.create_name_mask(df, named_cards)
    
    return (has_create & has_token) | named_matches

def create_predefined_enchantment_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that create non-predefined enchantment tokens.
    
    Args:
        df: DataFrame to search
    
    Returns:
        Boolean Series indicating which cards create generic enchantmnet tokens
    """
    # Create text pattern matches
    has_create = df['text'].str.contains('create', case=False, na=False)
    
    # Create masks for each token type
    token_masks = []
    for token in settings.enchantment_tokens:
        token_mask = utility.create_text_mask(df, token.lower())
        
        token_masks.append(token_mask)
        
    return has_create & pd.concat(token_masks, axis=1).any(axis=1)
    
## General enchantments matter
def tag_for_enchantments_matter(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about enchantments using vectorized operations.

    This function identifies and tags cards that:
    - Have abilities that trigger off enchantments
    - Care about enchantment states or counts
    - Interact with enchantment spells or permanents
    - Have constellation or similar mechanics

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging cards that care about enchantments in {color}_cards.csv')
    start_time = pd.Timestamp.now()
    
    try:
        # Create enchantment triggers mask
        # Define enchantment-related patterns
        ability_patterns = [
            'abilities of enchantment', 'ability of enchantment'
        ]

        state_patterns = [
            'are enchantments in addition', 'enchantment enters'
        ]

        type_patterns = [
            'all enchantment', 'another enchantment', 'enchantment card',
            'enchantment creature you control', 'enchantment creatures you control',
            'enchantment you control', 'enchantments you control'
        ]

        casting_patterns = [
            'cast an enchantment', 'enchantment spells as though they had flash',
            'enchantment spells you cast'
        ]

        counting_patterns = [
            'mana value among enchantment', 'number of enchantment'
        ]

        search_patterns = [
            'search your library for an enchantment'
        ]

        trigger_patterns = [
            'whenever a nontoken enchantment', 'whenever an enchantment',
            'whenever another nontoken enchantment', 'whenever one or more enchantment'
        ]

        # Combine all patterns
        all_patterns = (
            ability_patterns + state_patterns + type_patterns +
            casting_patterns + counting_patterns + search_patterns + trigger_patterns
        )
        triggers_mask = utility.create_text_mask(df, all_patterns)

        # Create exclusion mask
        exclusion_mask = utility.create_name_mask(df, 'luxa river shrine')

        # Combine masks
        final_mask = triggers_mask & ~exclusion_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Enchantments Matter'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with enchantment triggers in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging enchantment triggers: {str(e)}')
        raise

    logging.info(f'Completed tagging cards that care about enchantments in {color}_cards.csv')

## Aura
def tag_auras(df: pd.DataFrame, color: str) -> None:
    """Tag cards that are Auras or care about Auras using vectorized operations.

    This function identifies cards that:
    - Have abilities that trigger off Auras
    - Care about enchanted permanents
    - Modify Auras or enchanted permanents
    - Have Aura-related keywords

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    logging.info('Tagging Aura cards in %s_cards.csv', color)
    start_time = pd.Timestamp.now()
    
    try:
        # Create Aura mask
        aura_mask = utility.create_type_mask(df, 'Aura')
        if aura_mask.any():
            utility.apply_tag_vectorized(df, aura_mask,
                ['Auras', 'Enchantments Matter', 'Voltron'])
            logging.info('Tagged %d Aura cards', aura_mask.sum())
            
        # Create cares mask
        text_patterns = [
            'aura',
            'aura enters',
            'aura you control enters',
            'enchanted'
        ]
        cares_mask = utility.create_text_mask(df, text_patterns) | utility.create_name_mask(df, settings.AURA_SPECIFIC_CARDS)
        if cares_mask.any():
            utility.apply_tag_vectorized(df, cares_mask,
                ['Auras', 'Enchantments Matter', 'Voltron'])
            logging.info('Tagged %d cards that care about Auras', cares_mask.sum())
        
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Completed Aura tagging in %.2fs', duration)
    
    except Exception as e:
        logging.error('Error tagging Aura cards: %s', str(e))
        raise
    
## Constellation
def tag_constellation(df: pd.DataFrame, color: str) -> None:
    """Tag cards with Constellation using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging Constellation cards in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create mask for constellation keyword
        constellation_mask = utility.create_keyword_mask(df, 'Constellation')

        # Apply tags
        utility.apply_tag_vectorized(df, constellation_mask, ['Constellation', 'Enchantments Matter'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {constellation_mask.sum()} Constellation cards in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging Constellation cards: {str(e)}')
        raise

    logging.info('Completed tagging Constellation cards')

## Sagas
def tag_sagas(df: pd.DataFrame, color: str) -> None:
    """Tag cards with the Saga type using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    
    Raises:
        ValueError: if required DataFramecolumns are missing
    """
    logging.info('Tagging Saga cards in %s_cards.csv', color)
    start_time = pd.Timestamp.now()

    try:
        # Create mask for Saga type
        saga_mask = utility.create_type_mask(df, 'Saga')
        if saga_mask.any():
            utility.apply_tag_vectorized(df, saga_mask,
                ['Enchantments Matter', 'Sagas Matter'])
            logging.info('Tagged %d Saga cards', saga_mask.sum())
        
        # Create mask for cards that care about Sagas
        text_patterns = [
            'saga',
            'put a saga',
            'final chapter',
            'lore counter'
        ]
        cares_mask = utility.create_text_mask(df, text_patterns) # create_saga_cares_mask(df)
        if cares_mask.any():
            utility.apply_tag_vectorized(df, cares_mask,
                ['Enchantments Matter', 'Sagas Matter'])
            logging.info('Tagged %d cards that care about Sagas', cares_mask.sum())
        
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Completed Saga tagging in %.2fs', duration)

    except Exception as e:
        logging.error(f'Error tagging Saga cards: {str(e)}')
        raise

    logging.info('Completed tagging Saga cards')
    
## Cases
def tag_cases(df: pd.DataFrame, color: str) -> None:
    """Tag cards with the Case subtype using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    
    Raises:
        ValueError: if required DataFramecolumns are missing
    """
    logging.info('Tagging Case cards in %s_cards.csv', color)
    start_time = pd.Timestamp.now()

    try:
        # Create mask for Case type
        saga_mask = utility.create_type_mask(df, 'Case')
        if saga_mask.any():
            utility.apply_tag_vectorized(df, saga_mask,
                ['Enchantments Matter', 'Cases Matter'])
            logging.info('Tagged %d Saga cards', saga_mask.sum())
        
        # Create Case cares_mask
        cares_mask = utility.create_text_mask(df, 'solve a case')
        if cares_mask.any():
            utility.apply_tag_vectorized(df, cares_mask,
                ['Enchantments Matter', 'Cases Matter'])
            logging.info('Tagged %d cards that care about Cases', cares_mask.sum())
        
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Completed Case tagging in %.2fs', duration)

    except Exception as e:
        logging.error(f'Error tagging Case cards: {str(e)}')
        raise

    logging.info('Completed tagging Case cards')

## Rooms
def tag_rooms(df: pd.DataFrame, color: str) -> None:
    """Tag cards with the room subtype using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    
    Raises:
        ValueError: if required DataFramecolumns are missing
    """
    logging.info('Tagging Room cards in %s_cards.csv', color)
    start_time = pd.Timestamp.now()

    try:
        # Create mask for Room type
        room_mask = utility.create_type_mask(df, 'Room')
        if room_mask.any():
            utility.apply_tag_vectorized(df, room_mask,
                ['Enchantments Matter', 'Rooms Matter'])
            logging.info('Tagged %d Room cards', room_mask.sum())
        
        # Create keyword mask for rooms
        keyword_mask = utility.create_keyword_mask(df, 'Eerie')
        if keyword_mask.any():
            utility.apply_tag_vectorized(df, keyword_mask,
                ['Enchantments Matter', 'Rooms Matter'])
        
        # Create rooms care mask
        cares_mask = utility.create_text_mask(df, 'target room')
        if cares_mask.any():
            utility.apply_tag_vectorized(df, cares_mask,
                ['Enchantments Matter', 'Rooms Matter'])
        logging.info('Tagged %d cards that care about Rooms', cares_mask.sum())
        
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Completed Room tagging in %.2fs', duration)

    except Exception as e:
        logging.error(f'Error tagging Room cards: {str(e)}')
        raise

    logging.info('Completed tagging Room cards')

## Classes
def tag_classes(df: pd.DataFrame, color: str) -> None:
    """Tag cards with the Class subtype using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    
    Raises:
        ValueError: if required DataFramecolumns are missing
    """
    logging.info('Tagging Class cards in %s_cards.csv', color)
    start_time = pd.Timestamp.now()

    try:
        # Create mask for class type
        class_mask = utility.create_type_mask(df, 'Class')
        if class_mask.any():
            utility.apply_tag_vectorized(df, class_mask,
                ['Enchantments Matter', 'Classes Matter'])
            logging.info('Tagged %d Class cards', class_mask.sum())
        
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Completed Class tagging in %.2fs', duration)

    except Exception as e:
        logging.error(f'Error tagging Class cards: {str(e)}')
        raise

    logging.info('Completed tagging Class cards')

## Background
def tag_backgrounds(df: pd.DataFrame, color: str) -> None:
    """Tag cards with the Background subtype or which let you choose a background using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    
    Raises:
        ValueError: if required DataFramecolumns are missing
    """
    logging.info('Tagging Background cards in %s_cards.csv', color)
    start_time = pd.Timestamp.now()

    try:
        # Create mask for background type
        class_mask = utility.create_type_mask(df, 'Background')
        if class_mask.any():
            utility.apply_tag_vectorized(df, class_mask,
                ['Enchantments Matter', 'Backgrounds Matter'])
            logging.info('Tagged %d Background cards', class_mask.sum())
        
        # Create mask for Choose a Background
        cares_mask = utility.create_text_mask(df, 'Background')
        if cares_mask.any():
            utility.apply_tag_vectorized(df, cares_mask,
                ['Enchantments Matter', 'Backgroundss Matter'])
            logging.info('Tagged %d cards that have Choose a Background', cares_mask.sum())
        
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Completed Background tagging in %.2fs', duration)

    except Exception as e:
        logging.error(f'Error tagging Background cards: {str(e)}')
        raise

    logging.info('Completed tagging Background cards')
    
## Shrines
def tag_shrines(df: pd.DataFrame, color: str) -> None:
    """Tag cards with the Shrine subtype using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    
    Raises:
        ValueError: if required DataFramecolumns are missing
    """
    logging.info('Tagging Shrine cards in %s_cards.csv', color)
    start_time = pd.Timestamp.now()

    try:
        # Create mask for shrine type
        class_mask = utility.create_type_mask(df, 'Shrine')
        if class_mask.any():
            utility.apply_tag_vectorized(df, class_mask,
                ['Enchantments Matter', 'Shrines Matter'])
            logging.info('Tagged %d Shrine cards', class_mask.sum())
        
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Completed Shrine tagging in %.2fs', duration)

    except Exception as e:
        logging.error(f'Error tagging Shrine cards: {str(e)}')
        raise

    logging.info('Completed tagging Shrine cards')

### Exile Matters
## Exile Matter effects, such as Impuse draw, foretell, etc...
def tag_for_exile_matters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about exiling cards and casting them from exile.

    This function identifies and tags cards with cast-from exile effects such as:
    - Cascade
    - Discover
    - Foretell
    - Imprint
    - Impulse
    - Plot
    - Susend

    The function maintains proper tag hierarchy and ensures consistent application
    of related tags like 'Card Draw', 'Spellslinger', etc.

    Args:
        df: DataFrame containing card data to process
        color: Color identifier for logging purposes (e.g. 'white', 'blue')

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting "Exile Matters" tagging for {color}_cards.csv')
    print('\n==========\n')
    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags'}
        utility.validate_dataframe_columns(df, required_cols)

        # Process each type of Exile matters effect
        tag_for_general_exile_matters(df, color)
        logging.info('Completed general Exile Matters tagging')
        print('\n==========\n')
        
        tag_for_cascade(df, color)
        logging.info('Completed Cascade tagging')
        print('\n==========\n')
        
        tag_for_discover(df, color)
        logging.info('Completed Disxover tagging')
        print('\n==========\n')
        
        tag_for_foretell(df, color)
        logging.info('Completed Foretell tagging')
        print('\n==========\n')
        
        tag_for_imprint(df, color)
        logging.info('Completed Imprint tagging')
        print('\n==========\n')
        
        tag_for_impulse(df, color)
        logging.info('Completed Impulse tagging')
        print('\n==========\n')
        
        tag_for_plot(df, color)
        logging.info('Completed Plot tagging')
        print('\n==========\n')
        
        tag_for_suspend(df, color)
        logging.info('Completed Suspend tagging')
        print('\n==========\n')
        
        
        # Log completion and performance metrics
        duration = pd.Timestamp.now() - start_time
        logging.info(f'Completed all "Exile Matters" tagging in {duration.total_seconds():.2f}s')
    
    except Exception as e:
        logging.error(f'Error in tag_for_exile_matters: {str(e)}')
        raise

def tag_for_general_exile_matters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have a general care about casting from Exile theme.

    This function identifies cards that:
    - Trigger off casting a card from exile
    - Trigger off playing a land from exile
    - Putting cards into exile to later play
    
    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purpposes
    
    Raises:
        ValueError: if required DataFrame columns are missing
    """
    logging.info('Tagging Exile Matters cards in %s_cards.csv', color)
    start_time =pd.Timestamp.now()
    
    try:
        # Create exile mask
        text_patterns = [
            'cards in exile',
            'cast a spell from exile',
            'cast but don\'t own',
            'cast from exile',
            'casts a spell from exile',
            'control but don\'t own',
            'exiled with',
            'from anywhere but their hand',
            'from anywhere but your hand',
            'from exile',
            'own in exile',
            'play a card from exile',
            'plays a card from exile',
            'play a land from exile',
            'plays a land from exile',
            'put into exile',
            'remains exiled'
            ]
        text_mask = utility.create_text_mask(df, text_patterns)
        if text_mask.any():
            utility.apply_tag_vectorized(df, text_mask, ['Exile Matters'])
            logging.info('Tagged %d Exile Matters cards', text_mask.sum())
        
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Completed Exile Matters tagging in %.2fs', duration)
    
    except Exception as e:
        logging.error('Error tagging Exile Matters cards: %s', str(e))
        raise

## Cascade cards
def tag_for_cascade(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have or otherwise give the Cascade ability

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    logging.info('Tagging Cascade cards in %s_cards.csv', color)
    start_time = pd.Timestamp.now()
    
    try:
        # Create Cascade mask
        text_patterns = [
            'gain cascade',
            'has cascade',
            'have cascade',
            'have "cascade',
            'with cascade',
        ]
        text_mask = utility.create_text_mask(df, text_patterns)
        if text_mask.any():
            utility.apply_tag_vectorized(df, text_mask, ['Cascade', 'Exile Matters'])
            logging.info('Tagged %d cards relating to Cascade', text_mask.sum())
        
        keyword_mask = utility.create_keyword_mask(df, 'Cascade')
        if keyword_mask.any():
            utility.apply_tag_vectorized(df, text_mask, ['Cascade', 'Exile Matters'])
            logging.info('Tagged %d cards that have Cascade', keyword_mask.sum())
    
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Completed Cascade tagging in %.2fs', duration)
    
    except Exception as e:
        logging.error('Error tagging Cacade cards: %s', str(e))
        raise
    
## Dsicover cards
def tag_for_discover(df: pd.DataFrame, color: str) -> None:
    """Tag cards with Discover using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging Discover cards in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create mask for Discover keyword
        keyword_mask = utility.create_keyword_mask(df, 'Discover')

        # Apply tags
        utility.apply_tag_vectorized(df, keyword_mask, ['Discover', 'Exile Matters'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {keyword_mask.sum()} Discover cards in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging Discover cards: {str(e)}')
        raise

    logging.info('Completed tagging Discover cards')

## Foretell cards, and cards that care about foretell
def tag_for_foretell(df: pd.DataFrame, color: str) -> None:
    """Tag cards with Foretell using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging Foretell cards in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create mask for Foretell keyword
        keyword_mask = utility.create_keyword_mask(df, 'Foretell')

        # Create mask for Foretell text
        text_mask = utility.create_text_mask(df, 'Foretell')

        final_mask = keyword_mask | text_mask
        # Apply tags
        utility.apply_tag_vectorized(df, final_mask,  ['Foretell', 'Exile Matters'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} Foretell cards in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging Foretell cards: {str(e)}')
        raise

    logging.info('Completed tagging Foretell cards')

## Cards that have or care about imprint
def tag_for_imprint(df: pd.DataFrame, color: str) -> None:
    """Tag cards with Imprint using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging Imprint cards in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create mask for Imprint keyword
        keyword_mask = utility.create_keyword_mask(df, 'Imprint')

        # Create mask for Imprint text
        text_mask = utility.create_text_mask(df, 'Imprint')

        final_mask = keyword_mask | text_mask
        # Apply tags
        utility.apply_tag_vectorized(df, final_mask,  ['Imprint', 'Exile Matters'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} Imprint cards in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging Imprint cards: {str(e)}')
        raise

    logging.info('Completed tagging Imprint cards')

## Cards that have or care about impulse
def create_impulse_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with impulse-like effects.

    This function identifies cards that exile cards from the top of libraries
    and allow playing them for a limited time, including:
    - Exile top card(s) with may cast/play effects
    - Named cards with similar effects
    - Junk token creation

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have Impulse effects
    """
    # Define text patterns
    exile_patterns = [
        'exile the top',
        'exiles the top'
    ]

    play_patterns = [
        'may cast',
        'may play'
    ]

    # Named cards with Impulse effects
    impulse_cards = [
        'daxos of meletis', 'bloodsoaked insight', 'florian, voldaren scion',
        'possibility storm', 'ragava, nimble pilferer', 'rakdos, the muscle',
        'stolen strategy', 'urabrask, heretic praetor', 'valakut exploration',
        'wild wasteland'
    ]

    # Create exclusion patterns
    exclusion_patterns = [
        'damage to each', 'damage to target', 'deals combat damage',
        'raid', 'target opponent\'s hand',
        ]
    secondary_exclusion_patterns = [
        'each opponent', 'morph', 'opponent\'s library',
        'skip your draw', 'target opponent', 'that player\'s',
        'you may look at the top card'
        ]
 
    # Create masks
    tag_mask = utility.create_tag_mask(df, 'Imprint')
    exile_mask = utility.create_text_mask(df, exile_patterns)
    play_mask = utility.create_text_mask(df, play_patterns)
    named_mask = utility.create_name_mask(df, impulse_cards)
    junk_mask = utility.create_text_mask(df, 'junk token')
    first_exclusion_mask = utility.create_text_mask(df, exclusion_patterns)
    planeswalker_mask = df['type'].str.contains('Planeswalker', case=False, na=False)
    second_exclusion_mask = utility.create_text_mask(df, secondary_exclusion_patterns)
    exclusion_mask = (~first_exclusion_mask & ~planeswalker_mask) & second_exclusion_mask

    # Combine masks
    impulse_mask = ((exile_mask & play_mask & ~exclusion_mask & ~tag_mask) | 
                   named_mask | junk_mask)
 
    return impulse_mask

def tag_for_impulse(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have impulse-like effects using vectorized operations.

    This function identifies and tags cards that exile cards from library tops
    and allow playing them for a limited time, including:
    - Exile top card(s) with may cast/play effects 
    - Named cards with similar effects
    - Junk token creation

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging Impulse effects in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create impulse mask
        impulse_mask = create_impulse_mask(df)

        # Apply tags
        utility.apply_tag_vectorized(df, impulse_mask, ['Exile Matters', 'Impulse'])

        # Add Junk Tokens tag where applicable
        junk_mask = impulse_mask & utility.create_text_mask(df, 'junk token')
        utility.apply_tag_vectorized(df, junk_mask, ['Junk Tokens'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {impulse_mask.sum()} cards with Impulse effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging Impulse effects: {str(e)}')
        raise

    logging.info('Completed tagging Impulse effects')
## Cards that have or care about plotting
def tag_for_plot(df: pd.DataFrame, color: str) -> None:
    """Tag cards with Plot using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging Plot cards in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create mask for Plot keyword
        keyword_mask = utility.create_keyword_mask(df, 'Plot')

        # Create mask for Plot keyword
        text_mask = utility.create_text_mask(df, 'Plot')

        final_mask = keyword_mask | text_mask
        # Apply tags
        utility.apply_tag_vectorized(df, final_mask,  ['Plot', 'Exile Matters'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} Plot cards in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging Plot cards: {str(e)}')
        raise

    logging.info('Completed tagging Plot cards')

## Cards that have or care about suspend
def tag_for_suspend(df: pd.DataFrame, color: str) -> None:
    """Tag cards with Suspend using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging Suspend cards in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create mask for Suspend keyword
        keyword_mask = utility.create_keyword_mask(df, 'Suspend')

        # Create mask for Suspend keyword
        text_mask = utility.create_text_mask(df, 'Suspend')

        final_mask = keyword_mask | text_mask
        # Apply tags
        utility.apply_tag_vectorized(df, final_mask,  ['Suspend', 'Exile Matters'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} Suspend cards in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging Suspend cards: {str(e)}')
        raise

    logging.info('Completed tagging Suspend cards')

### Tokens
def create_creature_token_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that create creature tokens.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards create creature tokens
    """
    # Create base pattern for token creation
    create_pattern = r'create|put'
    has_create = utility.create_text_mask(df, create_pattern)

    # Create pattern for creature tokens
    token_patterns = [
        'artifact creature token',
        'creature token',
        'enchantment creature token'
    ]
    has_token = utility.create_text_mask(df, token_patterns)

    # Create exclusion mask
    exclusion_patterns = ['fabricate', 'modular']
    exclusion_mask = utility.create_text_mask(df, exclusion_patterns)

    # Create name exclusion mask
    excluded_cards = ['agatha\'s soul cauldron']
    name_exclusions = utility.create_name_mask(df, excluded_cards)

    return has_create & has_token & ~exclusion_mask & ~name_exclusions

def create_token_modifier_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that modify token creation.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards modify token creation
    """
    # Create patterns for token modification
    modifier_patterns = [
        'create one or more',
        'one or more creature',
        'one or more tokens would be created',
        'one or more tokens would be put',
        'one or more tokens would enter',
        'one or more tokens you control',
        'put one or more'
    ]
    has_modifier = utility.create_text_mask(df, modifier_patterns)

    # Create patterns for token effects
    effect_patterns = ['instead', 'plus']
    has_effect = utility.create_text_mask(df, effect_patterns)

    # Create name exclusion mask
    excluded_cards = [
        'cloakwood swarmkeeper',
        'neyali, sun\'s vanguard',
        'staff of the storyteller'
    ]
    name_exclusions = utility.create_name_mask(df, excluded_cards)

    return has_modifier & has_effect & ~name_exclusions

def tag_for_tokens(df: pd.DataFrame, color: str) -> None:
    """Tag cards that create or modify tokens using vectorized operations.

    This function identifies and tags:
    - Cards that create creature tokens
    - Cards that modify token creation (doublers, replacement effects)
    - Cards that care about tokens

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info('Tagging token-related cards in %s_cards.csv', color)
    print('\n==========\n')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create creature token mask
        creature_mask = create_creature_token_mask(df)
        if creature_mask.any():
            utility.apply_tag_vectorized(df, creature_mask, 
                ['Creature Tokens', 'Token Creation', 'Tokens Matter'])
            logging.info('Tagged %d cards that create creature tokens', creature_mask.sum())

        # Create token modifier mask
        modifier_mask = create_token_modifier_mask(df)
        if modifier_mask.any():
            utility.apply_tag_vectorized(df, modifier_mask,
                ['Token Modification', 'Token Creation', 'Tokens Matter'])
            logging.info('Tagged %d cards that modify token creation', modifier_mask.sum())

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info('Completed token tagging in %.2fs', duration)

    except Exception as e:
        logging.error('Error tagging token cards: %s', str(e))
        raise

### Life Matters
def tag_for_life_matters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about life totals, life gain/loss, and related effects using vectorized operations.

    This function coordinates multiple subfunctions to handle different life-related aspects:
    - Lifegain effects and triggers
    - Lifelink and lifelink-like abilities
    - Life loss triggers and effects
    - Food token creation and effects
    - Life-related kindred synergies

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting "Life Matters" tagging for {color}_cards.csv')
    print('\n==========\n')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags', 'type', 'creatureTypes'}
        utility.validate_dataframe_columns(df, required_cols)

        # Process each type of life effect
        tag_for_lifegain(df, color)
        logging.info('Completed lifegain tagging')
        print('\n==========\n')

        tag_for_lifelink(df, color)
        logging.info('Completed lifelink tagging')
        print('\n==========\n')

        tag_for_life_loss(df, color)
        logging.info('Completed life loss tagging')
        print('\n==========\n')

        tag_for_food(df, color)
        logging.info('Completed food token tagging')
        print('\n==========\n')

        tag_for_life_kindred(df, color)
        logging.info('Completed life kindred tagging')
        print('\n==========\n')

        # Log completion and performance metrics
        duration = pd.Timestamp.now() - start_time
        logging.info(f'Completed all "Life Matters" tagging in {duration.total_seconds():.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_life_matters: {str(e)}')
        raise

def tag_for_lifegain(df: pd.DataFrame, color: str) -> None:
    """Tag cards with lifegain effects using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging lifegain effects in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create masks for different lifegain patterns
        gain_patterns = [f'gain {num} life' for num in settings.num_to_search]
        gain_patterns.extend([f'gains {num} life' for num in settings.num_to_search])
        gain_patterns.extend(['gain life', 'gains life'])
        
        gain_mask = utility.create_text_mask(df, gain_patterns)

        # Exclude replacement effects
        replacement_mask = utility.create_text_mask(df, ['if you would gain life', 'whenever you gain life'])
        
        # Apply lifegain tags
        final_mask = gain_mask & ~replacement_mask
        if final_mask.any():
            utility.apply_tag_vectorized(df, final_mask, ['Lifegain', 'Life Matters'])
            logging.info(f'Tagged {final_mask.sum()} cards with lifegain effects')

        # Tag lifegain triggers
        trigger_mask = utility.create_text_mask(df, ['if you would gain life', 'whenever you gain life'])
        if trigger_mask.any():
            utility.apply_tag_vectorized(df, trigger_mask, ['Lifegain', 'Lifegain Triggers', 'Life Matters'])
            logging.info(f'Tagged {trigger_mask.sum()} cards with lifegain triggers')

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Completed lifegain tagging in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging lifegain effects: {str(e)}')
        raise

def tag_for_lifelink(df: pd.DataFrame, color: str) -> None:
    """Tag cards with lifelink and lifelink-like effects using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging lifelink effects in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create masks for different lifelink patterns
        lifelink_mask = utility.create_text_mask(df, 'lifelink')
        lifelike_mask = utility.create_text_mask(df, [
            'deals damage, you gain that much life',
            'loses life.*gain that much life'
        ])

        # Exclude combat damage references for life loss conversion
        damage_mask = utility.create_text_mask(df, 'deals damage')
        life_loss_mask = lifelike_mask & ~damage_mask

        # Combine masks
        final_mask = lifelink_mask | lifelike_mask | life_loss_mask

        # Apply tags
        if final_mask.any():
            utility.apply_tag_vectorized(df, final_mask, ['Lifelink', 'Lifegain', 'Life Matters'])
            logging.info(f'Tagged {final_mask.sum()} cards with lifelink effects')

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Completed lifelink tagging in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging lifelink effects: {str(e)}')
        raise

def tag_for_life_loss(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about life loss using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging life loss effects in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create masks for different life loss patterns
        text_patterns = [
            'you lost life',
            'you gained and lost life',
            'you gained or lost life',
            'you would lose life',
            'you\'ve gained and lost life this turn',
            'you\'ve lost life',
            'whenever you gain or lose life',
            'whenever you lose life'
        ]
        text_mask = utility.create_text_mask(df, text_patterns)

        # Apply tags
        if text_mask.any():
            utility.apply_tag_vectorized(df, text_mask, ['Lifeloss', 'Lifeloss Triggers', 'Life Matters'])
            logging.info(f'Tagged {text_mask.sum()} cards with life loss effects')

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Completed life loss tagging in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging life loss effects: {str(e)}')
        raise

def tag_for_food(df: pd.DataFrame, color: str) -> None:
    """Tag cards that create or care about Food using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging Food token in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create masks for Food tokens
        text_mask = utility.create_text_mask(df, 'food')
        type_mask = utility.create_type_mask(df, 'food')

        # Combine masks
        final_mask = text_mask | type_mask

        # Apply tags
        if final_mask.any():
            utility.apply_tag_vectorized(df, final_mask, ['Food', 'Lifegain', 'Life Matters'])
            logging.info(f'Tagged {final_mask.sum()} cards with Food effects')

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Completed Food tagging in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging Food effects: {str(e)}')
        raise

def tag_for_life_kindred(df: pd.DataFrame, color: str) -> None:
    """Tag cards with life-related kindred synergies using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging life-related kindred effects in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create mask for life-related creature types
        life_tribes = ['Angel', 'Bat', 'Cleric', 'Vampire']
        kindred_mask = df['creatureTypes'].apply(lambda x: any(tribe in x for tribe in life_tribes))

        # Apply tags
        if kindred_mask.any():
            utility.apply_tag_vectorized(df, kindred_mask, ['Lifegain', 'Life Matters'])
            logging.info(f'Tagged {kindred_mask.sum()} cards with life-related kindred effects')

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Completed life kindred tagging in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging life kindred effects: {str(e)}')
        raise

### Counters
def tag_for_counters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about or interact with counters using vectorized operations.

    This function identifies and tags cards that:
    - Add or remove counters (+1/+1, -1/-1, special counters)
    - Care about counters being placed or removed
    - Have counter-based abilities (proliferate, undying, etc)
    - Create or modify counters

    The function maintains proper tag hierarchy and ensures consistent application
    of related tags like 'Counters Matter', '+1/+1 Counters', etc.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting counter-related tagging for {color}_cards.csv')
    print('\n==========\n')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags', 'name', 'creatureTypes'}
        utility.validate_dataframe_columns(df, required_cols)

        # Process each type of counter effect
        tag_for_general_counters(df, color)
        logging.info('Completed general counter tagging')
        print('\n==========\n')

        tag_for_plus_counters(df, color)
        logging.info('Completed +1/+1 counter tagging')
        print('\n==========\n')

        tag_for_minus_counters(df, color)
        logging.info('Completed -1/-1 counter tagging')
        print('\n==========\n')

        tag_for_special_counters(df, color)
        logging.info('Completed special counter tagging')
        print('\n==========\n')

        # Log completion and performance metrics
        duration = pd.Timestamp.now() - start_time
        logging.info(f'Completed all counter-related tagging in {duration.total_seconds():.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_counters: {str(e)}')
        raise

def tag_for_general_counters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about counters in general using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging general counter effects in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create masks for different counter patterns
        text_patterns = [
            'choose a kind of counter',
            'if it had counters',
            'move a counter',
            'one or more counters',
            'proliferate',
            'remove a counter',
            'with counters on them'
        ]
        text_mask = utility.create_text_mask(df, text_patterns)

        # Create mask for specific cards
        specific_cards = [
            'banner of kinship',
            'damning verdict',
            'ozolith'
        ]
        name_mask = utility.create_name_mask(df, specific_cards)

        # Combine masks
        final_mask = text_mask | name_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Counters Matter'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with general counter effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging general counter effects: {str(e)}')
        raise

def tag_for_plus_counters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about +1/+1 counters using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging +1/+1 counter effects in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create text pattern mask
        text_patterns = [
            r'\+1/\+1 counter',
            r'if it had counters',
            r'one or more counters',
            r'one or more \+1/\+1 counter',
            r'proliferate',
            r'undying',
            r'with counters on them'
        ]
        text_mask = utility.create_text_mask(df, text_patterns)
        # Create creature type mask
        type_mask = df['creatureTypes'].apply(lambda x: 'Hydra' in x if isinstance(x, list) else False)

        # Combine masks
        final_mask = text_mask | type_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['+1/+1 Counters', 'Counters Matter', 'Voltron'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with +1/+1 counter effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging +1/+1 counter effects: {str(e)}')
        raise

def tag_for_minus_counters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about -1/-1 counters using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging -1/-1 counter effects in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create text pattern mask
        text_patterns = [
            '-1/-1 counter',
            'if it had counters',
            'infect',
            'one or more counter',
            'one or more -1/-1 counter',
            'persist',
            'proliferate',
            'wither'
        ]
        text_mask = utility.create_text_mask(df, text_patterns)
        
        # Apply tags
        utility.apply_tag_vectorized(df, text_mask, ['-1/-1 Counters', 'Counters Matter'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {text_mask.sum()} cards with -1/-1 counter effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging -1/-1 counter effects: {str(e)}')
        raise

def tag_for_special_counters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about special counters using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging special counter effects in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Process each counter type
        counter_counts = {}
        for counter_type in settings.counter_types:
            # Create pattern for this counter type
            pattern = f'{counter_type} counter'
            mask = utility.create_text_mask(df, pattern)

            if mask.any():
                # Apply tags
                tags = [f'{counter_type} Counters', 'Counters Matter']
                utility.apply_tag_vectorized(df, mask, tags)
                counter_counts[counter_type] = mask.sum()

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        total_cards = sum(counter_counts.values())
        logging.info(f'Tagged {total_cards} cards with special counter effects in {duration:.2f}s')
        for counter_type, count in counter_counts.items():
            if count > 0:
                logging.info(f'  - {counter_type}: {count} cards')

    except Exception as e:
        logging.error(f'Error tagging special counter effects: {str(e)}')
        raise

### Voltron
def create_voltron_commander_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that are Voltron commanders.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are Voltron commanders
    """
    return utility.create_name_mask(df, settings.VOLTRON_COMMANDER_CARDS)

def create_voltron_support_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that support Voltron strategies.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards support Voltron strategies
    """
    return utility.create_text_mask(df, settings.VOLTRON_PATTERNS)

def create_voltron_equipment_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for Equipment-based Voltron cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are Equipment-based Voltron cards
    """
    return utility.create_type_mask(df, 'Equipment')

def create_voltron_aura_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for Aura-based Voltron cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are Aura-based Voltron cards
    """
    return utility.create_type_mask(df, 'Aura')

def tag_for_voltron(df: pd.DataFrame, color: str) -> None:
    """Tag cards that fit the Voltron strategy.

    This function identifies and tags cards that support the Voltron strategy including:
    - Voltron commanders
    - Equipment and Auras
    - Cards that care about equipped/enchanted creatures
    - Cards that enhance single creatures

    The function uses vectorized operations for performance and follows patterns
    established in other tagging functions.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting Voltron strategy tagging for {color}_cards.csv')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags', 'type', 'name'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different Voltron aspects
        commander_mask = create_voltron_commander_mask(df)
        support_mask = create_voltron_support_mask(df)
        equipment_mask = create_voltron_equipment_mask(df)
        aura_mask = create_voltron_aura_mask(df)

        # Combine masks
        final_mask = commander_mask | support_mask | equipment_mask | aura_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Voltron'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with Voltron strategy in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_voltron: {str(e)}')
        raise
        duration = pd.Timestamp.now() - start_time
        logging.info(f'Completed all "Life Matters" tagging in {duration.total_seconds():.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_voltron: {str(e)}')
        raise

### Lands matter
def create_lands_matter_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that care about lands in general.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have lands matter effects
    """
    # Create mask for named cards
    name_mask = utility.create_name_mask(df, settings.LANDS_MATTER_SPECIFIC_CARDS)

    # Create text pattern masks
    play_mask = utility.create_text_mask(df, settings.LANDS_MATTER_PATTERNS['land_play'])
    search_mask = utility.create_text_mask(df, settings.LANDS_MATTER_PATTERNS['land_search']) 
    state_mask = utility.create_text_mask(df, settings.LANDS_MATTER_PATTERNS['land_state'])

    # Combine all masks
    return name_mask | play_mask | search_mask | state_mask

def create_domain_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with domain effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have domain effects
    """
    keyword_mask = utility.create_keyword_mask(df, settings.DOMAIN_PATTERNS['keyword'])
    text_mask = utility.create_text_mask(df, settings.DOMAIN_PATTERNS['text'])
    return keyword_mask | text_mask

def create_landfall_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with landfall triggers.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have landfall effects
    """
    keyword_mask = utility.create_keyword_mask(df, settings.LANDFALL_PATTERNS['keyword'])
    trigger_mask = utility.create_text_mask(df, settings.LANDFALL_PATTERNS['triggers'])
    return keyword_mask | trigger_mask

def create_landwalk_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with landwalk abilities.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have landwalk abilities
    """
    basic_mask = utility.create_text_mask(df, settings.LANDWALK_PATTERNS['basic'])
    nonbasic_mask = utility.create_text_mask(df, settings.LANDWALK_PATTERNS['nonbasic'])
    return basic_mask | nonbasic_mask

def create_land_types_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that care about specific land types.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards care about specific land types
    """
    # Create type-based mask
    type_mask = utility.create_type_mask(df, settings.LAND_TYPES)

    # Create text pattern masks for each land type
    text_masks = []
    for land_type in settings.LAND_TYPES:
        patterns = [
            f'search your library for a {land_type.lower()}',
            f'search your library for up to two {land_type.lower()}',
            f'{land_type} you control'
        ]
        text_masks.append(utility.create_text_mask(df, patterns))

    # Combine all masks
    return type_mask | pd.concat(text_masks, axis=1).any(axis=1)

def tag_for_lands_matter(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about lands using vectorized operations.

    This function identifies and tags cards with land-related effects including:
    - General lands matter effects (searching, playing additional lands, etc)
    - Domain effects
    - Landfall triggers
    - Landwalk abilities
    - Specific land type matters

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting lands matter tagging for {color}_cards.csv')
    print('\n==========\n')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'type', 'name'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different land effects
        lands_mask = create_lands_matter_mask(df)
        domain_mask = create_domain_mask(df)
        landfall_mask = create_landfall_mask(df)
        landwalk_mask = create_landwalk_mask(df)
        types_mask = create_land_types_mask(df)

        # Apply tags based on masks
        if lands_mask.any():
            utility.apply_tag_vectorized(df, lands_mask, ['Lands Matter'])
            logging.info(f'Tagged {lands_mask.sum()} cards with general lands matter effects')

        if domain_mask.any():
            utility.apply_tag_vectorized(df, domain_mask, ['Domain', 'Lands Matter'])
            logging.info(f'Tagged {domain_mask.sum()} cards with domain effects')

        if landfall_mask.any():
            utility.apply_tag_vectorized(df, landfall_mask, ['Landfall', 'Lands Matter'])
            logging.info(f'Tagged {landfall_mask.sum()} cards with landfall effects')

        if landwalk_mask.any():
            utility.apply_tag_vectorized(df, landwalk_mask, ['Landwalk', 'Lands Matter'])
            logging.info(f'Tagged {landwalk_mask.sum()} cards with landwalk abilities')

        if types_mask.any():
            utility.apply_tag_vectorized(df, types_mask, ['Land Types Matter', 'Lands Matter'])
            logging.info(f'Tagged {types_mask.sum()} cards with specific land type effects')

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Completed lands matter tagging in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_lands_matter: {str(e)}')
        raise

### Spells Matter
def create_spellslinger_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with spellslinger text patterns.

    This function identifies cards that care about casting spells through text patterns like:
    - Casting modal spells
    - Casting spells from anywhere
    - Casting instant/sorcery spells
    - Casting noncreature spells
    - First/next spell cast triggers

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have spellslinger text patterns
    """
    text_patterns = [
        'cast a modal',
        'cast a spell from anywhere',
        'cast an instant',
        'cast a noncreature',
        'casts an instant',
        'casts a noncreature',
        'first instant',
        'first spell',
        'next cast an instant',
        'next instant',
        'next spell',
        'second instant',
        'second spell',
        'you cast an instant',
        'you cast a spell'
    ]
    return utility.create_text_mask(df, text_patterns)

def create_spellslinger_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with spellslinger-related keywords.

    This function identifies cards with keywords that indicate they care about casting spells:
    - Magecraft
    - Storm
    - Prowess
    - Surge
    
    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have spellslinger keywords
    """
    keyword_patterns = [
        'Magecraft',
        'Storm',
        'Prowess',
        'Surge'
    ]
    return utility.create_keyword_mask(df, keyword_patterns)

def create_spellslinger_type_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for instant/sorcery type cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are instants or sorceries
    """
    return utility.create_type_mask(df, ['Instant', 'Sorcery'])

def create_spellslinger_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from spellslinger tagging.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    # Add specific exclusion patterns here if needed
    excluded_names = [
        'Possibility Storm',
        'Wild-Magic Sorcerer'
    ]
    return utility.create_name_mask(df, excluded_names)

def tag_for_spellslinger(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about casting spells using vectorized operations.

    This function identifies and tags cards that care about spellcasting including:
    - Cards that trigger off casting spells
    - Instant and sorcery spells
    - Cards with spellslinger-related keywords
    - Cards that care about noncreature spells

    The function maintains proper tag hierarchy and ensures consistent application
    of related tags like 'Spellslinger', 'Spells Matter', etc.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting Spellslinger tagging for {color}_cards.csv')
    print('\n==========\n')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'type', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different spellslinger patterns
        text_mask = create_spellslinger_text_mask(df)
        keyword_mask = create_spellslinger_keyword_mask(df)
        type_mask = create_spellslinger_type_mask(df)
        exclusion_mask = create_spellslinger_exclusion_mask(df)

        # Combine masks
        final_mask = (text_mask | keyword_mask | type_mask) & ~exclusion_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Spellslinger', 'Spells Matter'])
        logging.info(f'Tagged {final_mask.sum()} general Spellslinger cards')
        
        # Run non-generalized tags
        tag_for_storm(df, color)
        tag_for_magecraft(df, color)
        tag_for_cantrips(df, color)
        tag_for_spell_copy(df, color)
        
        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Completed Spellslinger tagging in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_spellslinger: {str(e)}')
        raise

def create_storm_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with storm effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have storm effects
    """
    # Create keyword mask
    keyword_mask = utility.create_keyword_mask(df, 'Storm')

    # Create text mask
    text_patterns = [
        'gain storm',
        'has storm',
        'have storm'
    ]
    text_mask = utility.create_text_mask(df, text_patterns)

    return keyword_mask | text_mask

def tag_for_storm(df: pd.DataFrame, color: str) -> None:
    """Tag cards with storm effects using vectorized operations.

    This function identifies and tags cards that:
    - Have the storm keyword
    - Grant or care about storm

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create storm mask
        storm_mask = create_storm_mask(df)

        # Apply tags
        utility.apply_tag_vectorized(df, storm_mask, ['Storm', 'Spellslinger', 'Spells Matter'])

        # Log results
        storm_count = storm_mask.sum()
        logging.info(f'Tagged {storm_count} cards with Storm effects')

    except Exception as e:
        logging.error(f'Error tagging Storm effects: {str(e)}')
        raise

## Tag for Cantrips
def tag_for_cantrips(df: pd.DataFrame, color: str) -> None:
    """Tag cards in the DataFrame as cantrips based on specific criteria.

    Cantrips are defined as low-cost spells (mana value <= 2) that draw cards.
    The function excludes certain card types, keywords, and specific named cards
    from being tagged as cantrips.

    Args:
        df: The DataFrame containing card data
        color: The color identifier for logging purposes
    """
    try:
        # Convert mana value to numeric
        df['manaValue'] = pd.to_numeric(df['manaValue'], errors='coerce')

        # Create exclusion masks
        excluded_types = utility.create_type_mask(df, 'Land|Equipment')
        excluded_keywords = utility.create_keyword_mask(df, ['Channel', 'Cycling', 'Connive', 'Learn', 'Ravenous'])
        has_loot = df['themeTags'].apply(lambda x: 'Loot' in x)

        # Define name exclusions
        EXCLUDED_NAMES = {
            'Archivist of Oghma', 'Argothian Enchantress', 'Audacity', 'Betrayal', 'Bequeathal', 'Blood Scrivener', 'Brigon, Soldier of Meletis',
            'Compost', 'Concealing curtains // Revealing Eye', 'Cryptbreaker', 'Curiosity', 'Cuse of Vengeance', 'Cryptek', 'Dakra Mystic',
            'Dawn of a New Age', 'Dockside Chef', 'Dreamcatcher', 'Edgewall Innkeeper', 'Eidolon of Philosophy', 'Evolved Sleeper',
            'Femeref Enchantress', 'Finneas, Ace Archer', 'Flumph', 'Folk Hero', 'Frodo, Adventurous Hobbit', 'Goblin Artisans',
            'Goldberry, River-Daughter', 'Gollum, Scheming Guide', 'Hatching Plans', 'Ideas Unbound', 'Ingenius Prodigy', 'Ior Ruin Expedition',
            "Jace's Erasure", 'Keeper of the Mind', 'Kor Spiritdancer', 'Lodestone Bauble', 'Puresteel Paladin', 'Jeweled Bird', 'Mindblade Render',
            "Multani's Presence", "Nahiri's Lithoforming", 'Ordeal of Thassa', 'Pollywog Prodigy', 'Priest of Forgotten Gods', 'Ravenous Squirrel',
            'Read the Runes', 'Red Death, Shipwrecker', 'Roil Cartographer', 'Sage of Lat-Name', 'Saprazzan Heir', 'Scion of Halaster', 'See Beyond',
            'Selhoff Entomber', 'Shielded Aether Theif', 'Shore Keeper', 'silverquill Silencer', 'Soldevi Sage', 'Soldevi Sentry', 'Spiritual Focus',
            'Sram, Senior Edificer', 'Staff of the Storyteller', 'Stirge', 'Sylvan Echoes', "Sythis Harvest's Hand", 'Sygg, River Cutthroat',
            'Tenuous Truce', 'Test of Talents', 'Thalakos seer', "Tribute to Horobi // Echo of Deaths Wail", 'Vampire Gourmand', 'Vampiric Rites',
            'Vampirism', 'Vessel of Paramnesia', "Witch's Caultron", 'Wall of Mulch', 'Waste Not', 'Well Rested'
            # Add other excluded names here
        }
        excluded_names = df['name'].isin(EXCLUDED_NAMES)

        # Create cantrip condition masks
        has_draw = utility.create_text_mask(df, PATTERN_GROUPS['draw'])
        low_cost = df['manaValue'].fillna(float('inf')) <= 2

        # Combine conditions
        cantrip_mask = (
            ~excluded_types &
            ~excluded_keywords &
            ~has_loot &
            ~excluded_names &
            has_draw &
            low_cost
        )

        # Apply tags
        utility.apply_tag_vectorized(df, cantrip_mask, TAG_GROUPS['Cantrips'])

        # Log results
        cantrip_count = cantrip_mask.sum()
        logging.info(f'Tagged {cantrip_count} Cantrip cards')

    except Exception as e:
        logging.error('Error tagging Cantrips in %s_cards.csv: %s', color, str(e))
        raise


def create_magecraft_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with magecraft effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have magecraft effects
    """
    return utility.create_keyword_mask(df, 'Magecraft')

def tag_for_magecraft(df: pd.DataFrame, color: str) -> None:
    """Tag cards with magecraft using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        # Validate required columns
        required_cols = {'themeTags', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create magecraft mask
        magecraft_mask = create_magecraft_mask(df)

        # Apply tags
        utility.apply_tag_vectorized(df, magecraft_mask, ['Magecraft', 'Spellslinger', 'Spells Matter'])

        # Log results
        magecraft_count = magecraft_mask.sum()
        logging.info(f'Tagged {magecraft_count} cards with Magecraft effects')

    except Exception as e:
        logging.error(f'Error tagging Magecraft effects: {str(e)}')
        raise
    
## Spell Copy
def create_spell_copy_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with spell copy text patterns.

    This function identifies cards that copy spells through text patterns like:
    - Copy target spell
    - Copy that spell
    - Copy the next spell
    - Create copies of spells

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have spell copy text patterns
    """
    text_patterns = [
        'copy a spell',
        'copy it',
        'copy that spell',
        'copy target',
        'copy the next',
        'create a copy',
        'creates a copy'
    ]
    return utility.create_text_mask(df, text_patterns)

def create_spell_copy_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with spell copy related keywords.

    This function identifies cards with keywords that indicate they copy spells:
    - Casualty
    - Conspire
    - Replicate
    - Storm
    
    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have spell copy keywords
    """
    keyword_patterns = [
        'Casualty',
        'Conspire',
        'Replicate',
        'Storm'
    ]
    return utility.create_keyword_mask(df, keyword_patterns)

def tag_for_spell_copy(df: pd.DataFrame, color: str) -> None:
    """Tag cards that copy spells using vectorized operations.

    This function identifies and tags cards that copy spells including:
    - Cards that directly copy spells
    - Cards with copy-related keywords
    - Cards that create copies of spells

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different spell copy patterns
        text_mask = create_spell_copy_text_mask(df)
        keyword_mask = create_spell_copy_keyword_mask(df)

        # Combine masks
        final_mask = text_mask | keyword_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Spell Copy', 'Spellslinger', 'Spells Matter'])

        # Log results
        spellcopy_count = final_mask.sum()
        logging.info(f'Tagged {spellcopy_count} spell copy cards')
    
    except Exception as e:
        logging.error(f'Error in tag_for_spell_copy: {str(e)}')
        raise

### Ramp
def create_mana_dork_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for creatures that produce mana.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are mana dorks
    """
    # Create base creature mask
    creature_mask = utility.create_type_mask(df, 'Creature')

    # Create text pattern masks
    tap_mask = utility.create_text_mask(df, ['{T}: Add', '{T}: Untap'])
    sac_mask = utility.create_text_mask(df, ['creature: add', 'control: add'])

    # Create mana symbol mask
    mana_patterns = [f'add {{{c}}}' for c in ['C', 'W', 'U', 'B', 'R', 'G']]
    mana_mask = utility.create_text_mask(df, mana_patterns)

    # Create specific cards mask
    specific_cards = ['Awaken the Woods', 'Forest Dryad']
    name_mask = utility.create_name_mask(df, specific_cards)

    return creature_mask & (tap_mask | sac_mask | mana_mask) | name_mask

def create_mana_rock_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for artifacts that produce mana.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are mana rocks
    """
    # Create base artifact mask
    artifact_mask = utility.create_type_mask(df, 'Artifact')

    # Create text pattern masks
    tap_mask = utility.create_text_mask(df, ['{T}: Add', '{T}: Untap'])
    sac_mask = utility.create_text_mask(df, ['creature: add', 'control: add'])

    # Create mana symbol mask
    mana_patterns = [f'add {{{c}}}' for c in ['C', 'W', 'U', 'B', 'R', 'G']]
    mana_mask = utility.create_text_mask(df, mana_patterns)

    # Create token mask
    token_mask = utility.create_tag_mask(df, ['Powerstone Tokens', 'Treasure Tokens', 'Gold Tokens']) | \
                 utility.create_text_mask(df, 'token named meteorite')

    return (artifact_mask & (tap_mask | sac_mask | mana_mask)) | token_mask

def create_extra_lands_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that allow playing additional lands.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards allow playing extra lands
    """
    text_patterns = [
        'additional land',
        'play an additional land',
        'play two additional lands',
        'put a land',
        'put all land',
        'put those land',
        'return all land',
        'return target land'
    ]

    return utility.create_text_mask(df, text_patterns)

def create_land_search_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that search for lands.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards search for lands
    """
    # Create basic search patterns
    search_patterns = [
        'search your library for a basic',
        'search your library for a land',
        'search your library for up to',
        'each player searches',
        'put those land'
    ]

    # Create land type specific patterns
    land_types = ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest', 'Wastes']
    for land_type in land_types:
        search_patterns.extend([
            f'search your library for a basic {land_type.lower()}',
            f'search your library for a {land_type.lower()}',
            f'search your library for an {land_type.lower()}'
        ])

    return utility.create_text_mask(df, search_patterns)

def tag_for_ramp(df: pd.DataFrame, color: str) -> None:
    """Tag cards that provide mana acceleration using vectorized operations.

    This function identifies and tags cards that provide mana acceleration through:
    - Mana dorks (creatures that produce mana)
    - Mana rocks (artifacts that produce mana)
    - Extra land effects
    - Land search effects

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting ramp tagging for {color}_cards.csv')
    print('\n==========\n')

    try:
        # Create masks for different ramp categories
        dork_mask = create_mana_dork_mask(df)
        rock_mask = create_mana_rock_mask(df)
        lands_mask = create_extra_lands_mask(df)
        search_mask = create_land_search_mask(df)

        # Apply tags for each category
        if dork_mask.any():
            utility.apply_tag_vectorized(df, dork_mask, ['Mana Dork', 'Ramp'])
            logging.info(f'Tagged {dork_mask.sum()} mana dork cards')

        if rock_mask.any():
            utility.apply_tag_vectorized(df, rock_mask, ['Mana Rock', 'Ramp'])
            logging.info(f'Tagged {rock_mask.sum()} mana rock cards')

        if lands_mask.any():
            utility.apply_tag_vectorized(df, lands_mask, ['Lands Matter', 'Ramp'])
            logging.info(f'Tagged {lands_mask.sum()} extra lands cards')

        if search_mask.any():
            utility.apply_tag_vectorized(df, search_mask, ['Lands Matter', 'Ramp'])
            logging.info(f'Tagged {search_mask.sum()} land search cards')

        # Log completion
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Completed ramp tagging in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_ramp: {str(e)}')
        raise

### Other Misc Themes
def tag_for_themes(df: pd.DataFrame, color: str) -> None:
    """Tag cards that fit other themes that haven't been done so far.

    This function will call on functions to tag for:
    - Aggo
    - Aristocrats
    - Big Mana
    - Blink
    - Burn
    - Clones
    - Control
    - Energy
    - Infect
    - Legends Matter
    - Little Creatures
    - Mill
    - Monarch
    - Multiple Copy Cards (i.e. Hare Apparent or Dragon's Approach)
    - Superfriends
    - Reanimate
    - Stax
    - Theft
    - Toughess Matters
    - Topdeck
    - X Spells

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting tagging for remaining themes in {color}_cards.csv')
    print('\n===============\n')
    tag_for_aggro(df, color)
    print('\n==========\n')
    tag_for_aristocrats(df, color)
    print('\n==========\n')
    tag_for_big_mana(df, color)
    print('\n==========\n')
    tag_for_blink(df, color)
    print('\n==========\n')
    tag_for_burn(df, color)
    print('\n==========\n')
    tag_for_clones(df, color)
    print('\n==========\n')
    tag_for_control(df, color)
    print('\n==========\n')
    tag_for_energy(df, color)
    print('\n==========\n')
    tag_for_infect(df, color)
    print('\n==========\n')
    tag_for_legends_matter(df, color)
    print('\n==========\n')
    tag_for_little_guys(df, color)
    print('\n==========\n')
    tag_for_mill(df, color)
    print('\n==========\n')
    tag_for_monarch(df, color)
    print('\n==========\n')
    tag_for_multiple_copies(df, color)
    print('\n==========\n')
    tag_for_planeswalkers(df, color)
    print('\n==========\n')
    tag_for_reanimate(df, color)
    print('\n==========\n')
    tag_for_stax(df, color)
    print('\n==========\n')
    tag_for_theft(df, color)
    print('\n==========\n')
    tag_for_toughness(df, color)
    print('\n==========\n')
    tag_for_topdeck(df, color)
    print('\n==========\n')
    tag_for_x_spells(df, color)
    print('\n==========\n')
    
    duration = (pd.Timestamp.now() - start_time).total_seconds()
    logging.info(f'Completed theme tagging in {duration:.2f}s')
    
## Aggro
def create_aggro_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with aggro-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have aggro text patterns
    """
    text_patterns = [
        'a creature attacking',
        'deal combat damage',
        'deals combat damage', 
        'have riot',
        'this creature attacks',
        'whenever you attack',
        'whenever .* attack',
        'whenever .* deals combat',
        'you control attack',
        'you control deals combat',
        'untap all attacking creatures'
    ]
    return utility.create_text_mask(df, text_patterns)

def create_aggro_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with aggro-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have aggro keywords
    """
    keyword_patterns = [
        'Blitz',
        'Deathtouch',
        'Double Strike', 
        'First Strike',
        'Fear',
        'Haste',
        'Menace',
        'Myriad',
        'Prowl',
        'Raid',
        'Shadow',
        'Spectacle',
        'Trample'
    ]
    return utility.create_keyword_mask(df, keyword_patterns)

def create_aggro_theme_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with aggro-related themes.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have aggro themes
    """
    return utility.create_tag_mask(df, ['Voltron'])

def tag_for_aggro(df: pd.DataFrame, color: str) -> None:
    """Tag cards that fit the Aggro theme using vectorized operations.

    This function identifies and tags cards that support aggressive strategies including:
    - Cards that care about attacking
    - Cards with combat-related keywords
    - Cards that deal combat damage
    - Cards that support Voltron strategies

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting Aggro strategy tagging for {color}_cards.csv')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different aggro aspects
        text_mask = create_aggro_text_mask(df)
        keyword_mask = create_aggro_keyword_mask(df)
        theme_mask = create_aggro_theme_mask(df)

        # Combine masks
        final_mask = text_mask | keyword_mask | theme_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Aggro', 'Combat Matters'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with Aggro strategy in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_aggro: {str(e)}')
        raise


## Aristocrats
def create_aristocrat_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with aristocrat-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have aristocrat text patterns
    """
    return utility.create_text_mask(df, settings.ARISTOCRAT_TEXT_PATTERNS)

def create_aristocrat_name_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for specific aristocrat-related cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are specific aristocrat cards
    """
    return utility.create_name_mask(df, settings.ARISTOCRAT_SPECIFIC_CARDS)

def create_aristocrat_self_sacrifice_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for creatures with self-sacrifice effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which creatures have self-sacrifice effects
    """
    # Create base creature mask
    creature_mask = utility.create_type_mask(df, 'Creature')
    
    # Create name-based patterns
    def check_self_sacrifice(row):
        if pd.isna(row['text']) or pd.isna(row['name']):
            return False
        name = row['name'].lower()
        text = row['text'].lower()
        return f'sacrifice {name}' in text or f'when {name} dies' in text
    
    # Apply patterns to creature cards
    return creature_mask & df.apply(check_self_sacrifice, axis=1)

def create_aristocrat_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with aristocrat-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have aristocrat keywords
    """
    return utility.create_keyword_mask(df, 'Blitz')

def create_aristocrat_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from aristocrat effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    return utility.create_text_mask(df, settings.ARISTOCRAT_EXCLUSION_PATTERNS)

def tag_for_aristocrats(df: pd.DataFrame, color: str) -> None:
    """Tag cards that fit the Aristocrats or Sacrifice Matters themes using vectorized operations.

    This function identifies and tags cards that care about sacrificing permanents or creatures dying, including:
    - Cards with sacrifice abilities or triggers
    - Cards that care about creatures dying
    - Cards with self-sacrifice effects
    - Cards with Blitz or similar mechanics

    The function uses efficient vectorized operations and separate mask creation functions
    for different aspects of the aristocrats theme. It handles:
    - Text-based patterns for sacrifice and death triggers
    - Specific named cards known for aristocrats strategies
    - Self-sacrifice effects on creatures
    - Relevant keywords like Blitz
    - Proper exclusions to avoid false positives

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting aristocrats effect tagging for {color}_cards.csv')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'name', 'type', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different aristocrat patterns
        text_mask = create_aristocrat_text_mask(df)
        name_mask = create_aristocrat_name_mask(df)
        self_sacrifice_mask = create_aristocrat_self_sacrifice_mask(df)
        keyword_mask = create_aristocrat_keyword_mask(df)
        exclusion_mask = create_aristocrat_exclusion_mask(df)

        # Combine masks
        final_mask = (text_mask | name_mask | self_sacrifice_mask | keyword_mask) & ~exclusion_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Aristocrats', 'Sacrifice Matters'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with aristocrats effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_aristocrats: {str(e)}')
        raise


## Big Mana
def create_big_mana_cost_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with high mana costs or X costs.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have high/X mana costs
    """
    # High mana value mask
    high_cost = df['manaValue'].fillna(0).astype(float) >= 5
    
    # X cost mask
    x_cost = df['manaCost'].fillna('').str.contains('{X}', case=False, regex=False)
    
    return high_cost | x_cost

def tag_for_big_mana(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about or generate large amounts of mana using vectorized operations.

    This function identifies and tags cards that:
    - Have high mana costs (5 or greater)
    - Care about high mana values or power
    - Generate large amounts of mana
    - Have X costs
    - Have keywords related to mana generation

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting big mana tagging for {color}_cards.csv')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags', 'manaValue', 'manaCost', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different big mana patterns
        text_mask = utility.create_text_mask(df, settings.BIG_MANA_TEXT_PATTERNS)
        keyword_mask = utility.create_keyword_mask(df, settings.BIG_MANA_KEYWORDS)
        cost_mask = create_big_mana_cost_mask(df)
        specific_mask = utility.create_name_mask(df, settings.BIG_MANA_SPECIFIC_CARDS)
        tag_mask = utility.create_tag_mask(df, 'Cost Reduction')

        # Combine all masks
        final_mask = text_mask | keyword_mask | cost_mask | specific_mask | tag_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Big Mana'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with big mana effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_big_mana: {str(e)}')
        raise

## Blink
def create_etb_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with enter-the-battlefield effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have ETB effects
    """
    text_patterns = [
        'creature entering causes',
        'permanent entering the battlefield',
        'permanent you control enters',
        'whenever another creature enters',
        'whenever another nontoken creature enters',
        'when this creature enters',
        'whenever this creature enters'
    ]
    return utility.create_text_mask(df, text_patterns)

def create_ltb_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with leave-the-battlefield effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have LTB effects
    """
    text_patterns = [
        'when this creature leaves',
        'whenever this creature leaves'
    ]
    return utility.create_text_mask(df, text_patterns)

def create_blink_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with blink/flicker text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have blink/flicker effects
    """
    text_patterns = [
        'exile any number of other',
        'exile one or more cards from your hand',
        'permanent you control, then return',
        'permanents you control, then return',
        'return it to the battlefield',
        'return that card to the battlefield',
        'return them to the battlefield',
        'return those cards to the battlefield',
        'triggered ability of a permanent'
    ]
    return utility.create_text_mask(df, text_patterns)

def tag_for_blink(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have blink/flicker effects using vectorized operations.

    This function identifies and tags cards with blink/flicker effects including:
    - Enter-the-battlefield (ETB) triggers
    - Leave-the-battlefield (LTB) triggers
    - Exile and return effects
    - Permanent flicker effects

    The function maintains proper tag hierarchy and ensures consistent application
    of related tags like 'Blink', 'Enter the Battlefield', and 'Leave the Battlefield'.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting blink/flicker effect tagging for {color}_cards.csv')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags', 'name'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different blink patterns
        etb_mask = create_etb_mask(df)
        ltb_mask = create_ltb_mask(df)
        blink_mask = create_blink_text_mask(df)

        # Create name-based masks
        name_patterns = df.apply(
            lambda row: f'when {row["name"]} enters|whenever {row["name"]} enters|when {row["name"]} leaves|whenever {row["name"]} leaves',
            axis=1
        )
        name_mask = df.apply(
            lambda row: bool(re.search(name_patterns[row.name], row['text'], re.IGNORECASE)) if pd.notna(row['text']) else False,
            axis=1
        )

        # Combine all masks
        final_mask = etb_mask | ltb_mask | blink_mask | name_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Blink', 'Enter the Battlefield', 'Leave the Battlefield'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with blink/flicker effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_blink: {str(e)}')
        raise

## Burn
def create_burn_damage_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with damage-dealing effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have damage effects
    """
    # Create damage number patterns using list comprehension
    damage_patterns = [f'deals {i} damage' for i in range(1, 101)] + ['deals x damage']
    damage_mask = utility.create_text_mask(df, damage_patterns)

    # Create general damage trigger patterns
    trigger_patterns = [
        'deals combat damage',
        'deals damage',
        'deals noncombat damage', 
        'deals that much damage',
        'excess damage',
        'excess noncombat damage',
        'would deal an amount of noncombat damage',
        'would deal damage',
        'would deal noncombat damage'
    ]
    trigger_mask = utility.create_text_mask(df, trigger_patterns)

    # Create pinger patterns
    pinger_patterns = ['deals 1 damage', 'exactly 1 damage']
    pinger_mask = utility.create_text_mask(df, pinger_patterns)

    return damage_mask | trigger_mask | pinger_mask

def create_burn_life_loss_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with life loss effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have life loss effects
    """
    # Create life loss number patterns
    life_patterns = [f'lose {i} life' for i in range(1, 101)]
    life_patterns.extend([f'loses {i} life' for i in range(1, 101)])
    life_patterns.append('lose x life')
    life_patterns.append('loses x life')
    life_mask = utility.create_text_mask(df, life_patterns)

    # Create general life loss trigger patterns 
    trigger_patterns = [
        'each 1 life',
        'loses that much life',
        'opponent lost life',
        'opponent loses life', 
        'player loses life',
        'unspent mana causes that player to lose that much life',
        'would lose life'
    ]
    trigger_mask = utility.create_text_mask(df, trigger_patterns)

    return life_mask | trigger_mask

def create_burn_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with burn-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have burn keywords
    """
    keyword_patterns = ['Bloodthirst', 'Spectacle']
    return utility.create_keyword_mask(df, keyword_patterns)

def create_burn_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from burn effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    # Add specific exclusion patterns here if needed
    return pd.Series(False, index=df.index)

def tag_for_burn(df: pd.DataFrame, color: str) -> None:
    """Tag cards that deal damage or cause life loss using vectorized operations.

    This function identifies and tags cards with burn effects including:
    - Direct damage dealing
    - Life loss effects
    - Burn-related keywords (Bloodthirst, Spectacle)
    - Pinger effects (1 damage)

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting burn effect tagging for {color}_cards.csv')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different burn patterns
        damage_mask = create_burn_damage_mask(df)
        life_mask = create_burn_life_loss_mask(df)
        keyword_mask = create_burn_keyword_mask(df)
        exclusion_mask = create_burn_exclusion_mask(df)

        # Combine masks
        burn_mask = (damage_mask | life_mask | keyword_mask) & ~exclusion_mask
        pinger_mask = utility.create_text_mask(df, ['deals 1 damage', 'exactly 1 damage', 'loses 1 life'])

        # Apply tags
        utility.apply_tag_vectorized(df, burn_mask, ['Burn'])
        utility.apply_tag_vectorized(df, pinger_mask & ~exclusion_mask, ['Pingers'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {burn_mask.sum()} cards with burn effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_burn: {str(e)}')
        raise

## Clones
def create_clone_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with clone-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have clone text patterns
    """
    text_patterns = [
        'a copy of a creature',
        'a copy of an aura',
        'a copy of a permanent',
        'a token that\'s a copy of',
        'as a copy of',
        'becomes a copy of',
        '"legend rule" doesn\'t apply',
        'twice that many of those tokens'
    ]
    return utility.create_text_mask(df, text_patterns)

def create_clone_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with clone-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have clone keywords
    """
    return utility.create_keyword_mask(df, 'Myriad')

def create_clone_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from clone effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    # Add specific exclusion patterns here if needed
    return pd.Series(False, index=df.index)

def tag_for_clones(df: pd.DataFrame, color: str) -> None:
    """Tag cards that create copies or have clone effects using vectorized operations.

    This function identifies and tags cards that:
    - Create copies of creatures or permanents
    - Have copy-related keywords like Myriad
    - Ignore the legend rule
    - Double token creation

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting clone effect tagging for {color}_cards.csv')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different clone patterns
        text_mask = create_clone_text_mask(df)
        keyword_mask = create_clone_keyword_mask(df)
        exclusion_mask = create_clone_exclusion_mask(df)

        # Combine masks
        final_mask = (text_mask | keyword_mask) & ~exclusion_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Clones'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with clone effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_clones: {str(e)}')
        raise

## Control
def create_control_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with control-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have control text patterns
    """
    text_patterns = [
        'a player casts',
        'can\'t attack you',
        'cast your first spell during each opponent\'s turn', 
        'choose new target',
        'choose target opponent',
        'counter target',
        'of an opponent\'s choice',
        'opponent cast',
        'return target',
        'tap an untapped creature',
        'your opponents cast'
    ]
    return utility.create_text_mask(df, text_patterns)

def create_control_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with control-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have control keywords
    """
    keyword_patterns = ['Council\'s dilemma']
    return utility.create_keyword_mask(df, keyword_patterns)

def create_control_specific_cards_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for specific control-related cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are specific control cards
    """
    specific_cards = [
        'Azor\'s Elocutors',
        'Baral, Chief of Compliance',
        'Dragonlord Ojutai',
        'Grand Arbiter Augustin IV',
        'Lavinia, Azorius Renegade',
        'Talrand, Sky Summoner'
    ]
    return utility.create_name_mask(df, specific_cards)

def tag_for_control(df: pd.DataFrame, color: str) -> None:
    """Tag cards that fit the Control theme using vectorized operations.

    This function identifies and tags cards that control the game through:
    - Counter magic
    - Bounce effects
    - Tap effects
    - Opponent restrictions
    - Council's dilemma effects

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting control effect tagging for {color}_cards.csv')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'keywords', 'name'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different control patterns
        text_mask = create_control_text_mask(df)
        keyword_mask = create_control_keyword_mask(df)
        specific_mask = create_control_specific_cards_mask(df)

        # Combine masks
        final_mask = text_mask | keyword_mask | specific_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Control'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with control effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_control: {str(e)}')
        raise

## Energy
def tag_for_energy(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about energy counters using vectorized operations.

    This function identifies and tags cards that:
    - Use energy counters ({E})
    - Care about energy counters
    - Generate or spend energy

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting energy counter tagging for {color}_cards.csv')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create mask for energy text
        energy_mask = df['text'].str.contains('{e}', case=False, na=False)

        # Apply tags
        utility.apply_tag_vectorized(df, energy_mask, ['Energy'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {energy_mask.sum()} cards with energy effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_energy: {str(e)}')
        raise

## Infect
def create_infect_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with infect-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have infect text patterns
    """
    text_patterns = [
        'one or more counter',
        'poison counter', 
        'toxic [1-10]',
    ]
    return utility.create_text_mask(df, text_patterns)

def create_infect_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with infect-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have infect keywords
    """
    keyword_patterns = [
        'Infect',
        'Proliferate', 
        'Toxic',
    ]
    return utility.create_keyword_mask(df, keyword_patterns)

def create_infect_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from infect effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    # Add specific exclusion patterns here if needed
    return pd.Series(False, index=df.index)

def tag_for_infect(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have infect-related effects using vectorized operations.

    This function identifies and tags cards with infect effects including:
    - Infect keyword ability
    - Toxic keyword ability 
    - Proliferate mechanic
    - Poison counter effects

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting infect effect tagging for {color}_cards.csv')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different infect patterns
        text_mask = create_infect_text_mask(df)
        keyword_mask = create_infect_keyword_mask(df)
        exclusion_mask = create_infect_exclusion_mask(df)

        # Combine masks
        final_mask = (text_mask | keyword_mask) & ~exclusion_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Infect'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with infect effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_infect: {str(e)}')
        raise

## Legends Matter
def create_legends_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with legendary/historic text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have legendary/historic text patterns
    """
    text_patterns = [
        'a legendary creature',
        'another legendary',
        'cast a historic',
        'cast a legendary', 
        'cast legendary',
        'equip legendary',
        'historic cards',
        'historic creature',
        'historic permanent',
        'historic spells',
        'legendary creature you control',
        'legendary creatures you control',
        'legendary permanents',
        'legendary spells you',
        'number of legendary',
        'other legendary',
        'play a historic',
        'play a legendary',
        'target legendary',
        'the "legend rule" doesn\'t'
    ]
    return utility.create_text_mask(df, text_patterns)

def create_legends_type_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with Legendary in their type line.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are Legendary
    """
    return utility.create_type_mask(df, 'Legendary')

def tag_for_legends_matter(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about legendary permanents using vectorized operations.

    This function identifies and tags cards that:
    - Are legendary permanents
    - Care about legendary permanents
    - Care about historic spells/permanents
    - Modify the legend rule

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting legendary/historic tagging for {color}_cards.csv')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'type'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different legendary patterns
        text_mask = create_legends_text_mask(df)
        type_mask = create_legends_type_mask(df)

        # Combine masks
        final_mask = text_mask | type_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Historics Matter', 'Legends Matter'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with legendary/historic effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_legends_matter: {str(e)}')
        raise

## Little Fellas
def create_little_guys_power_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for creatures with power 2 or less.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have power 2 or less
    """
    # Create mask for valid power values
    valid_power = pd.to_numeric(df['power'], errors='coerce')
    
    # Create mask for power <= 2
    return (valid_power <= 2) & pd.notna(valid_power)

def tag_for_little_guys(df: pd.DataFrame, color: str) -> None:
    """Tag cards that are or care about low-power creatures using vectorized operations.

    This function identifies and tags:
    - Creatures with power 2 or less
    - Cards that care about creatures with low power
    - Cards that reference power thresholds of 2 or less

    The function handles edge cases like '*' in power values and maintains proper
    tag hierarchy.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting low-power creature tagging for {color}_cards.csv')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'power', 'text', 'themeTags'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different patterns
        power_mask = create_little_guys_power_mask(df)
        text_mask = utility.create_text_mask(df, 'power 2 or less')

        # Combine masks
        final_mask = power_mask | text_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Little Fellas'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with Little Fellas in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_little_guys: {str(e)}')
        raise

## Mill
def create_mill_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with mill-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have mill text patterns
    """
    # Create text pattern masks
    text_patterns = [
        'descended',
        'from a graveyard',
        'from your graveyard', 
        'in your graveyard',
        'into his or her graveyard',
        'into their graveyard',
        'into your graveyard',
        'mills that many cards',
        'opponent\'s graveyard',
        'put into a graveyard',
        'put into an opponent\'s graveyard', 
        'put into your graveyard',
        'rad counter',
        'surveil',
        'would mill'
    ]
    text_mask = utility.create_text_mask(df, text_patterns)

    # Create mill number patterns
    mill_patterns = [f'mill {num}' for num in settings.num_to_search]
    mill_patterns.extend([f'mills {num}' for num in settings.num_to_search])
    number_mask = utility.create_text_mask(df, mill_patterns)

    return text_mask | number_mask

def create_mill_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with mill-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have mill keywords
    """
    keyword_patterns = ['Descend', 'Mill', 'Surveil']
    return utility.create_keyword_mask(df, keyword_patterns)

def tag_for_mill(df: pd.DataFrame, color: str) -> None:
    """Tag cards that mill cards or care about milling using vectorized operations.

    This function identifies and tags cards with mill effects including:
    - Direct mill effects (putting cards from library to graveyard)
    - Mill-related keywords (Descend, Mill, Surveil)
    - Cards that care about graveyards
    - Cards that track milled cards

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting mill effect tagging for {color}_cards.csv')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different mill patterns
        text_mask = create_mill_text_mask(df)
        keyword_mask = create_mill_keyword_mask(df)

        # Combine masks
        final_mask = text_mask | keyword_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Mill'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with mill effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_mill: {str(e)}')
        raise

def tag_for_monarch(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about the monarch mechanic using vectorized operations.

    This function identifies and tags cards that interact with the monarch mechanic, including:
    - Cards that make you become the monarch
    - Cards that prevent becoming the monarch
    - Cards with monarch-related triggers
    - Cards with the monarch keyword

    The function uses vectorized operations for performance and follows patterns
    established in other tagging functions.

    Args:
        df: DataFrame containing card data with text and keyword columns
        color: Color identifier for logging purposes (e.g. 'white', 'blue')

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting monarch mechanic tagging for {color}_cards.csv')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create text pattern mask
        text_patterns = [
            'becomes? the monarch',
            'can\'t become the monarch',
            'is the monarch',
            'was the monarch', 
            'you are the monarch',
            'you become the monarch',
            'you can\'t become the monarch',
            'you\'re the monarch'
        ]
        text_mask = utility.create_text_mask(df, text_patterns)

        # Create keyword mask
        keyword_mask = utility.create_keyword_mask(df, 'Monarch')

        # Combine masks
        final_mask = text_mask | keyword_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Monarch'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with monarch effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_monarch: {str(e)}')
        raise

## Multi-copy cards
def tag_for_multiple_copies(df: pd.DataFrame, color: str) -> None:
    """Tag cards that allow having multiple copies in a deck using vectorized operations.

    This function identifies and tags cards that can have more than 4 copies in a deck,
    like Seven Dwarves or Persistent Petitioners. It uses the multiple_copy_cards list
    from settings to identify these cards.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting multiple copies tagging for {color}_cards.csv')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'name', 'themeTags'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create mask for multiple copy cards
        multiple_copies_mask = utility.create_name_mask(df, multiple_copy_cards)

        # Apply tags
        if multiple_copies_mask.any():
            # Get matching card names
            matching_cards = df[multiple_copies_mask]['name'].unique()
            
            # Apply base tag
            utility.apply_tag_vectorized(df, multiple_copies_mask, ['Multiple Copies'])
            
            # Apply individual card name tags
            for card_name in matching_cards:
                card_mask = df['name'] == card_name
                utility.apply_tag_vectorized(df, card_mask, [card_name])

            logging.info(f'Tagged {multiple_copies_mask.sum()} cards with multiple copies effects')

        # Log completion
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Completed multiple copies tagging in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_multiple_copies: {str(e)}')
        raise

## Planeswalkers
def create_planeswalker_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with planeswalker-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have planeswalker text patterns
    """
    text_patterns = [
        'a planeswalker',
        'affinity for planeswalker',
        'enchant planeswalker',
        'historic permanent',
        'legendary permanent', 
        'loyalty ability',
        'one or more counter',
        'planeswalker spells',
        'planeswalker type'
    ]
    return utility.create_text_mask(df, text_patterns)

def create_planeswalker_type_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with Planeswalker type.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are Planeswalkers
    """
    return utility.create_type_mask(df, 'Planeswalker')

def create_planeswalker_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with planeswalker-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have planeswalker keywords
    """
    return utility.create_keyword_mask(df, 'Proliferate')

def tag_for_planeswalkers(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about planeswalkers using vectorized operations.

    This function identifies and tags cards that:
    - Are planeswalker cards
    - Care about planeswalkers
    - Have planeswalker-related keywords like Proliferate
    - Interact with loyalty abilities

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting planeswalker tagging for {color}_cards.csv')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags', 'type', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different planeswalker patterns
        text_mask = create_planeswalker_text_mask(df)
        type_mask = create_planeswalker_type_mask(df)
        keyword_mask = create_planeswalker_keyword_mask(df)

        # Combine masks
        final_mask = text_mask | type_mask | keyword_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Planeswalkers', 'Super Friends'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with planeswalker effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_planeswalkers: {str(e)}')
        raise

## Reanimator
def create_reanimator_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with reanimator-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have reanimator text patterns
    """
    text_patterns = [
        'descended',
        'discard your hand',
        'from a graveyard',
        'in a graveyard',
        'into a graveyard', 
        'leave a graveyard',
        'in your graveyard',
        'into your graveyard',
        'leave your graveyard'
    ]
    return utility.create_text_mask(df, text_patterns)

def create_reanimator_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with reanimator-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have reanimator keywords
    """
    keyword_patterns = [
        'Blitz',
        'Connive', 
        'Descend',
        'Escape',
        'Flashback',
        'Mill'
    ]
    return utility.create_keyword_mask(df, keyword_patterns)

def create_reanimator_type_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with reanimator-related creature types.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have reanimator creature types
    """
    return df['creatureTypes'].apply(lambda x: 'Zombie' in x if isinstance(x, list) else False)

def tag_for_reanimate(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about graveyard recursion using vectorized operations.

    This function identifies and tags cards with reanimator effects including:
    - Cards that interact with graveyards
    - Cards with reanimator-related keywords (Blitz, Connive, etc)
    - Cards that loot or mill
    - Zombie tribal synergies

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting reanimator effect tagging for {color}_cards.csv')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'keywords', 'creatureTypes'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different reanimator patterns
        text_mask = create_reanimator_text_mask(df)
        keyword_mask = create_reanimator_keyword_mask(df)
        type_mask = create_reanimator_type_mask(df)

        # Combine masks
        final_mask = text_mask | keyword_mask | type_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Reanimate'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with reanimator effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_reanimate: {str(e)}')
        raise

## Stax
def create_stax_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with stax-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have stax text patterns
    """
    return utility.create_text_mask(df, settings.STAX_TEXT_PATTERNS)

def create_stax_name_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards used in stax strategies.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have stax text patterns
    """
    return utility.create_text_mask(df, settings.STAX_SPECIFIC_CARDS)

def create_stax_tag_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with stax-related tags.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have stax tags
    """
    return utility.create_tag_mask(df, 'Control')

def create_stax_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from stax effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    # Add specific exclusion patterns here if needed
    return utility.create_text_mask(df, settings.STAX_EXCLUSION_PATTERNS)

def tag_for_stax(df: pd.DataFrame, color: str) -> None:
    """Tag cards that fit the Stax theme using vectorized operations.

    This function identifies and tags cards that restrict or tax opponents including:
    - Cards that prevent actions (can't attack, can't cast, etc)
    - Cards that tax actions (spells cost more)
    - Cards that control opponents' resources
    - Cards that create asymmetric effects

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting stax effect tagging for {color}_cards.csv')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different stax patterns
        text_mask = create_stax_text_mask(df)
        name_mask = create_stax_name_mask(df)
        tag_mask = create_stax_tag_mask(df)
        exclusion_mask = create_stax_exclusion_mask(df)

        # Combine masks
        final_mask = (text_mask | tag_mask | name_mask) & ~exclusion_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Stax'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with stax effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_stax: {str(e)}')
        raise

## Theft
def create_theft_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with theft-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have theft text patterns
    """
    return utility.create_text_mask(df, settings.THEFT_TEXT_PATTERNS)

def create_theft_name_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for specific theft-related cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are specific theft cards
    """
    return utility.create_name_mask(df, settings.THEFT_SPECIFIC_CARDS)

def tag_for_theft(df: pd.DataFrame, color: str) -> None:
    """Tag cards that steal or use opponents' resources using vectorized operations.

    This function identifies and tags cards that:
    - Cast spells owned by other players
    - Take control of permanents
    - Use opponents' libraries
    - Create theft-related effects

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting theft effect tagging for {color}_cards.csv')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'name'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different theft patterns
        text_mask = create_theft_text_mask(df)
        name_mask = create_theft_name_mask(df)

        # Combine masks
        final_mask = text_mask | name_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Theft'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with theft effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_theft: {str(e)}')
        raise
    
## Toughness Matters
def create_toughness_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with toughness-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have toughness text patterns
    """
    text_patterns = [
        'card\'s toughness',
        'creature\'s toughness',
        'damage equal to its toughness',
        'lesser toughness',
        'total toughness',
        'toughness greater',
        'with defender'
    ]
    return utility.create_text_mask(df, text_patterns)

def create_toughness_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with toughness-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have toughness keywords
    """
    return utility.create_keyword_mask(df, 'Defender')

def _is_valid_numeric_comparison(power: Union[int, str, None], toughness: Union[int, str, None]) -> bool:
    """Check if power and toughness values allow valid numeric comparison.

    Args:
        power: Power value to check
        toughness: Toughness value to check

    Returns:
        True if values can be compared numerically, False otherwise
    """
    try:
        if power is None or toughness is None:
            return False
        power_val = int(power)
        toughness_val = int(toughness)
        return True
    except (ValueError, TypeError):
        return False

def create_power_toughness_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards where toughness exceeds power.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have toughness > power
    """
    valid_comparison = df.apply(
        lambda row: _is_valid_numeric_comparison(row['power'], row['toughness']),
        axis=1
    )
    numeric_mask = valid_comparison & (pd.to_numeric(df['toughness'], errors='coerce') > 
                                     pd.to_numeric(df['power'], errors='coerce'))
    return numeric_mask

def tag_for_toughness(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about toughness using vectorized operations.

    This function identifies and tags cards that:
    - Reference toughness in their text
    - Have the Defender keyword
    - Have toughness greater than power
    - Care about high toughness values

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting toughness tagging for {color}_cards.csv')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'keywords', 'power', 'toughness'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different toughness patterns
        text_mask = create_toughness_text_mask(df)
        keyword_mask = create_toughness_keyword_mask(df)
        power_toughness_mask = create_power_toughness_mask(df)

        # Combine masks
        final_mask = text_mask | keyword_mask | power_toughness_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Toughness Matters'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with toughness effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_toughness: {str(e)}')
        raise

## Topdeck
def create_topdeck_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with topdeck-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have topdeck text patterns
    """
    return utility.create_text_mask(df, settings.TOPDECK_TEXT_PATTERNS)

def create_topdeck_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with topdeck-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have topdeck keywords
    """
    return utility.create_keyword_mask(df, settings.TOPDECK_KEYWORDS)

def create_topdeck_specific_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for specific topdeck-related cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are specific topdeck cards
    """
    return utility.create_name_mask(df, settings.TOPDECK_SPECIFIC_CARDS)

def create_topdeck_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from topdeck effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    return utility.create_text_mask(df, settings.TOPDECK_EXCLUSION_PATTERNS)

def tag_for_topdeck(df: pd.DataFrame, color: str) -> None:
    """Tag cards that manipulate the top of library using vectorized operations.

    This function identifies and tags cards that interact with the top of the library including:
    - Cards that look at or reveal top cards
    - Cards with scry or surveil effects
    - Cards with miracle or similar mechanics
    - Cards that care about the order of the library

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting topdeck effect tagging for {color}_cards.csv')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different topdeck patterns
        text_mask = create_topdeck_text_mask(df)
        keyword_mask = create_topdeck_keyword_mask(df)
        specific_mask = create_topdeck_specific_mask(df)
        exclusion_mask = create_topdeck_exclusion_mask(df)

        # Combine masks
        final_mask = (text_mask | keyword_mask | specific_mask) & ~exclusion_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Topdeck'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with topdeck effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_topdeck: {str(e)}')
        raise

## X Spells
def create_x_spells_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with X spell-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have X spell text patterns
    """
    text_patterns = [
        'cost {x} less',
        'don\'t lose this',
        'don\'t lose unspent',
        'lose unused mana',
        'unused mana would empty',
        'with {x} in its',
        'you cast cost {1} less',
        'you cast cost {2} less',
        'you cast cost {3} less',
        'you cast cost {4} less',
        'you cast cost {5} less'
    ]
    return utility.create_text_mask(df, text_patterns)

def create_x_spells_mana_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with X in their mana cost.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have X in mana cost
    """
    return df['manaCost'].fillna('').str.contains('{X}', case=True, regex=False)

def tag_for_x_spells(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about X spells using vectorized operations.

    This function identifies and tags cards that:
    - Have X in their mana cost
    - Care about X spells or mana values
    - Have cost reduction effects for X spells
    - Preserve unspent mana

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting X spells tagging for {color}_cards.csv')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'manaCost'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different X spell patterns
        text_mask = create_x_spells_text_mask(df)
        mana_mask = create_x_spells_mana_mask(df)

        # Combine masks
        final_mask = text_mask | mana_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['X Spells'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with X spell effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_x_spells: {str(e)}')
        raise

### Interaction
## Overall tag for interaction group
def tag_for_interaction(df: pd.DataFrame, color: str) -> None:
    """Tag cards that interact with the board state or stack.

    This function coordinates tagging of different interaction types including:
    - Counterspells
    - Board wipes
    - Combat tricks
    - Protection effects
    - Spot removal

    The function maintains proper tag hierarchy and ensures consistent application
    of interaction-related tags.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting interaction effect tagging for {color}_cards.csv')
    print('\n==========\n')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags', 'name', 'type', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Process each type of interaction
        sub_start = pd.Timestamp.now()
        tag_for_counterspells(df, color)
        logging.info(f'Completed counterspell tagging in {(pd.Timestamp.now() - sub_start).total_seconds():.2f}s')
        print('\n==========\n')

        sub_start = pd.Timestamp.now()
        tag_for_board_wipes(df, color)
        logging.info(f'Completed board wipe tagging in {(pd.Timestamp.now() - sub_start).total_seconds():.2f}s')
        print('\n==========\n')

        sub_start = pd.Timestamp.now()
        tag_for_combat_tricks(df, color)
        logging.info(f'Completed combat trick tagging in {(pd.Timestamp.now() - sub_start).total_seconds():.2f}s')
        print('\n==========\n')

        sub_start = pd.Timestamp.now()
        tag_for_protection(df, color)
        logging.info(f'Completed protection tagging in {(pd.Timestamp.now() - sub_start).total_seconds():.2f}s')
        print('\n==========\n')
        
        sub_start = pd.Timestamp.now()
        tag_for_removal(df, color)
        logging.info(f'Completed removal tagging in {(pd.Timestamp.now() - sub_start).total_seconds():.2f}s')
        print('\n==========\n')

        # Log completion and performance metrics
        duration = pd.Timestamp.now() - start_time
        logging.info(f'Completed all interaction tagging in {duration.total_seconds():.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_interaction: {str(e)}')
        raise

## Counterspells
def create_counterspell_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with counterspell text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have counterspell text patterns
    """
    return utility.create_text_mask(df, settings.COUNTERSPELL_TEXT_PATTERNS)

def create_counterspell_specific_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for specific counterspell cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are specific counterspell cards
    """
    return utility.create_name_mask(df, settings.COUNTERSPELL_SPECIFIC_CARDS)

def create_counterspell_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from counterspell effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    return utility.create_text_mask(df, settings.COUNTERSPELL_EXCLUSION_PATTERNS)

def tag_for_counterspells(df: pd.DataFrame, color: str) -> None:
    """Tag cards that counter spells using vectorized operations.

    This function identifies and tags cards that:
    - Counter spells directly
    - Return spells to hand/library
    - Exile spells from the stack
    - Care about countering spells

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting counterspell effect tagging for {color}_cards.csv')

    try:
        # Validate required columns
        required_cols = {'text', 'themeTags', 'name'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different counterspell patterns
        text_mask = create_counterspell_text_mask(df)
        specific_mask = create_counterspell_specific_mask(df)
        exclusion_mask = create_counterspell_exclusion_mask(df)

        # Combine masks
        final_mask = (text_mask | specific_mask) & ~exclusion_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Counterspells', 'Interaction', 'Spellslinger', 'Spells Matter'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with counterspell effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_counterspells: {str(e)}')
        raise

## Board Wipes
def tag_for_board_wipes(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have board wipe effects using vectorized operations.

    This function identifies and tags cards with board wipe effects including:
    - Mass destruction effects (destroy all/each)
    - Mass exile effects (exile all/each)
    - Mass bounce effects (return all/each)
    - Mass sacrifice effects (sacrifice all/each)
    - Mass damage effects (damage to all/each)

    The function uses helper functions to identify different types of board wipes
    and applies tags consistently using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting board wipe effect tagging for {color}_cards.csv')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags', 'name'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different board wipe types
        destroy_mask = utility.create_mass_effect_mask(df, 'mass_destruction')
        exile_mask = utility.create_mass_effect_mask(df, 'mass_exile')
        bounce_mask = utility.create_mass_effect_mask(df, 'mass_bounce')
        sacrifice_mask = utility.create_mass_effect_mask(df, 'mass_sacrifice')
        damage_mask = utility.create_mass_damage_mask(df)

        # Create exclusion mask
        exclusion_mask = utility.create_text_mask(df, settings.BOARD_WIPE_EXCLUSION_PATTERNS)

        # Create specific cards mask
        specific_mask = utility.create_name_mask(df, settings.BOARD_WIPE_SPECIFIC_CARDS)

        # Combine all masks
        final_mask = (
            destroy_mask | exile_mask | bounce_mask | 
            sacrifice_mask | damage_mask | specific_mask
        ) & ~exclusion_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Board Wipes', 'Interaction'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with board wipe effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_board_wipes: {str(e)}')
        raise

    logging.info(f'Completed board wipe tagging for {color}_cards.csv')

## Combat Tricks
def create_combat_tricks_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with combat trick text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have combat trick text patterns
    """
    # Create patterns for power/toughness modifiers
    number_patterns = [str(x) for x in range(11)] + ['X']
    buff_patterns = []
    
    for num in number_patterns:
        # Positive buffs
        buff_patterns.extend([
            fr'gets \+{num}/\+{num}',
            fr'get \+{num}/\+{num}',
            fr'gets \+{num}/\+0',
            fr'get \+{num}/\+0',
            fr'gets \+0/\+{num}',
            fr'get \+0/\+{num}'
        ])
        
        # Negative buffs
        buff_patterns.extend([
            fr'gets -{num}/-{num}',
            fr'get -{num}/-{num}',
            fr'gets -{num}/\+0',
            fr'get -{num}/\+0',
            fr'gets \+0/-{num}',
            fr'get \+0/-{num}'
        ])

    # Other combat trick patterns
    other_patterns = [
        'bolster',
        'double strike',
        'first strike',
        'has base power and toughness',
        'untap all creatures',
        'untap target creature',
        'with base power and toughness'
    ]

    # Combine all patterns
    all_patterns = buff_patterns + other_patterns
    return utility.create_text_mask(df, all_patterns)

def create_combat_tricks_type_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for instant-speed combat tricks.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are instant-speed combat tricks
    """
    return utility.create_type_mask(df, 'Instant')

def create_combat_tricks_flash_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for flash-based combat tricks.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have flash-based combat tricks
    """
    return utility.create_keyword_mask(df, 'Flash')

def create_combat_tricks_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from combat tricks.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    # Specific cards to exclude
    excluded_cards = [
        'Assimilate Essence',
        'Mantle of Leadership',
        'Michiko\'s Reign of Truth // Portrait of Michiko'
    ]
    name_mask = utility.create_name_mask(df, excluded_cards)

    # Text patterns to exclude
    text_patterns = [
        'remains tapped',
        'only as a sorcery'
    ]
    text_mask = utility.create_text_mask(df, text_patterns)

    return name_mask | text_mask

def tag_for_combat_tricks(df: pd.DataFrame, color: str) -> None:
    """Tag cards that function as combat tricks using vectorized operations.

    This function identifies and tags cards that modify combat through:
    - Power/toughness buffs at instant speed
    - Flash creatures and enchantments with combat effects
    - Tap abilities that modify power/toughness
    - Combat-relevant keywords and abilities

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting combat trick tagging for {color}_cards.csv')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags', 'type', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different combat trick patterns
        text_mask = create_combat_tricks_text_mask(df)
        type_mask = create_combat_tricks_type_mask(df)
        flash_mask = create_combat_tricks_flash_mask(df)
        exclusion_mask = create_combat_tricks_exclusion_mask(df)

        # Combine masks
        final_mask = ((text_mask & (type_mask | flash_mask)) | 
                     (flash_mask & utility.create_type_mask(df, 'Enchantment'))) & ~exclusion_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Combat Tricks', 'Interaction'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with combat trick effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_combat_tricks: {str(e)}')
        raise
    
## Protection/Safety spells
def create_protection_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with protection-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have protection text patterns
    """
    text_patterns = [
        'has indestructible',
        'has protection',
        'has shroud',
        'has ward',
        'have indestructible', 
        'have protection',
        'have shroud',
        'have ward',
        'hexproof from',
        'gain hexproof',
        'gain indestructible',
        'gain protection',
        'gain shroud', 
        'gain ward',
        'gains hexproof',
        'gains indestructible',
        'gains protection',
        'gains shroud',
        'gains ward',
        'phases out',
        'protection from'
    ]
    return utility.create_text_mask(df, text_patterns)

def create_protection_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with protection-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have protection keywords
    """
    keyword_patterns = [
        'Hexproof',
        'Indestructible',
        'Protection',
        'Shroud',
        'Ward'
    ]
    return utility.create_keyword_mask(df, keyword_patterns)

def create_protection_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from protection effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    excluded_cards = [
        'Out of Time',
        'The War Doctor'
    ]
    return utility.create_name_mask(df, excluded_cards)

def tag_for_protection(df: pd.DataFrame, color: str) -> None:
    """Tag cards that provide or have protection effects using vectorized operations.

    This function identifies and tags cards with protection effects including:
    - Indestructible
    - Protection from [quality]
    - Hexproof/Shroud
    - Ward
    - Phase out

    The function uses helper functions to identify different types of protection
    and applies tags consistently using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting protection effect tagging for {color}_cards.csv')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different protection patterns
        text_mask = create_protection_text_mask(df)
        keyword_mask = create_protection_keyword_mask(df)
        exclusion_mask = create_protection_exclusion_mask(df)

        # Combine masks
        final_mask = (text_mask | keyword_mask) & ~exclusion_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Protection', 'Interaction'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with protection effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_protection: {str(e)}')
        raise

## Spot removal
def create_removal_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with removal text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have removal text patterns
    """
    return utility.create_text_mask(df, settings.REMOVAL_TEXT_PATTERNS)

def tag_for_removal(df: pd.DataFrame, color: str) -> None:
    """Tag cards that provide spot removal using vectorized operations.

    This function identifies and tags cards that remove permanents through:
    - Destroy effects
    - Exile effects
    - Bounce effects
    - Sacrifice effects
    
    The function uses helper functions to identify different types of removal
    and applies tags consistently using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting removal effect tagging for {color}_cards.csv')

    try:
        # Validate inputs
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")

        # Validate required columns
        required_cols = {'text', 'themeTags', 'keywords'}
        utility.validate_dataframe_columns(df, required_cols)

        # Create masks for different removal patterns
        text_mask = create_removal_text_mask(df)

        # Combine masks
        final_mask = text_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Removal', 'Interaction'])

        # Log results
        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Tagged {final_mask.sum()} cards with removal effects in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error in tag_for_removal: {str(e)}')
        raise


#start_time = pd.Timestamp.now()
#regenerate_csvs_all()
#for color in settings.colors:
#    load_dataframe(color)
#duration = (pd.Timestamp.now() - start_time).total_seconds()
#logging.info(f'Tagged cards in {duration:.2f}s')