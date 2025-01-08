from __future__ import annotations

import logging
import os
import pprint # type: ignore
import re
from typing import Dict, List, Optional, Set, Union

import pandas as pd # type: ignore

import settings
import utility

from settings import artifact_tokens, csv_directory, colors, counter_types, enchantment_tokens, multiple_copy_cards, num_to_search, triggers
from setup import regenerate_csv_by_color


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
        df = pd.read_csv(filepath, converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})

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
    #print('\n====================\n')
    #tag_for_counters(df, color)
    #print('\n====================\n')
    #tag_for_voltron(df, color)
    #print('\n====================\n')
    #tag_for_spellslinger(df, color)
    #print('\n====================\n')
    #tag_for_ramp(df, color)
    #print('\n====================\n')
    #tag_for_themes(df, color)
    #print('\n====================\n')
    #tag_for_interaction(df, color)
    
    # Lastly, sort all theme tags for easier reading
    sort_theme_tags(df, color)
    df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
    #print(df)
    print(f'Tags are done being set on {color}_cards.csv')
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
    print(f'Alphabetically sorting theme tags in {color}_cards.csv.')
    
    df['themeTags'] = df['themeTags'].apply(utility.sort_list)
    
    columns_to_keep = ['name', 'faceName','edhrecRank', 'colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'creatureTypes', 'text', 'power', 'toughness', 'keywords', 'themeTags', 'layout', 'side']
    df = df[columns_to_keep]
    print(f'Theme tags alphabetically sorted in {color}_cards.csv.\n')

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
    logging.info('Tagging cantrips in %s_cards.csv', color)

    try:
        # Convert mana value to numeric
        df['manaValue'] = pd.to_numeric(df['manaValue'], errors='coerce')

        # Create exclusion masks
        excluded_types = utility.create_text_mask(df, 'Land|Equipment')
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

        logging.info('Successfully tagged cantrips in %s_cards.csv', color)

    except Exception as e:
        logging.error('Error tagging cantrips in %s_cards.csv: %s', color, str(e))
        raise

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
        predefined_mask = create_predefined_artifact_mask(df)
        if predefined_mask.any():
            utility.apply_tag_vectorized(df, predefined_mask,
                ['Artifact Tokens', 'Artifacts Matter', 'Token Creation', 'Tokens Matter'])
            logging.info('Tagged %d cards with predefined artifact tokens', predefined_mask.sum())

        # Tag fabricate cards
        fabricate_mask = create_fabricate_mask(df)
        if fabricate_mask.any():
            utility.apply_tag_vectorized(df, fabricate_mask,
                ['Artifact Tokens', 'Artifacts Matter', 'Token Creation', 'Tokens Matter'])
            logging.info('Tagged %d cards with fabricate', fabricate_mask.sum())

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
        'bloodforged battleaxe', 'court of vantress', 'elmar, ulvenwald informant',
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

def create_predefined_artifact_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that create predefined artifact tokens.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards create predefined artifact tokens
    """
    # Create base mask for 'create' text
    # Create text pattern matches
    create_pattern = r'create|put'
    has_create = utility.create_text_mask(df, create_pattern)

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

        token_masks.append(token_mask)

    # Combine all token masks
    return has_create & pd.concat(token_masks, axis=1).any(axis=1)

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
    print('==========\n')
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
    print('==========\n')

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
    - Life-related tribal synergies

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logging.info(f'Starting life-related effect tagging for {color}_cards.csv')

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

        tag_for_food_tokens(df, color)
        logging.info('Completed food token tagging')
        print('\n==========\n')

        tag_for_life_tribal(df, color)
        logging.info('Completed life tribal tagging')
        print('\n==========\n')

        # Log completion and performance metrics
        duration = pd.Timestamp.now() - start_time
        logging.info(f'Completed all life-related tagging in {duration.total_seconds():.2f}s')

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

def tag_for_food_tokens(df: pd.DataFrame, color: str) -> None:
    """Tag cards that create or care about Food tokens using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging Food token effects in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create masks for Food tokens
        text_mask = utility.create_text_mask(df, 'food token')
        type_mask = utility.create_text_mask(df, 'food', column='type')

        # Combine masks
        final_mask = text_mask | type_mask

        # Apply tags
        if final_mask.any():
            utility.apply_tag_vectorized(df, final_mask, ['Food Tokens', 'Lifegain', 'Life Matters'])
            logging.info(f'Tagged {final_mask.sum()} cards with Food token effects')

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Completed Food token tagging in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging Food token effects: {str(e)}')
        raise

def tag_for_life_tribal(df: pd.DataFrame, color: str) -> None:
    """Tag cards with life-related tribal synergies using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logging.info(f'Tagging life-related tribal effects in {color}_cards.csv')
    start_time = pd.Timestamp.now()

    try:
        # Create mask for life-related creature types
        life_tribes = ['Angel', 'Bat', 'Cleric', 'Vampire']
        tribal_mask = df['creatureTypes'].apply(lambda x: any(tribe in x for tribe in life_tribes))

        # Apply tags
        if tribal_mask.any():
            utility.apply_tag_vectorized(df, tribal_mask, ['Lifegain', 'Life Matters'])
            logging.info(f'Tagged {tribal_mask.sum()} cards with life-related tribal effects')

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logging.info(f'Completed life tribal tagging in {duration:.2f}s')

    except Exception as e:
        logging.error(f'Error tagging life tribal effects: {str(e)}')
        raise

# Add to settings.py:
LIFE_RELATED_TAGS = [
    'Food Tokens',
    'Lifegain',
    'Lifegain Triggers', 
    'Life Matters',
    'Lifelink',
    'Lifeloss',
    'Lifeloss Triggers'
]

### Voltron
def tag_for_voltron(df, color):
    # Iterate through each {color}_cards.csv file to find voltron cards
    # Also check for cards that care about auras
    # Tag for voltron
    print(f'Tagging cards in {color}_cards.csv that fit the "Voltron" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if 'Voltron' in row['themeTags']:
            continue
        
        if row['type'] == 'Creature':
            if ('Auras' in theme_tags
                or 'Equipment' in theme_tags):
                tag_type = ['Voltron']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        # Tagging for specifically named cards
        if ('feather, the redeemed' in row['name'].lower()
            or 'kosei, penitent warlord' in row['name'].lower()
            or 'narset, enlightened master' in row['name'].lower()
            or 'rafiq of the many' in row['name'].lower()
            or 'raised by giants' in row['name'].lower()
            or 'rograkh, son of rohgahh' in row['name'].lower()
            or 'skullbriar, the walking grave' in row['name'].lower()
            or 'slicer, hired muscle' in row['name'].lower()
            or 'wilson, refined grizzly' in row['name'].lower()
            or 'yargle and multani' in row['name'].lower()
            or 'zurgo helmsmasher' in row['name'].lower()
            ):
            tag_type = ['Voltron']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    # Overwrite file with voltron tag added
    print(f'"Voltron" themed cards in {color}_cards.csv have been tagged.\n')

### Lands matter
def tag_for_lands_matter(df, color):
    # Iterate through each {color}_cards.csv file to find lands matter cards
    # Tag for Lands Matter, effects like Landfal, play additional lands,
    # that affect where you can play lands from. Also includes domain as it
    # cares about basic land types. And landwalk effects
    print(f'Tagging cards in {color}_cards.csv that fit the "Lands Matter" theme:')
    print('\n===============\n')
    print(f'Tagging cards in {color}_cards.csv that have a generalized "Lands Matter" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        
        # Do specifically name lands matter cards
        if ('abundance' in row['name'].lower()
            or 'archdruid\'s charm' in row['name'].lower()
            or 'archelos, lagoon mystic' in row['name'].lower()
            or 'catacylsmic prospecting' in row['name'].lower()
            or 'coiling oracle' in row['name'].lower()
            or 'disorienting choice' in row['name'].lower()
            or 'eerie ultimatum' in row['name'].lower()
            or 'gitrog monster' in row['name'].lower()
            or 'mana reflection' in row['name'].lower()
            or 'nahiri\'s lithoforming' in row['name'].lower()
            or 'nine-fingers keene' in row['name'].lower()
            or 'open the way' in row['name'].lower()
            or 'realms uncharted' in row['name'].lower()
            or 'reshape the earth' in row['name'].lower()
            or 'scapeshift' in row['name'].lower()
            or 'yarok, the desecrated' in row['name'].lower()
            or 'wonderscape sage' in row['name'].lower()
            ):
            tag_type = ['Lands Matter']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
                    
        # Do generalized lands matter tags
        if pd.notna(row['text']):
            if ('copy of any land' in row['text'].lower()
                or 'desert card' in row['text'].lower()
                or 'everything counter' in row['text'].lower()
                or 'flood counter' in row['text'].lower()
                or 'forest dryad' in row['text'].lower()
                or 'forest lands' in row['text'].lower()
                or 'landfall' in row['text'].lower()
                or 'land card' in row['text'].lower()
                or 'land card from your graveyard' in row['text'].lower()
                or 'land card in your graveyard' in row['text'].lower()
                or 'land card is put into your graveyard' in row['text'].lower()
                or 'land cards' in row['text'].lower()
                or 'land cards from your graveyard' in row['text'].lower()
                or 'land cards in your graveyard' in row['text'].lower()
                or 'land cards put into your graveyard' in row['text'].lower()
                or 'land enters' in row['text'].lower()
                or 'lands you control' in row['text'].lower()
                or 'lands from your graveyard' in row['text'].lower()
                or 'nonbasic land type' in row['text'].lower()
                or 'number of lands you control' in row['text'].lower()
                or 'one or more land cards' in row ['text'.lower()]
                or 'play a land' in row['text'].lower()
                or 'play an additional land' in row['text'].lower()
                or 'play lands from the top of your library' in row['text'].lower()
                or 'play two additional lands' in row['text'].lower()
                or 'plays a land' in row['text'].lower()
                or 'put a land card' in row['text'].lower()
                or 'return all land cards' in row['text'].lower()
                or 'sacrifice a land' in row['text'].lower()
                or 'search their library for a basic land card' in row['text'].lower()
                or 'search your library for a basic land card' in row['text'].lower()
                or 'search your library for a land card' in row['text'].lower()
                or 'search your library for up to two basic land card' in row['text'].lower()
                or 'target land' in row['text'].lower()
                or 'target land card' in row['text'].lower()
                or 'up to x land card' in row['text'].lower()
                ):
                tag_type = ['Lands Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
    print(f'General "Lands Matter" themed cards in {color}_cards.csv have been tagged.\n')
    print('\n==========\n')
    tag_for_domain(df, color)
    print('\n==========\n')
    tag_for_landfall(df, color)
    print('\n==========\n')
    tag_land_types(df, color)
    print('\n==========\n')
    tag_for_landwalk(df, color)
    # Overwrite file with wheels tag added
    print(f'"Lands Matter" themed cards in {color}_cards.csv have been tagged.\n')
    
## Domain
def tag_for_domain(df, color):
    print(f'Tagging cards in {color}_cards.csv that have the "Domain" keyword.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        # Add domain tags
        if pd.notna(row['text']):
            if ('domain' in row['text'].lower()
                ):
                tag_type = ['Domain', 'Lands Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['keywords']):
            if ('Domain' in row['keywords']
            ):
                tag_type = ['Domain', 'Lands Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    # Overwrite file with Landfall tag added
    print(f'"Domain" cards in {color}_cards.csv have been tagged.\n')

## Tag for landfall
def tag_for_landfall(df, color):
    print(f'Tagging cards in {color}_cards.csv that have the "Landfall" keyword.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            continue
        # Add Landfall tags
        if ('landfall' in row['text'].lower()
            ):
            tag_type = ['Landfall', 'Lands Matter']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
        
    # Overwrite file with LAndfall tag added
    #df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
    print(f'"Landfall" cards in {color}_cards.csv have been tagged.\n')
    
## Tag for land type
def tag_land_types(df, color):
    print(f'Tagging cards in {color}_cards.csv that have specific land types.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        # Tag Urza lands
        if ('Land — Urza' in row['type']
            ):
            tag_type = ['Urzatron', 'Lands Matter']    
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
        
        # Tag Snow lands
        if ('Snow Land' in row['type']
            ):
            tag_type = ['Snow Matters', 'Lands Matter']    
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
        
        # Define land types
        land_types = ['plains', 'island', 'swamp', 'mountain', 'forest', 'wastes',
                        'cave','desert', 'gate', 'lair', 'locus', 'sphere']
        
        if pd.notna(row['text']):
            # Search for cards that use the specific land types (i.e. fetches, reveal lands, etc...)
            for land_type in land_types:
                if (f'search your library for a {land_type}' in row['text'].lower()
                    or f'search your library for up to two {land_type}' in row['text'].lower()
                    or land_type.capitalize() in row['type']
                    ):
                    if ('azor\'s gateway' in row['name'].lower()
                        ):
                        continue
                    if land_type not in ['plains', 'wastes' 'locus']:
                        tag_type = [f'{land_type.capitalize()}s Matter', 'Lands Matter']
                    else:
                        tag_type = [f'{land_type.capitalize()} Matter', 'Lands Matter']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
                
                # Tag the cards that don't have types that could be in card names and unrelated
                # to their land type
                if land_type not in ['gate', 'sphere', 'lair', 'locus', 'cave']:
                    if (land_type in row['text'].lower()):
                        if land_type not in ['plains', 'wastes']:
                            tag_type = [f'{land_type.capitalize()}s Matter', 'Lands Matter']
                        else:
                            tag_type = [f'{land_type.capitalize()} Matter', 'Lands Matter']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
                
                # Tag cards that do have types that could be in card names and unrelated to their
                # land types, with some refined logic to filter better filter out matches
                if land_type in ['gate', 'sphere', 'lair', 'locus', 'cave']:
                    if (f'or more {land_type.capitalize()}s' in row['text']
                        or f'{land_type.capitalize()}s' in row['text']
                        or f'a {land_type.capitalize()}' in row['text']
                        or f'{land_type.capitalize()} you control' in row['text']
                        ):
                        # Exclude specifically named cards
                        if ('Adarkar Wastes' in row['name']
                            or 'Afflicted Deserter'in row['name']
                            or 'Caves of Chaos Adventurer'in row['name']
                            or 'Caves of Koilos' in row['name']
                            or 'Cave People'in row['name']
                            or 'Gates of Istfell' in row['name']
                            or 'Gimli of the Glittering Caves'in row['name']
                            or 'Karplusan Forest' in row['name']
                            or 'Llanowar Wastes' in row['name']
                            or 'Mountain Titan' in row['name']
                            or 'Sea Gate Oracle' in row['name']
                            or 'Sea Gate Restoration'in row['name']
                            or 'Sea Gate Stormcaller'in row['name']
                            or 'Skyshroud Forest' in row['name']
                            or 'Sophina, Spearsage Deserter' in row['name']
                            or 'Swamp Mosquito'in row['name']
                            or 'Watcher of the Spheres' in row['name']
                            ):
                            continue
                        tag_type = [f'{land_type.capitalize()}s Matter', 'Lands Matter']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
    
    # Overwrite file with land type tags added
    print(f'Land types tagged on cards in {color}_cards.csv\n')

## Landwalk
def tag_for_landwalk(df, color):
    print(f'Tagging cards in {color}_cards.csv that have the "Landwalk" keyword.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        land_types = ['plains', 'island', 'swamp', 'mountain', 'forest', 'nonbasic land', 'land']
        # Define landwalk abilities
        if pd.notna(row['text']):
            for land_type in land_types:
                if (f'{land_type}walk' in row['text'].lower()):
                    tag_type = [f'{land_type.capitalize()}walk']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
        
    # Overwrite file with wheels tag added
    print(f'"Landwalk" cards in {color}_cards.csv have been tagged.\n')

### Spells Matter
def tag_for_spellslinger(df, color):
    # Iterate through each {color}_cards.csv file to find spells matter cards
    # Things like Storm, Magecraft, playing noncreature spells, or otherwise
    # Playing a lot of spells
    # Noncreature cast triggers
    print(f'Checking {color}_cards.csv for "Spellslinger" cards.\n')
    print('\n===============\n')
    print(f'Checking {color}_cards.csv for cards that care about casting spells.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('cast a modal' in row['text'].lower()
                or 'cast a spell from anywhere' in row['text'].lower()
                or 'cast an instant' in row['text'].lower()
                or 'cast a noncreature' in row['text'].lower()
                or 'casts an instant' in row['text'].lower()
                or 'casts a noncreature' in row['text'].lower()
                or 'first instant' in row['text'].lower()
                or 'first spell' in row['text'].lower()
                or 'next cast an instant' in row['text'].lower()
                or 'next instant' in row['text'].lower()
                or 'next spell' in row['text'].lower()
                or 'second instant' in row['text'].lower()
                or 'second spell' in row['text'].lower()
                or 'you cast an instant' in row['text'].lower()
                or 'you cast a spell' in row['text'].lower()
                ):
                tag_type = ['Spellslinger', 'Spells Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    # Overwrite file with Spells Matter tag added
    print(f'Cards that care about casting spells in {color}_cards.csv have been tagged.\n')
    print('\n==========\n')
    tag_for_storm(df, color)
    print('\n==========\n')
    tag_for_magecraft(df, color)
    print('\n==========\n')
    tag_for_cantrips(df, color)
    print('\n==========\n')
    tag_for_spell_copy(df, color)
    print(f'"Spellslinger" themed cards in {color}_cards.csv have been tagged.\n')

## Storm
def tag_for_storm(df, color):
    # Tag for storm
    print(f'Tagging cards in {color}_cards.csv that have the the "Storm" keyword.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        
        if pd.notna(row['keywords']):
            if ('storm' in row['keywords'].lower()
                ):
                tag_type = ['Storm', 'Spellslinger', 'Spells Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        if pd.notna(row['text']):
            if ('gain storm' in row['text'].lower()
                or 'has storm' in row['text'].lower()
                or 'have storm' in row['text'].lower()
                ):
                tag_type = ['Storm', 'Spellslinger', 'Spells Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'Cards with "Storm" tagged in {color}_cards.csv.\n')

## Magecraft
def tag_for_magecraft(df, color):
    # Logic for magecraft
    print(f'Checking {color}_cards.csv for "Magecraft" cards.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['keywords']):
            if ('magecraft' in row['keywords'].lower()
                ):
                tag_type = ['Magecraft', 'Spellslinger', 'Spells Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
                        
    print(f'"Magecraft" cards tagged in {color}_cards.csv.\n')

## Spell Copy
def tag_for_spell_copy(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Spell Copy" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('copy a spell' in row['text'].lower()
                or 'copy it' in row['text'].lower()
                or 'copy that spell' in row['text'].lower()
                or 'copy target' in row['text'].lower()
                or 'has casualty' in row['text'].lower()
                or 'has conspire' in row['text'].lower()
                ):
                tag_type = ['Spell Copy']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if ('Magecraft' in theme_tags
            or 'Storm' in theme_tags
            or 'Spellslinger' in theme_tags
            ):
            tag_type = ['Spell Copy']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Spell Copy" cards in {color}_cards.csv have been tagged.\n')

### Ramp
def tag_for_ramp(df, color):
    # Tag for ramp
    print(f'Tagging cards in {color}_cards.csv that are considerd Ramp.\n')
    print('\n===============\n')
    mana_dorks(df, color)
    print('\n==========\n')
    mana_rocks(df, color)
    print('\n==========\n')
    play_extra_lands(df, color)
    print('\n==========\n')
    search_for_lands(df, color)
    print('\n==========\n')
    
    print(f'Tagging any other Ramp cards in {color}_cards.csv.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            # Tap for extra mana
            if ('for mana, add an additional' in row['text'].lower()
                or 'for mana, adds an additional' in row['text'].lower()
                or 'for mana, add one' in row['text'].lower()
                or 'for mana, it produces three' in row['text'].lower()
                or 'for mana, it produces twice' in row['text'].lower()
                or 'for mana, its controller adds' in row['text'].lower()
                or 'for mana, that player adds' in row['text'].lower()
                or 'for mana, while you\'re the monarch' in row['text'].lower()
                ):
                tag_type = ['Mana Dork', 'Ramp']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    print(f'Other Ramp cards in {color}_cards.csv have been tagged.\n')
    
    print(f'Ramp cards in {color}_cards.csv have been tagged.\n')

## Mana Dorks
def mana_dorks(df, color):
    print(f'Tagging cards in {color}_cards.csv that are Mana Dorks.\n'
          'A Mana Dork is any creature that produces mana, either by tapping, sacrificing, or other means.\n')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('Creature' in row['type']
                ):
                # Tap itself for mana
                if ('{T}: Add' in row['text']):
                    tag_type = ['Mana Dork', 'Ramp']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
                
                # Tap to untap
                if ('{T}: Untap' in row['text']):
                    tag_type = ['Mana Dork', 'Ramp']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
                
                # Sac for mana
                if ('creature: add' in row['text'].lower()):
                    tag_type = ['Mana Dork', 'Ramp']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
                
                # Tap something else for mana
                if ('control: add' in row['text'].lower()):
                    tag_type = ['Mana Dork', 'Ramp']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
                
                # Specific cards
                if ('Awaken the Woods' == row['name']
                    or 'Forest Dryad' == row['name']):
                    tag_type = ['Mana Dork', 'Ramp']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
                
                # Add by other means
                colors = ['C', 'W', 'U', 'B', 'R', 'G']
                for color in colors:
                    if f'add {{{color}}}' in row['text'].lower():
                        tag_type = ['Mana Dork', 'Ramp']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
    
    print(f'Mana Dork cards in {color}_cards.csv have been tagged.\n')

## Mana Rocks
def mana_rocks(df, color):
    print(f'Tagging cards in {color}_cards.csv that are or create Mana Rocks.\n'
          'A Mana Rock is an artifact that produces mana, either by tapping, sacrificing, or other means.\n')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('Artifact' in row['type']
                ):
                # Tap itself for mana
                if ('{T}: Add' in row['text']):
                    tag_type = ['Mana Rock', 'Ramp']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
                
                # Tap to untap
                if ('{T}: Untap' in row['text']):
                    tag_type = ['Mana Rock', 'Ramp']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
                
                # Sac for mana
                if ('creature: add' in row['text'].lower()):
                    tag_type = ['Mana Rock', 'Ramp']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
                
                # Tap something else for mana
                if ('control: add' in row['text'].lower()):
                    tag_type = ['Mana Rock', 'Ramp']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
                
                # Add by other means
                colors = ['C', 'W', 'U', 'B', 'R', 'G']
                for color in colors:
                    if f'add {{{color}}}' in row['text'].lower():
                        tag_type = ['Mana Rock', 'Ramp']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
                
            # Mana rock generation
            if ('Powerstone Tokens' in theme_tags
                or 'Treasure Tokens' in theme_tags
                or 'Gold Tokens' in theme_tags
                or 'token named metorite' in row['text'].lower()
                ):
                tag_type = ['Mana Rock', 'Ramp']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    print(f'Mana Rock cards in {color}_cards.csv have been tagged.\n')

## Play extra lands
def play_extra_lands(df, color):
    print(f'Tagging cards in {color}_cards.csv that let you play extra lands or otherwise return lands.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('additional land' in row['text'].lower()
                or 'play an additional land' in row['text'].lower()
                or 'play two additional lands' in row['text'].lower()
                or 'put a land' in row['text'].lower()
                or 'put all land' in row['text'].lower()
                or 'put those land' in row['text'].lower()
                or 'return all land' in row['text'].lower()
                or 'return target land' in row['text'].lower()
                ):
                tag_type = ['Lands Matter', 'Ramp']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            if ('return all land' in row['text'].lower()
                ):
                tag_type = ['Lands Matter', 'Ramp']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'Extra land cards in {color}_cards.csv have been tagged.\n')

## Land Search
def search_for_lands(df, color):
    print(f'Tagging cards in {color}_cards.csv that have either search for lands or directly put a land onto the battlefield.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            # Search for lands
            if ('search your library for a basic' in row['text'].lower()
                or 'search your library for a land' in row['text'].lower()
                or 'each player searches' in row['text'].lower()
                ):
                tag_type = ['Lands Matter', 'Ramp']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            if ('search your library for up to' in row['text'].lower()
                and 'land' in row['text'].lower()):
                tag_type = ['Lands Matter', 'Ramp']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
                        
            # Reveal for lands
            if ('put those land' in row['text'].lower()):
                tag_type = ['Lands Matter', 'Ramp']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # For specific land types
            land_types = ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest', 'Wastes']
            for land_type in land_types:
                if (f'search your library for a basic {land_type.lower()}' in row['text'].lower()
                    or f'search your library for a {land_type.lower()}' in row['text'].lower()
                    or f'search your library for an {land_type.lower()}' in row['text'].lower()
                    ):
                    tag_type = ['Lands Matter', 'Ramp']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
    
    print(f'Cards that search for or directly put out a land in {color}_cards.csv have been tagged.\n')

### Other Misc Themes
def tag_for_themes(df, color):
    print(f'Tagging other themes in {color}_cards.csv.\n')
    print('\n===============\n')
    tag_for_aggro(df, color)
    print('\n==========\n')
    search_for_aristocrats(df, color)
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
    search_for_legends(df, color)
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
    
    print(f'Other themes have been tagged in {color}_cards.csv.\n')
    
## Aggro
def tag_for_aggro(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Aggro" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('a creature attacking' in row['text'].lower()
                or 'deal combat damage' in row['text'].lower()
                or 'deals combat damage' in row['text'].lower()
                or 'have riot' in row['text'].lower()
                or 'this creature attacks' in row['text'].lower()
                or 'whenever you attack' in row['text'].lower()
                or f'whenever {row['name'].lower()} attack' in row['text'].lower()
                or f'whenever {row['name'].lower()} deals combat' in row['text'].lower()
                or 'you control attack' in row['text'].lower()
                or 'you control deals combat' in row['text'].lower()
                or 'untap all attacking creatures' in row['text'].lower()
                ):
                tag_type = ['Aggro', 'Combat Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['keywords']):
            if ('Blitz' in row['keywords']
                or 'Deathtouch' in row['keywords']
                or 'Double Strike' in row['keywords']
                or 'First Strike' in row['keywords']
                or 'Fear' in row['keywords']
                or 'Haste' in row['keywords']
                or 'Menace' in row['keywords']
                or 'Myriad' in row['keywords']
                or 'Prowl' in row['keywords']
                or 'Raid' in row['keywords']
                or 'Shadow' in row['keywords']
                or 'Spectale' in row['keywords']
                or 'Trample' in row['keywords']
                ):
                tag_type = ['Aggro', 'Combat Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if ('Voltron' in theme_tags):
            tag_type = ['Aggro', 'Combat Matters']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Aggro" cards in {color}_cards.csv have been tagged.\n')

## Aristocrats
def search_for_aristocrats(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit either an "Aristocrats" or "Sacrifice Matters" theme.\n'
          'These themes have a large amount of overlap and most have overlapping cards.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        # Specifically named cards
        if (
            row['name'] == 'Bolas\'s Citadel'
            or row['name'] == 'Chatterfang, Squirrel General'
            or row['name'] == 'Endred Sahr, Master Breeder'
            or row['name'] == 'Hazel of the Rootbloom'
            or row['name'] == 'Korvold, Gleeful Glutton'
            or row['name'] == 'Massacre Girl'
            or row['name'] == 'Marchesa, the Black Rose'
            or row['name'] == 'Slimefoot and Squee'
            or row['name'] == 'Teysa Karlov'
            or row['name'] == 'Teysa, Orzhov Scion'
            ):
            tag_type = ['Aristocrats', 'Sacrifice Matters']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
        
        # In text
        if pd.notna(row['text']):
            if (
                'another creature dies' in row['text'].lower()
                or 'has blitz' in row['text'].lower()
                or 'have blitz' in row['text'].lower()
                or 'each player sacrifices:' in row['text'].lower()
                or 'if a creature died' in row['text'].lower()
                or 'if a creature dying' in row['text'].lower()
                or 'permanents were sacrificed' in row['text'].lower()
                or 'put into a graveyard' in row['text'].lower()
                or 'sacrifice a creature:' in row['text'].lower()
                or 'sacrifice another' in row['text'].lower()
                or 'sacrifice another creature' in row['text'].lower()
                or 'sacrifice a nontoken:' in row['text'].lower()
                or 'sacrifice a permanent:' in row['text'].lower()
                or 'sacrifice another' in row['text'].lower()
                or 'sacrifice another creature' in row['text'].lower()
                or 'sacrifice another nontoken:' in row['text'].lower()
                or 'sacrifice another permanent:' in row['text'].lower()
                or 'sacrifice another token:' in row['text'].lower()
                or 'sacrifices a creature:' in row['text'].lower()
                or 'sacrifices another:' in row['text'].lower()
                or 'sacrifices another creature:' in row['text'].lower()
                or 'sacrifices another nontoken:' in row['text'].lower()
                or 'sacrifices another permanent:' in row['text'].lower()
                or 'sacrifices another token:' in row['text'].lower()
                or 'sacrifices a nontoken:' in row['text'].lower()
                or 'sacrifices a permanent:' in row['text'].lower()
                or 'sacrifices a token:' in row['text'].lower()
                or 'when this creature dies' in row['text'].lower()
                or 'whenever a food' in row['text'].lower()
                or 'when this creature dies' in row['text'].lower()
                or 'whenever you sacrifice' in row['text'].lower()
                or 'you control dies' in row['text'].lower()
                or 'you own dies' in row['text'].lower()
                or 'you may sacrifice' in row['text'].lower()
                ):
                tag_type = ['Aristocrats', 'Sacrifice Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        # Self-sacrifice
        if pd.notna(row['text']):
            if 'Creature' in row['type']:
                if (
                    f'sacrifice {row['name'].lower()}' in row['text'].lower()
                    or f'when {row['name'].lower()} dies' in row['text'].lower()
                    ):
                    tag_type = ['Aristocrats', 'Sacrifice Matters']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
        
        # In keywords
        if pd.notna(row['keywords']):
            if ('Blitz' in row['keywords'].lower()
                ):
                tag_type = ['Aristocrats', 'Sacrifice Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Aristocrats" and "Sacrifice Matters" cards in {color}_cards.csv have been tagged.\n')

## Big Mana
def tag_for_big_mana(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Big Mana" theme.')
    df['manaValue'] = df['manaValue'].astype(int)
    df['manaCost'] = df['manaCost'].astype(str)
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        
        # Specific cards
        if (row['name'] == 'Akroma\'s Memorial'
            or row['name'] == 'Forsake Monument'
            or row['name'] == 'Guardian Project'
            or row['name'] == 'Omniscience'
            or row['name'] == 'One with the Multiverse'
            or row['name'] == 'Portal to Phyrexia'
            ):
            tag_type = ['Big Mana']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
        
        if pd.notna(row['text']):
            # Mana value 5 or greater matters
            if (
                'add {w}{u}{b}{r}{g}' in row['text'].lower()
                or 'card onto the battlefield' in row['text'].lower()
                or 'control with power 3 or greater' in row['text'].lower()
                or 'control with power 4 or greater' in row['text'].lower()
                or 'control with power 5 or greater' in row['text'].lower()
                or 'creature with power 3 or greater' in row['text'].lower()
                or 'creature with power 4 or greater' in row['text'].lower()
                or 'creature with power 5 or greater' in row['text'].lower()
                or 'double the power' in row['text'].lower()
                or 'from among them onto the battlefield' in row['text'].lower()
                or 'from among them without paying' in row['text'].lower()
                or 'hand onto the battlefield' in row['text'].lower()
                or 'mana, add one mana' in row['text'].lower()
                or 'mana, it produces twice' in row['text'].lower()
                or 'mana, it produces three' in row['text'].lower()
                or 'mana, its controller adds' in row['text'].lower()
                or 'you may cast it without paying' in row['text'].lower()
                or 'pay {w}{u}{b}{r}{g}' in row['text'].lower()
                or 'spell with power 5 or greater' in row['text'].lower()
                or 'value 5 or greater' in row['text'].lower()
                or 'value 6 or greater' in row['text'].lower()
                or 'value 7 or greater' in row['text'].lower()
                ):
                tag_type = ['Big Mana']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        # Spells with mana value 5 or greater
        if row['manaValue'] >= 5:
            tag_type = ['Big Mana']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags

        # X spells
        if ('{X}' in row['manaCost']
            ):
            tag_type = ['Big Mana']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
        
        # Keywords that care about big mana
        if pd.notna(row['keywords']):
            if ('Cascade' in row['keywords'].lower()
                or 'Convoke' in row['keywords'].lower()
                or 'Discover' in row['keywords'].lower()
                ):
                tag_type = ['Big Mana']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
                        
        # Already tagged things
        if ('Cost Reduction' in theme_tags
            ):
            tag_type = ['Big Mana']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Big Mana" themed cards in {color}_cards.csv have been tagged.\n')

## Blink
def tag_for_blink(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Blink/Flicker" theme.\n'
          'Cards here can generally also fit an ETB matters theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('creature entering causes' in row['text'].lower()
                or 'exile any number of other' in row['text'].lower()
                or 'exile one or more cards from your hand' in row['text'].lower()
                or 'permanent entering the battlefield' in row['text'].lower()
                or 'permanent you control, then return' in row['text'].lower()
                or 'permanent you control enters' in row['text'].lower()
                or 'permanents you control, then return' in row['text'].lower()
                or 'return it to the battlefield' in row['text'].lower()
                or 'return that card to the battlefield' in row['text'].lower()
                or 'return them to the battlefield' in row['text'].lower()
                or 'return those cards to the battlefield' in row['text'].lower()
                or 'triggered ability of a permanent' in row['text'].lower()
                or 'whenever another creature enters' in row['text'].lower()
                or 'whenever another nontoken creature enters' in row['text'].lower()
                or f'when {row['name']} enters' in row['text'].lower()
                or f'when {row['name']} leaves' in row['text'].lower()
                or 'when this creature enters' in row['text'].lower()
                or 'when this creature leaves' in row['text'].lower()
                or 'whenever this creature enters' in row['text'].lower()
                or 'whenever this creature leaves' in row['text'].lower()
                or f'whenever {row['name']} enters' in row['text'].lower()
                or f'whenever {row['name']} leaves' in row['text'].lower()
                ):
                tag_type = ['Blink', 'Enter the Battlefield', 'Leave the Battlefield']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Blink/Flicker" cards in {color}_cards.csv have been tagged.\n')
    
## Burn
def tag_for_burn(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Burn" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        damage_list = list(range(1, 101))
        damage_list = list(map(str, damage_list))
        damage_list.append('x')
        if pd.notna(row['text']):
            # Deals damage from 1-100 or X
            for i in damage_list:
                if (f'deals {i} damage' in row['text'].lower()
                    or f'lose {i} life' in row['text'].lower()
                    or f'loses {i} life' in row['text'].lower()
                    ):
                    tag_type = ['Burn']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
            
            # Deals damage triggers
            if (
                'deals combat damage' in row['text'].lower()
                or 'deals damage' in row['text'].lower()
                or 'deals noncombat damage' in row['text'].lower()
                or 'deals that much damage' in row['text'].lower()
                or 'each 1 life' in row['text'].lower()
                or 'excess damage' in row['text'].lower()
                or 'excess noncombat damage' in row['text'].lower()
                or 'loses that much life' in row['text'].lower()
                or 'opponent lost life' in row['text'].lower()
                or 'opponent loses life' in row['text'].lower()
                or 'player loses life' in row['text'].lower()
                or 'unspent mana causes that player to lose that much life' in row['text'].lower()
                or 'would deal an amount of noncombat damage' in row['text'].lower()
                or 'would deal damage' in row['text'].lower()
                or 'would deal noncombat damage' in row['text'].lower()
                or 'would lose life' in row['text'].lower()
                ):
                tag_type = ['Burn']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Pingers
            if ('deals 1 damage' in row['text'].lower()
                or 'exactly 1 damage' in row['text'].lower()
                or 'loses 1 life' in row['text'].lower()
                ):
                tag_type = ['Pingers']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
        # Keywords
        if pd.notna(row['keywords']):
            if ('Bloodthirst' in row['keywords'].lower()
                or 'Spectacle' in row['keywords'].lower()
                ):
                tag_type = ['Burn']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Burn" cards in {color}_cards.csv have been tagged.\n')

## Clones
def tag_for_clones(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Clones" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('a copy of a creature' in row['text'].lower()
                or 'a copy of an aura' in row['text'].lower()
                or 'a copy of a permanent' in row['text'].lower()
                or 'a token that\'s a copy of' in row['text'].lower()
                or 'as a copy of' in row['text'].lower()
                or 'becomes a copy of' in row['text'].lower()
                or '"legend rule" doesn\'t apply' in row['text'].lower()
                or 'twice that many of those tokens' in row['text'].lower()
                ):
                tag_type = ['Clones']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['keywords']):
            if ('Myriad' in row['keywords']
                ):
                tag_type = ['Clones']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Clones" cards in {color}_cards.csv have been tagged.\n')

## Control
def tag_for_control(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Control" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('a player casts' in row['text'].lower()
                or 'can\'t attacok you' in row['text'].lower()
                or 'cast your first spell during each opponent\'s turns' in row['text'].lower()
                or 'choose new target' in row['text'].lower()
                or 'choose target opponent' in row['text'].lower()
                or 'counter target' in row['text'].lower()
                or 'of an opponent\'s choice' in row['text'].lower()
                or 'opponent cast' in row['text'].lower()
                or 'return target' in row['text'].lower()
                or 'tap an untapped creature' in row['text'].lower()
                or 'your opponents cast' in row['text'].lower()
                ):
                tag_type = ['Control']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['keywords']):
            if ('Council\'s dilemma' in row['keywords']
                ):
                tag_type = ['Control']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Control" cards in {color}_cards.csv have been tagged.\n')

## Energy
def tag_for_energy(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Energy" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('{e}' in row['text'].lower()
                ):
                tag_type = ['Energy']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['keywords']):
            if ('' in row['keywords'].lower()
                ):
                tag_type = []
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Energy" cards in {color}_cards.csv have been tagged.\n')
    
## Infect
def tag_for_infect(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Infect" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('one or more counter' in row['text'].lower()
                or 'poison counter' in row['text'].lower()
                or 'toxic 1' in row['text'].lower()
                ):
                tag_type = ['Infect']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['keywords']):
            if ('Infect' in row['keywords'].lower()
                or 'Proliferate' in row['keywords'].lower()
                or 'Toxic' in row['keywords'].lower()
                ):
                tag_type = ['Infect']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Infect" cards in {color}_cards.csv have been tagged.\n')

## Legends Matter
def search_for_legends(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit a "Legends Matter" or "Historics Matter" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if ('Legendary' in row['type']
            ):
            tag_type = ['Historics Matter', 'Legends Matter']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['text']):
            if ('a legendary creature' in row['text'].lower()
                or 'another legendary' in row['text'].lower()
                or 'cast a historic' in row['text'].lower()
                or 'cast a legendary' in row['text'].lower()
                or 'cast legendary' in row['text'].lower()
                or 'equip legendary' in row['text'].lower()
                or 'historic cards' in row['text'].lower()
                or 'historic creature' in row['text'].lower()
                or 'historic permanent' in row['text'].lower()
                or 'historic spells' in row['text'].lower()
                or 'legendary creature you control' in row['text'].lower()
                or 'legendary creatures you control' in row['text'].lower()
                or 'legendary permanents' in row['text'].lower()
                or 'legendary spells you' in row['text'].lower()
                or 'number of legendary' in row['text'].lower()
                or 'other legendary' in row['text'].lower()
                or 'play a historic' in row['text'].lower()
                or 'play a legendary' in row['text'].lower()
                or 'target legendary' in row['text'].lower()
                or 'the "legend rule" doesn\'t' in row['text'].lower()
                ):
                tag_type = ['Historics Matter', 'Legends Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Legends Matter" and "Historics Matter" cards in {color}_cards.csv have been tagged.\n')

## Little Fellas
def tag_for_little_guys(df, color):
    print(f'Tagging cards in {color}_cards.csv that are or care about low-power (2 or less) creatures.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['power']):
            if '*' in row['power']:
                continue
            if (int(row['power']) <= 2):
                tag_type = ['Little Fellas']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        if pd.notna(row['text']):
            if ('power 2 or less' in row['text'].lower()
                ):
                tag_type = ['Little Fellas']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'Low-power (2 or less) creature cards in {color}_cards.csv have been tagged.\n')

## Mill
def tag_for_mill(df, color):
    print(f'Tagging cards in {color}_cards.csv that have a "Mill" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if ('Mill' in theme_tags):
            continue
        if pd.notna(row['text']):
            if ('desended' in row['text'].lower()
                or 'from a graveyard' in row['text'].lower()
                or 'from your graveyard' in row['text'].lower()
                or 'in your graveyard' in row['text'].lower()
                or 'into his or her graveyard' in row['text'].lower()
                or 'into their graveyard' in row['text'].lower()
                or 'into your graveyard' in row['text'].lower()
                or 'mills that many cards' in row['text'].lower()
                or 'opponent\'s graveyard' in row['text'].lower()
                or 'put into a graveyard' in row['text'].lower()
                or 'put into an opponent\'s graveyard' in row['text'].lower()
                or 'put into your graveyard' in row['text'].lower()
                or 'rad counter' in row['text'].lower()
                or 'Surveil' in row['text']
                or 'would mill' in row['text'].lower()
                ):
                tag_type = ['Mill']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            for num in num_to_search:
                if (f'mill {num}' in row['text'].lower()
                    or f'mills {num}' in row['text'].lower()
                    ):
                    tag_type = ['Mill']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['keywords']):
            if ('Descend' in row['keywords']
                or 'Mill' in row['keywords']
                or 'Surveil' in row['keywords']
                ):
                tag_type = ['Mill']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Mill" cards in {color}_cards.csv have been tagged.\n')

## Monarch
def tag_for_monarch(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Monarch" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('you are the monarch' in row['text'].lower()
                or 'you become the monarch' in row['text'].lower()
                or 'you can\'t become the monarch' in row['text'].lower()
                ):
                tag_type = ['Monarch']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['keywords']):
            if ('Monarch' in row['keywords'].lower()
                ):
                tag_type = ['Monarch']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Monarch" cards in {color}_cards.csv have been tagged.\n')

## Multi-copy cards
def tag_for_multiple_copies(df, color):
    print(f'Tagging cards in {color}_cards.csv that allow having multiple copies.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if (row['name'] in multiple_copy_cards
            ):
            tag_type = ['Multiple Copies', row['name']]
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Multiple-copy" cards in {color}_cards.csv have been tagged.\n')

## Planeswalkers
def tag_for_planeswalkers(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Planeswalkers/Super Friends" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('a planeswalker' in row['text'].lower()
                or 'affinity for planeswalker' in row['text'].lower()
                or 'a noncreature' in row['text'].lower()
                or 'enchant planeswalker' in row['text'].lower()
                or 'historic permanent' in row['text'].lower()
                or 'legendary permanent' in row['text'].lower()
                or 'loyalty ability' in row['text'].lower()
                or 'one or more counter' in row['text'].lower()
                or 'planeswalker spells' in row['text'].lower()
                or 'planeswalker type' in row['text'].lower()
                ):
                tag_type = ['Planeswalkers', 'Super Friends']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['keywords']):
            if ('Proliferate' in row['keywords']
                ):
                tag_type = ['Planeswalkers', 'Super Friends']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        if 'Planeswalker' in row['type']:
            tag_type = ['Planeswalkers', 'Super Friends']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Planeswalkers/Super Friends" cards in {color}_cards.csv have been tagged.\n')

## Reanimator
def tag_for_reanimate(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Reanimate" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('descended' in row['text'].lower()
                or 'discard your hand' in row['text'].lower()
                or 'from a graveyard' in row['text'].lower()
                or 'in a graveyard' in row['text'].lower()
                or 'into a graveyard' in row['text'].lower()
                or 'leave a graveyard' in row['text'].lower()
                or 'from a graveyard' in row['text'].lower()
                or 'in your graveyard' in row['text'].lower()
                or 'into your graveyard' in row['text'].lower()
                or 'leave your graveyard' in row['text'].lower()
                ):
                tag_type = ['Reanimate']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['keywords']):
            if ('Blitz' in row['keywords']
                or 'Connive' in row['keywords']
                or 'Descend' in row['keywords']
                or 'Escape' in row['keywords']
                or 'Flashback' in row['keywords']
                or 'Mill' in row['keywords']
                ):
                tag_type = ['Reanimate']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        if ('Loot' in theme_tags
            ):
            tag_type = ['Reanimate']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
        
        if ('Zombie' in row['creatureTypes']
            ):
            tag_type = ['Reanimate']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Reanimate" cards in {color}_cards.csv have been tagged.\n')

## Stax
def tag_for_stax(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Stax" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('an opponent controls' in row['text'].lower()
                or 'can attack you' in row['text'].lower()
                or 'can\'t attack' in row['text'].lower()
                or 'can\'t be cast' in row['text'].lower()
                or 'can\'t be activated' in row['text'].lower()
                or 'can\'t cast spells' in row['text'].lower()
                or 'can\'t enter' in row['text'].lower()
                or 'can\'t search' in row['text'].lower()
                or 'can\'t untap' in row['text'].lower()
                or 'don\'t untap' in row['text'].lower()
                or 'don\'t cause abilities' in row['text'].lower()
                or 'each other player\'s' in row['text'].lower()
                or 'each player\'s upkeep' in row['text'].lower()
                or 'opponent would search' in row['text'].lower()
                or 'opponents cast cost' in row['text'].lower()
                or 'opponents can\'t' in row['text'].lower()
                or 'opponents control' in row['text'].lower()
                or 'opponents control can\'t' in row['text'].lower()
                or 'opponents control enter tapped' in row['text'].lower()
                or 'spells cost {1} more' in row['text'].lower()
                or 'spells cost {2} more' in row['text'].lower()
                or 'spells cost {3} more' in row['text'].lower()
                or 'spells cost {4} more' in row['text'].lower()
                or 'spells cost {5} more' in row['text'].lower()
                or 'that player doesn\'t' in row['text'].lower()
                or 'unless that player pays' in row['text'].lower()
                or 'you control your opponent' in row['text'].lower()
                or 'you gain protection' in row['text'].lower()
                ):
                tag_type = ['Stax']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        if ('Control' in theme_tags
            ):
            tag_type = ['Stax']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Stax" cards in {color}_cards.csv have been tagged.\n')

## Theft
def tag_for_theft(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Theft" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('cast a spell you don\'t own' in row['text'].lower()
                or 'cast but don\'t own' in row['text'].lower()
                or 'cost to cast this spell, sacrifice' in row['text'].lower()
                or 'control but don\'t own' in row['text'].lower()
                or 'exile top of target player\'s library' in row['text'].lower()
                or 'exile top of each player\'s library' in row['text'].lower()
                or 'gain control of' in row['text'].lower()
                or 'target opponent\'s library' in row['text'].lower()
                or 'that player\'s library' in row['text'].lower()
                or 'you control enchanted creature' in row['text'].lower()
                ):
                tag_type = ['Theft']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        if ('Adarkar Valkyrie' == row['name']
            or 'Captain N\'gathrod' == row['name']
            or 'Hostage Taker' == row['name']
            or 'Siphon Insite' == row['name']
            or 'Thief of Sanity' == row['name']
            or 'Xanathar, Guild Kingpin' == row['name']
            or 'Zara, Renegade Recruiter' == row['name']
            ):
            tag_type = ['Theft']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Theft" cards in {color}_cards.csv have been tagged.\n')
    
## Toughness Matters
def tag_for_toughness(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Toughness Matters" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if (
                'card\'s toughness' in row['text'].lower()
                or 'creature\'s toughness' in row['text'].lower()
                or 'damage equal to its toughness' in row['text'].lower()
                or 'lesser toughness' in row['text'].lower()
                or 'total toughness' in row['text'].lower()
                or 'toughness greater' in row['text'].lower()
                or 'with defender' in row['text'].lower()
                ):
                tag_type = ['Toughness Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        if pd.notna(row['keywords']):
            if ('Defender' in row['keywords']
                ):
                tag_type = ['Toughness Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        if (isinstance(df.at[index, 'power'], int) and isinstance(df.at[index, 'toughness'], int)):
            if row['toughness'] > row['power']:
                tag_type = ['Toughness Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Toughness Matters" cards in {color}_cards.csv have been tagged.\n')

## Topdeck
def tag_for_topdeck(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "Topdeck" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('from the top' in row['text'].lower()
                or 'look at the top' in row['text'].lower()
                or 'reveal the top' in row['text'].lower()
                or 'scries' in row['text'].lower()
                or 'surveils' in row['text'].lower()
                or 'top of your library' in row['text'].lower()
                or 'you scry' in row['text'].lower()
                or 'you surveil' in row['text'].lower()
                ):
                tag_type = ['Topdeck']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['keywords']):
            if ('Miracle' in row['keywords']
                or 'Scry' in row['keywords']
                or 'Surveil' in row['keywords']
                ):
                tag_type = ['Topdeck']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Topdeck" cards in {color}_cards.csv have been tagged.\n')

## X Spells
def tag_for_x_spells(df, color):
    print(f'Tagging cards in {color}_cards.csv that fit the "X Spells" theme.')
    df['manaCost'] = df['manaCost'].astype(str)
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('cost {x} less' in row['text'].lower()
                or 'don\'t lose this' in row['text'].lower()
                or 'don\'t lose unspent' in row['text'].lower()
                or 'lose unused mana' in row['text'].lower()
                or 'unused mana would empty' in row['text'].lower()
                or 'with {x} in its' in row['text'].lower()
                or 'you cast cost {1} less' in row['text'].lower()
                or 'you cast cost {2} less' in row['text'].lower()
                or 'you cast cost {3} less' in row['text'].lower()
                or 'you cast cost {4} less' in row['text'].lower()
                or 'you cast cost {5} less' in row['text'].lower()
                ):
                tag_type = ['X Spells']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if ('{X}' in row['manaCost']
            ):
            tag_type = ['X Spells']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    print(f'"X Spells" cards in {color}_cards.csv have been tagged.\n')

### Interaction
## Overall tag for interaction group
def tag_for_interaction(df, color):
    print(f'Tagging Interaction cards in {color}_cards.csv.\n'
          'Interaction is anything that, well, interacts with the board or stack.\n'
          'This can be Counterspells, Board Wipes, Spot Removal, Combat Tricks, or Protections.\n')
    print('\n===============\n')
    tag_for_counterspells(df, color)
    print('\n==========\n')
    tag_for_board_wipes(df, color)
    print('\n==========\n')
    tag_for_combat_tricks(df, color)
    print('\n==========\n')
    tag_for_protection(df, color)
    print('\n==========\n')
    tag_for_removal(df, color)
    print('\n==========\n')
    
    print(f'Interaction cards have been tagged in {color}_cards.csv.\n')

## Counter spells
def tag_for_counterspells(df, color):
    print(f'Tagging cards in {color}_cards.csv that are Counterspells or care about Counterspells.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('control counters a' in row['text'].lower()
                or 'counter target' in row['text'].lower()
                or 'return target spell' in row['text'].lower()
                or 'then return it to its owner' in row['text'].lower()
                ):
                tag_type = ['Counterspells', 'Interaction', 'Spellslinger', 'Spells Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'Counterspell cards in {color}_cards.csv have been tagged.\n')

## Board Wipes
def tag_for_board_wipes(df, color):
    print(f'Tagging cards in {color}_cards.csv that are Board Wipes or otherwise deal board-wide damage.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        number_list = list(range(1, 101))
        number_list = list(map(str, number_list))
        number_list.append('x')
        
        # Specifically-named cards
        if (
            # Colorless
            'Aetherspouts' == row['name']
            or 'Calamity of the Titans' == row['name']
            or 'Fraying Line' == row['name']
            or 'Living Death' == row['name']
            or 'Living End' == row['name']
            or 'Oblivion Stone' == row['name']
            or 'The Moment' == row['name']
            or 'The Tabernacle at Pendrell Vale' == row['name']
            or 'Ugin, the Spirit Dragon' == row['name']
            or 'Worldslayer' == row['name']
            
            # White
            or 'Ajani, Strength of the Pride' == row['name']
            or 'Cleansing' == row['name']
            or 'Fall of the First Civilization' == row['name']
            or 'Gideon, the Oathsworn' == row['name']
            or 'Hallowed Burial' == row['name']
            or 'Out of Time' == row['name']
            or 'The Eternal Wanderer' == row['name']
            or 'The Night of the Doctor' == row['name']
            or 'Wave of Reckoning' == row['name']
            or 'What Must Be Done' == row['name']
            or 'Winds of Abandon' == row['name']
            
            # Blue
            or 'Cyclonic Rift' == row['name']
            or 'Engulf the Shore' == row['name']
            or 'Hurkyl\'s Final Meditation' == row['name']
            or 'Jin-Gitaxias // The Greath Synthesis' == row['name']
            or 'Kederekt Leviathan' == row['name']
            or 'Profaner of the Dead' == row['name']
            
            # Black
            or 'Blasphemous Edict' == row['name']
            or 'Blood on the Snow' == row['name']
            or 'Curse of the Cabal' == row['name']
            or 'Death Cloud' == row['name']
            or 'Gix\'s Command' == row['name']
            or 'Killing Wave' == row['name']
            or 'Liliana, Death\'s Majesty' == row['name']
            or 'Necroplasm' == row['name']
            or 'Necrotic Hex' == row['name']
            or 'Olivia\'s Wrath' == row['name']
            or 'Sphere of Annihilation' == row['name']
            or 'Swarmyard Massacre' == row['name']
            or 'The Elderspell' == row['name']
            or 'Urborg\'s Justice' == row['name']
            or 'Zombie Apocalypse' == row['name']
            
            # Red
            or 'Breath Weapon' == row['name']
            or 'Caught in the Crossfire' == row['name']
            or 'Chandra, Awakened Inferno' == row['name']
            or 'Draconic Intervention' == row['name']
            or 'Dwarven Catapult' == row['name']
            or 'Evaporate' == row['name']
            or 'Exocrine' == row['name']
            or 'Fiery Cannonade' == row['name']
            or 'Flame Blitz' == row['name']
            or 'Forerunner of the Empire' == row['name']
            or 'Rite of Ruin' == row['name']
            or 'Ronin Cliffrider' == row['name']
            or 'Sarkhan\'s Unsealing' == row['name']
            or 'Sacalding Salamander' == row['name']
            or 'Tectonic Break' == row['name']
            or 'Thoughts of Ruin' == row['name']
            or 'Thundercloud Shaman' == row['name']
            or 'Thunder of Hooves' == row['name']
            or 'Vampires\' Vengeance' == row['name']
            or 'Vandalblast' == row['name']
            or 'Thunder of Hooves' == row['name']
            or 'Warp World' == row['name']
            
            # Green
            or 'Ezuri\'s Predation' == row['name']
            or 'Nylea\'s Intervention' == row['name']
            or 'Spring Cleaning' == row['name']
            or 'Nylea\'s Intervention' == row['name']
            or 'Welcome to . . . // Jurassic Park' == row['name']
            
            # Azorius
            or 'Urza, Planeswalker' == row['name']
            
            # Orzhov
            or 'Magister of Worth' == row['name']
            or 'Necromancer\'s Covenant' == row['name']
            
            # Rakdos
            or 'Angrath, Minotaur Pirate' == row['name']
            or 'Hidetsugu Consumes All' == row['name']
            or 'Void' == row['name']
            or 'Widespread Brutality' == row['name']
            
            # Golgari
            or 'Hazardous Conditions' == row['name']
            
            # Izzet
            or 'Battle of Frost and Fire' == row['name']
            
            # Simic
            or 'The Bears of Littjara' == row['name']
            
            # Naya
            or 'Incandescent Aria' == row['name']
            
            # Mardu
            or 'Piru, the Volatile' == row['name']
            
            ):
            tag_type = ['Board Wipes', 'Interaction']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
        
        
        if pd.notna(row['text']):
            # General non-damage
            if ('destroy all' in row['text'].lower()
                or 'destroy each' in row['text'].lower()
                or 'destroy the rest' in row['text'].lower()
                or 'destroys the rest' in row['text'].lower()
                or 'for each attacking creature, put' in row['text'].lower()
                or 'exile all' in row['text'].lower()
                or 'exile any number' in row['text'].lower()
                or 'exile each' in row['text'].lower()
                or 'exile the rest' in row['text'].lower()
                or 'exiles any number' in row['text'].lower()
                or 'exiles the rest' in row['text'].lower()
                or 'put all attacking creatures' in row['text'].lower()
                or 'put all creatures' in row['text'].lower()
                or 'put all enchantments' in row['text'].lower()
                or 'return all' in row['text'].lower()
                or 'return any number of' in row['text'].lower()
                or 'return each' in row['text'].lower()
                or 'return to their owners\' hands' in row['text'].lower()
                or 'sacrifice all' in row['text'].lower()
                or 'sacrifice each' in row['text'].lower()
                or 'sacrifice that many' in row['text'].lower()
                or 'sacrifice the rest' in row['text'].lower()
                or 'sacrifice this creature unless you pay' in row['text'].lower()
                or 'sacrifices all' in row['text'].lower()
                or 'sacrifices each' in row['text'].lower()
                or 'sacrifices that many' in row['text'].lower()
                or 'sacrifices the creatures' in row['text'].lower()
                or 'sacrifices the rest' in row['text'].lower()
                or 'shuffles all creatures' in row['text'].lower()
                ):
                if ('blocking enchanted' in row['text'].lower()
                    or 'blocking it' in row['text'].lower()
                    or 'blocked by' in row['text'].lower()
                    or f'card exiled with {row['name'].lower()}' in row['text'].lower()
                    or f'cards exiled with {row['name'].lower()}' in row['text'].lower()
                    or 'end the turn' in row['text'].lower()
                    or 'exile all cards from your library' in row['text'].lower()
                    or 'exile all cards from your hand' in row['text'].lower()
                    or 'for each card exiled this way, search' in row['text'].lower()
                    or 'from all graveyards to the battlefield' in row['text'].lower()
                    or 'from all graveyards to their owner' in row['text'].lower()
                    or 'from your graveyard with the same name' in row['text'].lower()
                    or 'from their graveyard with the same name' in row['text'].lower()
                    or 'from their hand with the same name' in row['text'].lower()
                    or 'from their library with the same name' in row['text'].lower()
                    or 'from their graveyard to the battlefield' in row['text'].lower()
                    or 'from their graveyards to the battlefield' in row['text'].lower()
                    or 'from your graveyard with the same name' in row['text'].lower()
                    or 'from your graveyard to the battlefield' in row['text'].lower()
                    or 'from your graveyard to your hand' in row['text'].lower()
                    or 'from your hand with the same name' in row['text'].lower()
                    or 'from your library with the same name' in row['text'].lower()
                    or 'into your hand and exile the rest' in row['text'].lower()
                    or 'into your hand, and exile the rest' in row['text'].lower()
                    or 'it blocked' in row['text'].lower()
                    or 'rest back in any order' in row['text'].lower()
                    or 'reveals their hand' in row['text'].lower()
                    or 'other cards revealed' in row['text'].lower()
                    or 'return them to the battlefield' in row['text'].lower()
                    or 'return each of them to the battlefield' in row['text'].lower()
                    
                    # Excluding targetted
                    or 'destroy target' in row['text'].lower()
                    or 'exile target' in row['text'].lower()
                    
                    # Exclude erroneously matching tags
                    or 'Blink' in theme_tags
                    
                    # Exclude specific matches
                    # Colorless cards
                    or 'Scavenger Grounds' == row['name']
                    or 'Sentinel Totem' == row['name']
                    or 'Sheltered Valley' == row['name']
                    
                    # White cards
                    or 'Brilliant Restoration' == row['name']
                    or 'Calamity\'s Wake' == row['name']
                    or 'Honor the Fallen' == row['name']
                    or 'Hourglass of the Lost' == row['name']
                    or 'Livio, Oathsworn Sentinel' == row['name']
                    or 'Mandate of Peace' == row['name']
                    or 'Morningtide' == row['name']
                    or 'Pure Reflection' == row['name']
                    or 'Rest in Peace' == row['name']
                    or 'Sanctifier en-Vec' == row['name']
                    
                    # Blue cards
                    or 'Arcane Artisan' == row['name']
                    or 'Bazaar of Wonders' == row['name']
                    or 'Faerie Artisans' == row['name']
                    or 'Jace, the Mind Sculptor' == row['name']
                    or 'Mass Polymorph' == row['name']
                    or 'Metallurgic Summonings' == row['name']
                    or 'Paradoxical Outcome' == row['name']
                    or 'Saprazzan Bailiff' == row['name']
                    or 'The Tale of Tamiyo' == row['name']
                    or 'Vodalian War Machine' == row['name']
                    
                    # Black cards
                    or 'Desperate Research' == row['name']
                    or 'Doomsday' == row['name']
                    or 'Drudge Spell' == row['name']
                    or 'Elder Brain' == row['name']
                    or 'Gorex, the Tombshell' == row['name']
                    or 'Grave Consequences' == row['name']
                    or 'Hellcarver Demon' == row['name']
                    or 'Hypnox' == row['name']
                    or 'Kaervek\'s Spite' == row['name']
                    or 'Lich' == row['name']
                    or 'Opposition Agent' == row['name']
                    or 'Phyrexian Negator' == row['name']
                    or 'Phyrexian Totem' == row['name']
                    or 'Prowling Gheistcatcher' == row['name']
                    or 'Sengir Autocrat' == row['name']
                    or 'Shadow of the Enemy' == row['name']
                    or 'Sink into Takenuma' == row['name']
                    or 'Sutured Ghoul' == row['name']
                    or 'Sword-Point Diplomacy' == row['name']
                    or 'Szat\'s Will' == row['name']
                    or 'Tomb of Urami' == row['name']
                    or 'Tombstone Stairwell' == row['name']
                    or 'Yukora, the Prisoner' == row['name']
                    or 'Zombie Mob' == row['name']
                    
                    # Red cards
                    or 'Bomb Squad' in row['name']
                    or 'Barrel Down Sokenzan' == row['name']
                    or 'Explosive Singularity' == row['name']
                    or 'Expose the Culprit' == row['name']
                    or 'Lukka, Coppercoat Outcast' == row['name']
                    or 'March of Reckless Joy' == row['name']
                    or 'Thieves\' Auction' == row['name']
                    or 'Wild-Magic Sorcerer' == row['name']
                    or 'Witchstalker Frenzy' == row['name']
                    
                    # Green Cards
                    or 'Clear the Land' == row['name']
                    or 'Dual Nature' == row['name']
                    or 'Kamahl\'s Will' == row['name']
                    or 'March of Burgeoning Life' == row['name']
                    or 'Moonlight Hunt' == row['name']
                    or 'Nissa\'s Judgment' == row['name']
                    or 'Overlaid Terrain' == row['name']
                    or 'Rambling Possum' == row['name']
                    or 'Saproling Burst' == row['name']
                    or 'Splintering Wind' == row['name']
                    
                    # Orzhov
                    or 'Identity Crisis' == row['name']
                    or 'Kaya\'s Guile' == row['name']
                    or 'Kaya, Geist Hunter' == row['name']
                    
                    # Boros
                    or 'Quintorius Kand' == row['name']
                    or 'Suleiman\'s Legacy' == row['name']
                    or 'Wildfire Awakener' == row['name']
                    
                    # Dimir
                    or 'Ashiok' in row['name']
                    or 'Dralnu, Lich Lord' == row['name']
                    or 'Mnemonic Betrayal' == row['name']
                    
                    # Rakdos
                    or 'Blood for the Blood God!' == row['name']
                    or 'Mount Doom' == row['name']
                    or 'Rakdos Charm' == row['name']
                    
                    # Golgari
                    or 'Skemfar Elderhall' == row['name']
                    or 'Winter, Cynical Opportunist' == row['name']
                    
                    # Izzet
                    or 'Shaun, Father of Synths' == row['name']
                    or 'The Apprentice\'s Folly' == row['name']
                    
                    # Esper
                    or 'The Celestial Toymaker' == row['name']
                    
                    # Grixis
                    or 'Missy' == row['name']
                    or 'Nicol Bolas, the Ravager // Nicol Bolas, the Arisen' == row['name']
                    
                    # Naya
                    or 'Hazezon Tamar' == row['name']
                    
                    # Mardu
                    or 'Extus, Oriq Overlord // Awaken the Blood Avatar' == row['name']
                    
                    ):
                    continue
                else:
                    tag_type = ['Board Wipes', 'Interaction']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
            
            # Number-based
            if pd.notna(row['text']):
                for i in number_list:
                    # Deals damage from 1-100 or X
                    if (f'deals {i}' in row['text'].lower()):
                        if ('blocking it' in row['text'].lower()
                            or 'is blocked' in row['text'].lower()
                            or 'other creature you control' in row['text'].lower()
                            ):
                            continue
                        if ('target' in row['text'].lower() and 'overload' in row['text'].lower()):
                            tag_type = ['Board Wipes', 'Burn', 'Interaction']
                            for tag in tag_type:
                                if tag not in theme_tags:
                                    theme_tags.extend([tag])
                                    df.at[index, 'themeTags'] = theme_tags
                        if ('and each creature' in row['text'].lower()
                            or 'each artifact creature' in row['text'].lower()
                            or 'each creature' in row['text'].lower()
                            or 'each black creature' in row['text'].lower()
                            or 'each blue creature' in row['text'].lower()
                            or 'each green creature' in row['text'].lower()
                            or 'each nonartifact creature' in row['text'].lower()
                            or 'each nonblack creature' in row['text'].lower()
                            or 'each nonblue creature' in row['text'].lower()
                            or 'each nongreen creature' in row['text'].lower()
                            or 'each nonred creature' in row['text'].lower()
                            or 'each nonwhite creature' in row['text'].lower()
                            or 'each red creature' in row['text'].lower()
                            or 'each tapped creature' in row['text'].lower()
                            or 'each untapped creature' in row['text'].lower()
                            or 'each white creature' in row['text'].lower()
                            or 'to each attacking creature' in row['text'].lower()
                            or 'to each creature' in row['text'].lower()
                            or 'to each other creature' in row['text'].lower()
                            ):
                            tag_type = ['Board Wipes', 'Burn', 'Interaction']
                            for tag in tag_type:
                                if tag not in theme_tags:
                                    theme_tags.extend([tag])
                                    df.at[index, 'themeTags'] = theme_tags
                    
                    # -X/-X effects
                    if (f'creatures get -{i}/-{i}' in row['text'].lower()
                        or f'creatures get +{i}/-{i}' in row['text'].lower()
                        or f'creatures of that type -{i}/-{i}' in row['text'].lower()
                        or f'each creature gets -{i}/-{i}' in row['text'].lower()
                        or f'each other creature gets -{i}/-{i}' in row['text'].lower()
                        or f'control get -{i}/-{i}' in row['text'].lower()
                        or f'control gets -{i}/-{i}' in row['text'].lower()
                        or f'controls get -{i}/-{i}' in row['text'].lower()
                        or f'creatures get -0/-{i}' in row['text'].lower()
                        or f'tokens get -{i}/-{i}' in row['text'].lower()
                        or f'put a -{i}/-{i} counter on each' in row['text'].lower()
                        or f'put {i} -1/-1 counters on each' in row['text'].lower()
                        or f'tokens get -{i}/-{i}' in row['text'].lower()
                        or f'type of your choice get -{i}/-{i}' in row['text'].lower()
                        ):
                        if ('you control get -1/-1' in row['text'].lower()
                            ):
                            continue
                        tag_type = ['Board Wipes', 'Interaction']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
                
                # Deals non-definite damage equal to
                if ('deals damage equal to' in row['text'].lower()
                    or 'deals that much damage to' in row['text'].lower()
                    or 'deals damage to' in row['text'].lower()
                    ):
                    #if ():
                    #    continue
                    if ('each artifact creature' in row['text'].lower()
                        or 'each creature' in row['text'].lower()
                        or 'each black creature' in row['text'].lower()
                        or 'each blue creature' in row['text'].lower()
                        or 'each green creature' in row['text'].lower()
                        or 'each nonartifact creature' in row['text'].lower()
                        or 'each nonblack creature' in row['text'].lower()
                        or 'each nonblue creature' in row['text'].lower()
                        or 'each nongreen creature' in row['text'].lower()
                        or 'each nonred creature' in row['text'].lower()
                        or 'each nonwhite creature' in row['text'].lower()
                        or 'each red creature' in row['text'].lower()
                        or 'each tapped creature' in row['text'].lower()
                        or 'each untapped creature' in row['text'].lower()
                        or 'each white creature' in row['text'].lower()
                        or 'to each attacking creature' in row['text'].lower()
                        or 'to each creature' in row['text'].lower()
                        or 'to each other creature' in row['text'].lower()
                        ):
                        tag_type = ['Board Wipes', 'Burn', 'Interaction']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
    
    print(f'"Board Wipe" cards in {color}_cards.csv have been tagged.\n')

## Combat Tricks
def tag_for_combat_tricks(df, color):
    print(f'Tagging cards in {color}_cards.csv for Combat Tricks.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        number_list = list(range(0, 11))
        number_list = list(map(str, number_list))
        number_list.append('x')
        if pd.notna(row['text']):
            if 'remains tapped' in row['text']:
                continue
            if ('Assimilate Essence' == row['name']
                or 'Mantle of Leadership' == row['name']
                or 'Michiko\'s Reign of Truth // Portrait of Michiko' == row['name']):
                continue
            for number in number_list:
                # Tap abilities
                if (f'{{t}}: target creature gets +0/+{number}' in row['text'].lower()
                    or f'{{t}}: target creature gets +{number}/+0' in row['text'].lower()
                    or f'{{t}}: target creature gets +{number}/+{number}' in row['text'].lower()
                    or f'{{t}}: target creature you control gets +{number}/+{number}' in row['text'].lower()
                    ):
                    # Exclude sorcery speed
                    if ('only as a sorcery' in row['text'].lower()):
                        continue
                    tag_type = ['Combat Tricks', 'Interaction']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
                for number_2 in number_list:
                    if (f'{{t}}: target creature gets +{number}/+{number_2}' in row['text'].lower()
                        or f'{{t}}: target creature gets +{number}/+{number}' in row['text'].lower()
                        ):
                        if ('only as a sorcery' in row['text'].lower()):
                        # Exclude sorcery speed
                            continue
                        tag_type = ['Combat Tricks', 'Interaction']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
                    
                # Flash effects
                if 'Flash' in theme_tags:
                    if (f'chosen type get +{number}/+{number}' in row['text'].lower()
                        or f'creature gets +{number}/+{number}' in row['text'].lower()
                        or f'creatures get +{number}/+{number}' in row['text'].lower()
                        or f'you control gets +{number}/+{number}' in row['text'].lower()
                        ):
                        tag_type = ['Combat Tricks', 'Interaction']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
                    for number_2 in number_list:
                        if (f'chosen type get +{number}/+{number_2}' in row['text'].lower()
                            or f'creature gets +{number}/+{number_2}' in row['text'].lower()
                            or f'creatures get +{number}/+{number_2}' in row['text'].lower()
                            or f'you control gets +{number}/+{number_2}' in row['text'].lower()
                            ):
                            tag_type = ['Combat Tricks', 'Interaction']
                            for tag in tag_type:
                                if tag not in theme_tags:
                                    theme_tags.extend([tag])
                                    df.at[index, 'themeTags'] = theme_tags
                                    
                # Instant speed effects
                if row['type'] == 'Instant':
                    if (
                        # Positive values
                        f'chosen type get +{number}/+{number}' in row['text'].lower()
                        or f'creature gets +{number}/+{number}' in row['text'].lower()
                        or f'creatures get +{number}/+{number}' in row['text'].lower()
                        or f'each get +{number}/+{number}' in row['text'].lower()
                        or f'it gets +{number}/+{number}' in row['text'].lower()
                        or f'you control gets +{number}/+{number}' in row['text'].lower()
                        or f'you control get +{number}/+{number}' in row['text'].lower()
                        
                        # Negative values
                        or f'chosen type get -{number}/-{number}' in row['text'].lower()
                        or f'creature gets -{number}/-{number}' in row['text'].lower()
                        or f'creatures get -{number}/-{number}' in row['text'].lower()
                        or f'each get -{number}/-{number}' in row['text'].lower()
                        or f'it gets -{number}/-{number}' in row['text'].lower()
                        or f'you control gets -{number}/-{number}' in row['text'].lower()
                        or f'you control get -{number}/-{number}' in row['text'].lower()
                        
                        # Mixed values
                        or f'chosen type get +{number}/-{number}' in row['text'].lower()
                        or f'creature gets +{number}/-{number}' in row['text'].lower()
                        or f'creatures get +{number}/-{number}' in row['text'].lower()
                        or f'each get +{number}/-{number}' in row['text'].lower()
                        or f'it gets +{number}/-{number}' in row['text'].lower()
                        or f'you control gets +{number}/-{number}' in row['text'].lower()
                        or f'you control get +{number}/-{number}' in row['text'].lower()
                        
                        or f'chosen type get -{number}/+{number}' in row['text'].lower()
                        or f'creature gets -{number}/+{number}' in row['text'].lower()
                        or f'creatures get -{number}/+{number}' in row['text'].lower()
                        or f'each get -{number}/+{number}' in row['text'].lower()
                        or f'it gets -{number}/+{number}' in row['text'].lower()
                        or f'you control gets -{number}/+{number}' in row['text'].lower()
                        or f'you control get -{number}/+{number}' in row['text'].lower()
                        ):
                        tag_type = ['Combat Tricks', 'Interaction']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
                    for number_2 in number_list:
                        if (
                            # Positive Values
                            f'chosen type get +{number}/+{number_2}' in row['text'].lower()
                            or f'creature gets +{number}/+{number_2}' in row['text'].lower()
                            or f'creatures get +{number}/+{number_2}' in row['text'].lower()
                            or f'each get +{number}/+{number_2}' in row['text'].lower()
                            or f'it gets +{number}/+{number_2}' in row['text'].lower()
                            or f'you control gets +{number}/+{number_2}' in row['text'].lower()
                            or f'you control get +{number}/+{number_2}' in row['text'].lower()
                            
                            # Negative values
                            or f'chosen type get -{number}/-{number_2}' in row['text'].lower()
                            or f'creature gets -{number}/-{number_2}' in row['text'].lower()
                            or f'creatures get -{number}/-{number_2}' in row['text'].lower()
                            or f'each get -{number}/-{number_2}' in row['text'].lower()
                            or f'it gets -{number}/-{number_2}' in row['text'].lower()
                            or f'you control gets -{number}/-{number_2}' in row['text'].lower()
                            or f'you control get -{number}/-{number_2}' in row['text'].lower()
                            
                            # Mixed values
                            or f'chosen type get +{number}/-{number_2}' in row['text'].lower()
                            or f'creature gets +{number}/-{number_2}' in row['text'].lower()
                            or f'creatures get +{number}/-{number_2}' in row['text'].lower()
                            or f'each get +{number}/-{number_2}' in row['text'].lower()
                            or f'it gets +{number}/-{number_2}' in row['text'].lower()
                            or f'you control gets +{number}/-{number_2}' in row['text'].lower()
                            or f'you control get +{number}/-{number_2}' in row['text'].lower()
                            
                            or f'chosen type get -{number}/+{number_2}' in row['text'].lower()
                            or f'creature gets -{number}/+{number_2}' in row['text'].lower()
                            or f'creatures get -{number}/+{number_2}' in row['text'].lower()
                            or f'each get -{number}/+{number_2}' in row['text'].lower()
                            or f'it gets -{number}/+{number_2}' in row['text'].lower()
                            or f'you control gets -{number}/+{number_2}' in row['text'].lower()
                            or f'you control get -{number}/+{number_2}' in row['text'].lower()
                            ):
                            tag_type = ['Combat Tricks', 'Interaction']
                            for tag in tag_type:
                                if tag not in theme_tags:
                                    theme_tags.extend([tag])
                                    df.at[index, 'themeTags'] = theme_tags
            
            if row['type'] == 'Instant':
                if (
                    '+1/+1 counter' in row['text'].lower()
                    or 'bolster' in row['text'].lower()
                    or 'double strike' in row['text'].lower()
                    or 'first strike' in row['text'].lower()
                    or 'has base power and toughness' in row['text'].lower()
                    or 'untap all creatures' in row['text'].lower()
                    or 'untap target creature' in row['text'].lower()
                    or 'with base power and toughness' in row['text'].lower()
                    ):
                    tag_type = ['Combat Tricks', 'Interaction']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
            
            if 'Flash' in theme_tags:
                if (
                    'bolster' in row['text'].lower()
                    or 'untap all creatures' in row['text'].lower()
                    or 'untap target creature' in row['text'].lower()
                    ):
                    tag_type = ['Combat Tricks', 'Interaction']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
                if 'Enchantment' in row['type']:
                    if (
                        '+1/+1 counter' in row['text'].lower()
                        or 'double strike' in row['text'].lower()
                        or 'first strike' in row['text'].lower()
                        ):
                        tag_type = ['Combat Tricks', 'Interaction']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
        
    print(f'Combat Tricks in {color}_cards.csv have been tagged.\n')
    
## Protection/Safety spells
def tag_for_protection(df, color):
    print(f'Tagging cards in {color}_cards.csv that provide or have some form of protection (i.e. Protection, Indestructible, Hexproof, etc...).')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        named_exclusions = ['Out of Time', 'The War Doctor']
        if (row['name'] in named_exclusions
            ):
            continue
        if pd.notna(row['text']):
            if ('has indestructible' in row['text'].lower()
                or 'has indestructible' in row['text'].lower()
                or 'has protection' in row['text'].lower()
                or 'has shroud' in row['text'].lower()
                or 'has ward' in row['text'].lower()
                or 'have indestructible' in row['text'].lower()
                or 'have indestructible' in row['text'].lower()
                or 'have protection' in row['text'].lower()
                or 'have shroud' in row['text'].lower()
                or 'have ward' in row['text'].lower()
                or 'hexproof from' in row['text'].lower()
                or 'gain hexproof' in row['text'].lower()
                or 'gain indestructible' in row['text'].lower()
                or 'gain protection' in row['text'].lower()
                or 'gain shroud' in row['text'].lower()
                or 'gain ward' in row['text'].lower()
                or 'gains hexproof' in row['text'].lower()
                or 'gains indestructible' in row['text'].lower()
                or 'gains protection' in row['text'].lower()
                or 'gains shroud' in row['text'].lower()
                or 'gains ward' in row['text'].lower()
                or 'phases out' in row['text'].lower()
                or 'protection from' in row['text'].lower()
                ):
                tag_type = ['Interaction', 'Protection']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['keywords']):
            if ('Hexproof' in row['keywords']
                or 'Indestructible' in row['keywords']
                or 'Protection' in row['keywords']
                or 'Shroud' in row['keywords']
                or 'Ward' in row['keywords']
                ):
                tag_type = ['Interaction', 'Protection']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'Protection cards in {color}_cards.csv have been tagged.\n')

## Spot removal
def tag_for_removal(df, color):
    print(f'Tagging cards in {color}_cards.csv that Do some form of spot Removal.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('destroy target' in row['text'].lower()
                or 'destroys target' in row['text'].lower()
                or 'exile target' in row['text'].lower()
                or 'exiles target' in row['text'].lower()
                or 'sacrifices target' in row['text'].lower()
                
                ):
                tag_type = ['Interaction', 'Removal']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['keywords']):
            if ('' in row['keywords'].lower()
                ):
                tag_type = []
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'Removal cards in {color}_cards.csv have been tagged.\n')


#for color in colors:
#    load_dataframe(color)
start_time = pd.Timestamp.now()
#regenerate_csv_by_color('colorless')
load_dataframe('colorless')
duration = (pd.Timestamp.now() - start_time).total_seconds()
logging.info(f'Tagged cards in {duration:.2f}s')