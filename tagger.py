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
    #tag_for_artifacts(df, color)
    #print('\n====================\n')
    #tag_for_enchantments(df, color)
    #print('\n====================\n')
    #tag_for_exile_matters(df, color)
    #print('\n====================\n')
    #tag_for_tokens(df, color)
    #print('\n====================\n')
    #tag_for_life_matters(df, color)
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

def create_text_mask(df: pd.DataFrame, pattern: str) -> pd.Series:
    """Create a boolean mask for rows where text matches a pattern.
    
    Args:
        df: The dataframe to search
        pattern: Regex pattern to match
        
    Returns:
        Boolean series indicating matching rows
    """
    return df['text'].str.contains(pattern, case=False, na=False, regex=True)

def create_keyword_mask(df: pd.DataFrame, keywords: Union[str, List[str]]) -> pd.Series:
    """Create a boolean mask for rows with matching keywords.
    
    Args:
        df: The dataframe to search
        keywords: Keyword or list of keywords to match
        
    Returns:
        Boolean series indicating matching rows
    """
    if isinstance(keywords, str):
        keywords = [keywords]
    return df['keywords'].str.contains('|'.join(keywords), case=False, na=False)

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
        cost_mask = create_text_mask(df, PATTERN_GROUPS['cost_reduction'])

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
        named_mask = df['name'].isin(named_cards)

        # Combine masks
        final_mask = cost_mask | named_mask

        # Apply tags
        utility.apply_tag_vectorized(df, final_mask, ['Cost Reduction'])

        # Add spellslinger tags for noncreature spell cost reduction
        spell_mask = final_mask & create_text_mask(df, r"Sorcery|Instant|noncreature")
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
    draw_mask = df['text'].str.contains('|'.join(draw_patterns), case=False, na=False)

    # Create exclusion mask for conditional effects
    excluded_tags = settings.DRAW_RELATED_TAGS
    tag_mask = utility.create_tag_mask(df, excluded_tags)

    # Create text-based exclusions
    text_patterns = settings.DRAW_EXCLUSION_PATTERNS
    text_mask = df['text'].str.contains('|'.join(text_patterns), case=False, na=False)

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
    text_mask = df['text'].str.contains('|'.join(text_patterns), case=False, na=False)

    # Create name-based exclusions
    excluded_names = ['relic vial', 'vexing bauble']
    name_mask = df['name'].str.lower().isin(excluded_names)

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
    trigger_mask = df['text'].str.contains('|'.join(trigger_patterns), case=False, na=False)

    # Add other trigger patterns
    other_patterns = ['created a token', 'draw a card for each']
    other_mask = df['text'].str.contains('|'.join(other_patterns), case=False, na=False)

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
        draw_mask = create_conditional_draw_effect_mask(df)

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
    
    has_draw = df['text'].str.contains('|'.join(draw_patterns), case=False, na=False)
    has_discard = df['text'].str.contains('|'.join(discard_patterns), case=False, na=False)
    
    return ~has_other_loot & has_draw & has_discard

def create_connive_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with connive effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have connive effects
    """
    has_keyword = df['keywords'].str.contains('Connive', case=False, na=False)
    has_text = df['text'].str.contains('connives?', case=False, na=False)
    return has_keyword | has_text

def create_cycling_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with cycling effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have cycling effects
    """
    has_keyword = df['keywords'].str.contains('Cycling', case=False, na=False)
    has_text = df['text'].str.contains('cycling', case=False, na=False)
    return has_keyword | has_text

def create_blood_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with blood token effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have blood token effects
    """
    return df['text'].str.contains('blood token', case=False, na=False)

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
        excluded_types = create_text_mask(df, 'Land|Equipment')
        excluded_keywords = create_keyword_mask(df, ['Channel', 'Cycling', 'Connive', 'Learn', 'Ravenous'])
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
        has_draw = create_text_mask(df, PATTERN_GROUPS['draw'])
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
    base_mask = df['text'].str.contains(all_patterns, case=False, na=False, regex=True)

    # Add mask for specific card numbers
    number_patterns = [f'draw {num} card' for num in num_to_search]
    number_mask = df['text'].str.contains('|'.join(number_patterns), case=False, na=False)

    # Add mask for non-specific numbers
    nonspecific_mask = df['text'].str.contains('draw that many plus|draws that many plus', case=False, na=False)

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
    text_mask = df['text'].str.contains('|'.join(text_patterns), case=False, na=False)

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
        specific_cards_mask = df['name'].str.contains('sylvan library', case=False, na=False)

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
def create_wheels_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with wheel-related text effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have wheel-related text effects
    """
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

    # Create pattern string
    pattern = '|'.join(wheel_patterns)

    # Create mask
    return df['text'].str.contains(pattern, case=False, na=False, regex=True)

def create_wheels_name_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with wheel-related names.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have wheel-related names
    """
    # Define specific card names
    wheel_cards = [
        'arcane denial', 'bloodchief ascension', 'dark deal', 'elenda and azor', 'elixir of immortality',
        'forced fruition', 'glunch, the bestower', 'kiora the rising tide', 'kynaios and tiro of meletis',
        'library of leng','loran of the third path', 'mr. foxglove', 'raffine, scheming seer',
        'sauron, the dark lord', 'seizan, perverter of truth', 'triskaidekaphile', 'twenty-toed toad',
        'waste not', 'wedding ring', 'whispering madness'
    ]

    return df['name'].str.lower().isin(wheel_cards)

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
        text_mask = create_wheels_text_mask(df)
        name_mask = create_wheels_name_mask(df)

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
def tag_for_artifacts(df, color):
    # Iterate through each {color}_cards.csv file to find cards that care about artifacts
    print(f'Tagging "Artifact"-related cards in {color}_cards.csv.\n\n')
    print('\n===============\n')
    tag_for_artifact_tokens(df, color)
    print('\n==========\n')
    tag_equipment(df, color)
    print('\n==========\n')
    tag_vehicles(df, color)
    print('\n==========\n')
    tag_for_artifact_triggers(df, color)
    
    # Overwrite file with artifacts matter tag added
    print(f'"Artifacts Matter" cards tagged in {color}_cards.csv.\n')

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
    name_exclusions = df['name'].str.lower().isin(excluded_cards)

    # Create text pattern matches
    create_pattern = r'create|put'
    has_create = df['text'].str.contains(create_pattern, case=False, na=False)

    token_patterns = [
        'artifact creature token',
        'artifact token',
        'construct artifact',
        'copy of enchanted artifact',
        'copy of target artifact',
        'copy of that artifact'
    ]
    has_token = df['text'].str.contains('|'.join(token_patterns), case=False, na=False)

    # Named cards that create artifact tokens
    named_cards = [
        'bloodforged battle', 'court of vantress', 'elmar, ulvenwald informant',
        'faerie artisans', 'feldon of the third path', 'lenoardo da vinci',
        'march of progress', 'nexus of becoming', 'osgir, the reconstructor',
        'prototype portal', 'red sun\'s twilight', 'saheeli, the sun\'s brilliance',
        'season of weaving', 'shaun, father of synths', 'sophia, dogged detective',
        'vaultborn tyrant', 'wedding ring'
    ]
    named_matches = df['name'].str.lower().isin(named_cards)

    # Exclude fabricate cards
    has_fabricate = df['text'].str.contains('fabricate', case=False, na=False)

    return (has_create & has_token & ~name_exclusions & ~has_fabricate) | named_matches

def create_predefined_artifact_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that create predefined artifact tokens.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards create predefined artifact tokens
    """
    # Create base mask for 'create' text
    has_create = df['text'].str.contains('create', case=False, na=False)

    # Create masks for each token type
    token_masks = []
    for token in settings.artifact_tokens:
        token_mask = df['text'].str.contains(token.lower(), case=False, na=False)

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
    return df['text'].str.contains('fabricate', case=False, na=False)

## Artifact Triggers
def tag_for_artifact_triggers(df, color):
    print(f'Tagging cards in {color}_cards.csv that care about artifacts.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        
        # Tagging for triggered abilities, replacement effects, or other
        # effects that care about artifacts (i.e. Metalcraft)
        if pd.notna(row['text']):
            if ('abilities of artifact' in row['text'].lower()
                or 'ability of artifact' in row['text'].lower()
                or 'affinity for artifacts' in row['text'].lower()
                or 'all artifact' in row['text'].lower()
                or 'another artifact' in row['text'].lower()
                or 'another target artifact' in row['text'].lower()
                or 'are artifacts in addition' in row['text'].lower()
                or 'artifact' in row['text'].lower()
                or 'artifact card' in row['text'].lower()
                or 'artifact creature you control' in row['text'].lower()
                or 'artifact creatures you control' in row['text'].lower()
                or 'artifact enters' in row['text'].lower()
                or 'artifact spells as though they had flash' in row['text'].lower()
                or 'artifact spells you cast' in row['text'].lower()
                or 'artifact with the highest mana value' in row['text'].lower()
                or 'artifact you control' in row['text'].lower()
                or 'artifacts you control' in row['text'].lower()
                or 'cast an artifact' in row['text'].lower()
                or 'choose an artifact' in row['text'].lower()
                or 'copy of any artifact' in row['text'].lower()
                or 'each artifact' in row['text'].lower()
                or 'mana cost among artifact' in row['text'].lower()
                or 'mana value among artifact' in row['text'].lower()
                or 'metalcraft' in row['text'].lower()
                or 'number of artifacts' in row['text'].lower()
                or 'number of other artifacts' in row['text'].lower()
                or 'number of tapped artifacts' in row['text'].lower()
                or 'number of artifact' in row['text'].lower()
                or 'prowess' in row['text'].lower()
                or 'search your library for an artifact' in row['text'].lower()
                or 'target artifact' in row['text'].lower()
                or 'whenever a nontoken artifact' in row['text'].lower()
                or 'whenever an artifact' in row['text'].lower()
                or 'whenever another nontoken artifact' in row['text'].lower()
                or 'whenever one or more artifact' in row['text'].lower()
                or 'whenever you cast a noncreature' in row['text'].lower()
                or 'whenever you cast an artifact' in row['text'].lower()
                ):
                tag_type = ['Artifacts Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
    print(f'Cards in {color}_cards.csv that care about other artifacts have been tagged.\n')

## Equipment
def tag_equipment(df, color):
    # Iterate through each {color}_cards.csv file to find equipment cards
    # Also check for cards that care about equipments
    # Tag for equipments
    print(f'Tagging cards in {color}_cards.csv that have the "Equipment" type.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if 'Equipment' in row['type']:
                tag_type = ['Equipment', 'Equipment Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    
    # Tag for cares about equipment
    print(f'Tagging cards in {color}_cards.csv that care about Equipment.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('equipment' in row['text'].lower()
                or 'equipped' in row['text'].lower()
                or 'modified' in row['text'].lower()
                
                # Specifically named cards
                or 'alexios, deimos of kosmos' in row['name'].lower()
                or 'kosei, penitent warlord' in row['name'].lower()
                ):
                tag_type = ['Artifacts Matter', 'Equipment Matters', 'Voltron']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
    
    # Overwrite file with equipment tag added
    print(f'\nCards that care about equipment in {color}_cards.csv have been tagged.\n')

## Vehicles
def tag_vehicles(df, color):
    # Iterate through each {color}_cards.csv file to find Vehicle cards
    # Also check for cards that care about Vehicles
    # Tag for Vehicles
    print(f'Tagging cards in {color}_cards.csv that have the "Vehicle" type.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if ('Pilot' in row['type']):
            tag_type = ['Equipment', 'Equipment Matters']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['text']):
            if ('Vehicle' in row['type']
                or 'crew' in row['text'].lower()
                or 'noncreature artifact becomes' in row['text'].lower()
                or 'noncreature artifacts you control become' in row['text'].lower()
                or 'Vehicle' in row['text']
                or 'vehicles you control become' in row['text'].lower()
                ):
                tag_type = ['Equipment', 'Equipment Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    # Tag for cares about Vehicles
    print(f'Tagging cards in {color}_cards.csv that care about Vehicles.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('equipment' in row['text'].lower()
                or 'equipped' in row['text'].lower()
                or 'modified' in row['text'].lower()
                ):
                tag_type = ['Artifacts Matter', 'Vehicles']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Specifically named cards
        if ('alexios, deimos of kosmos' in row['name'].lower()
            or 'kosei, penitent warlord' in row['name'].lower()
            ):
            tag_type = ['Artifacts Matter', 'Vehicles']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    # Overwrite file with vehicles tag added
    print(f'Cards that care about Vehicles in {color}_cards.csv have been tagged.\n')

### Enchantments
def tag_for_enchantments(df, color):
    # Iterate through each {color}_cards.csv file to find enchantment cards
    # Also check for cards that care about enchantments
    print(f'Tagging "Enchantment Matter" themed cards in {color}_cards.csv.\n')
    print('\n===============\n')
    tag_for_enchantment_tokens(df, color)
    print('\n==========\n')
    tag_for_enchantments_matter(df, color)
    print('\n==========\n')
    tag_auras(df, color)
    print('\n==========\n')
    tag_constellation(df, color)
    print('\n==========\n')
    tag_sagas(df, color)
    print('\n==========\n')
    tag_cases(df, color)
    print('\n==========\n')
    tag_rooms(df, color)
    print('\n==========\n')
    tag_backgrounds(df, color)
    print('\n==========\n')
    tag_shrines(df, color)
    print(f'"Enchantments Matter" themed cards in {color}_cards.csv have been tagged.\n')

## Enchantment tokens
def tag_for_enchantment_tokens(df, color):
    print(f'Settings enchantment token tags on {color}_cards.csv.\n')
    
    # Tag for enchantment token creation
    print(f'Tagging cards in {color}_cards.csv that create or modify creation of Enchantment tokens.\n')
    
    tag_for_generic_enchantment_tokens(df, color)
    print('\n=====\n')
    tag_for_predefined_enchantment_tokens(df, color)
    print('\n=====\n')
    print(f'Cards in {color}_cards.csv that create or modify creation of Enchantment tokens have been tagged.')
    
    # Overwrite file with enchantment tag added
    print(f'Enchantment token-related cards tagged in {color}_cards.csv.\n')

def tag_for_generic_enchantment_tokens(df, color):
    print('Checking for non-predefined token generators.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('create' in row['text'].lower()
                or 'put' in row['text'].lower()
                ):
                if ('copy of enchanted enchantment' in row['text'].lower()
                    or 'copy of target enchantment' in row['text'].lower()
                    or 'copy of that enchantment' in row['text'].lower()
                    or 'enchantment creature token' in row['text'].lower()
                    or 'enchantment token' in row['text'].lower()):
                    tag_type = ['Enchantment Tokens', 'Enchantments Matter']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
        
                
        # Specifically named cards 
        if ('court of vantress' in row['name'].lower()
            or 'felhide spiritbinder' in row['name'].lower()
            or 'hammer of purphoros' in row['name'].lower()
            ):
            tag_type = ['Enchantment Tokens', 'Enchantments Matter']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    print(f'\nCards in {color}_cards.csv that are non-predefined token generators have been tagged.\n')

def tag_for_predefined_enchantment_tokens(df, color):
    # Tagging for roles and shards
    print('Checking for predefined token (i.e. Roles or Shard) generators.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('create' in row['text'].lower()):
                for enchantment_token in enchantment_tokens:
                    if (f'{enchantment_token.lower()}' in row['text'].lower()):
                        tag_type = ['Enchantment Tokens', f'{enchantment_token} Tokens', 'Enchantments Matter']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
            
    print(f'\nCards in {color}_cards.csv that are predefined token generators have been tagged.\n')
    
## General enchantments matter
def tag_for_enchantments_matter(df, color):
    # Tag for enchantments matter
    print(f'Tagging cards in {color}_cards.csv that care about enchantments.')
    
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        # Excluding false positive
        if ('luxa river shrine' in row['name']
            ):
            continue
        
        # Tagging based on triggered effects or other effects that care about enchantments
        if pd.notna(row['text']):
            if ('abilities of enchantment' in row['text'].lower()
                or 'ability of enchantment' in row['text'].lower()
                or 'all artifact and enchantment' in row['text'].lower()
                or 'all enchantment' in row['text'].lower()
                or 'another enchantment' in row['text'].lower()
                or 'another target enchantment' in row['text'].lower()
                or 'are enchantments in addition' in row['text'].lower()
                or 'bestow' in row['text'].lower()
                or 'cast an enchantment' in row['text'].lower()
                or 'choose an enchantment' in row['text'].lower()
                or 'constellation' in row['text'].lower()
                or 'copy of any enchantment' in row['text'].lower()
                or 'each enchantment' in row['text'].lower()
                or 'eerie' in row['text'].lower()
                or 'enchantment' in row['text'].lower()
                or 'enchantment card' in row['text'].lower()
                or 'enchantment creature you control' in row['text'].lower()
                or 'enchantment creatures you control' in row['text'].lower()
                or 'enchantment enters' in row['text'].lower()
                or 'enchantment spells as though they had flash' in row['text'].lower()
                or 'enchantment spells you cast' in row['text'].lower()
                or 'enchantment with the highest mana value' in row['text'].lower()
                or 'enchantment you control' in row['text'].lower()
                or 'enchantments you control' in row['text'].lower()
                or 'mana cost among enchantment' in row['text'].lower()
                or 'mana value among enchantment' in row['text'].lower()
                or 'modified creature you control' in row['text'].lower()
                or 'number of aura' in row['text'].lower()
                or 'number of enchantment' in row['text'].lower()
                or 'other enchantment' in row['text'].lower()
                or 'return an enchantment' in row['text'].lower()
                or 'search your library for an artifact or enchantment' in row['text'].lower()
                or 'search your library for an aura' in row['text'].lower()
                or 'search your library for an enchantment' in row['text'].lower()
                or 'shrine' in row['text'].lower()
                or 'target enchantment' in row['text'].lower()
                or 'whenever a nontoken enchantment' in row['text'].lower()
                or 'wehenver an enchantment' in row['text'].lower()
                or 'whenever an aura' in row['text'].lower()
                or 'whenever another nontoken enchantment' in row['text'].lower()
                or 'whenever one or more enchantment' in row['text'].lower()
                or 'whenever you cast a noncreature' in row['text'].lower()
                or 'whenever you cast an artifact or enchantment' in row['text'].lower()
                or 'whenever you cast an enchantment' in row['text'].lower()
                or 'you may cast aura' in row['text'].lower()
                ):
                tag_type = ['Enchantments Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
    print(f'Cards in {color}_cards.csv that care about other enchantments have been tagged.')

## Aura
def tag_auras(df, color):
    # Iterate through each {color}_cards.csv file to find aura cards
    # Also check for cards that care about auras
    # Tag for auras
    print(f'Tagging cards in {color}_cards.csv that have the "Aura" type.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if 'Aura' in row['type']:
                tag_type = ['Auras', 'Auras Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags

    # Tag for cares about aura
    print(f'Tagging cards in {color}_cards.csv that care about "Auras".')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('aura' in row['text'].lower()
                or 'enchanted creature' in row['text'].lower()
                or 'modified' in row['text'].lower()
                or 'equipped' in row['text'].lower()
                or 'aura enters' in row['text'].lower()
                or 'aura you control enters' in row['text'].lower()
                ):
                tag_type = ['Auras', 'Enchantments Matter', 'Voltron']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags

        # Specifically named cards
        if ('calix, guided by fate' in row['name'].lower()
            or 'gylwain, casting director' in row['name'].lower()
            or 'ivy, gleeful spellthief' in row['name'].lower()
            or 'killian, ink duelist' in row['name'].lower()
            ):
            tag_type = ['Auras', 'Enchantments Matter']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags

    # Overwrite file with Aura tag added
    logging.info(f'Cards that have or care about "Aura" in {color}_cards.csv have been tagged.')

## Constellation
def tag_constellation(df, color):
    # Iterate through each {color}_cards.csv file to find aura cards
    # Also check for cards that care about auras
    # Tag for auras
    print(f'Tagging cards in {color}_cards.csv that have "Constellation".')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            continue
        if pd.notna(row['keywords']):
            if ('Constellation' in row['keywords'].lower()
                ):
                tag_type = ['Constellation', 'Enchantments Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'Cards with "Constellation" in {color}_cards.csv have been tagged.\n')

## Sagas
def tag_sagas(df, color):
    # Iterate through each {color}_cards.csv file to find saga cards
    print(f'Tagging cards in {color}_cards.csv that have the "Saga" type.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if 'Saga' in row['type']:
            tag_type = ['Enchantments Matter', 'Sagas Matter']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    # Tag for cares about Sagas
    print(f'Tagging cards in {color}_cards.csv that care about "Sagas".')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('Saga' in row['text']
                or 'put a Saga' in row['text'].lower()
                or 'final chapter' in row['text'].lower()
                or 'lore counter' in row['text'].lower()
                ):
                tag_type = ['Enchantments Matter', 'Sagas Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
    # Overwrite file with Saga tag added
    print(f'Cards that are or care about "Sagas" in {color}_cards.csv have been tagged.\n')

## Cases
def tag_cases(df, color):
    # Iterate through each {color}_cards.csv file to find case cards
    # Also check for cards that care about cases
    # Tag for Cases
    print(f'Tagging cards in {color}_cards.csv that have the "Case" type.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if 'Case' in row['type']:
            tag_type = ['Cases Matter', 'Enchantments Matter']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    # Tag for cares about Cases
    print(f'Tagging cards in {color}_cards.csv that care about "Cases".')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('solve a case' in row['text'].lower()
                ):
                tag_type = ['Cases Matter', 'Enchantments Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    # Overwrite file with aura tag added
    print(f'Cards that are or care about "Cases" in {color}_cards.csv have been tagged.\n')

## Rooms
def tag_rooms(df, color):
    # Iterate through each {color}_cards.csv file to find Room cards
    # Also check for cards that care about Rooms
    # Tag for Rooms
    print(f'Tagging cards in {color}_cards.csv that have the "Room" type.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if 'Room' in row['type']:
            tag_type = ['Enchantments Matter', 'Rooms Matter']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    # Tag for cares about Cases
    print(f'Tagging cards in {color}_cards.csv that care about "Rooms".')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['keywords']):
            if ('Eerie' in row['keywords']):
                tag_type = ['Enchantments Matter', 'Rooms Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['text']):
            if ('target room' in row['text'].lower()
                ):
                tag_type = ['Enchantments Matter', 'Rooms Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
    # Overwrite file with Room tag added
    print(f'Cards that are or care about "Rooms" in {color}_cards.csv have been tagged.\n')

## Classes
def tag_classes(df, color):
    # Iterate through each {color}_cards.csv file to find Class cards
    # Tag for Classes
    print(f'Tagging cards in {color}_cards.csv that have the "Class" type.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if 'Class' in row['type']:
            tag_type = ['Classes Matter', 'Enchantments Matter']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    # Overwrite file with Room tag added
    #df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
    print(f'"Class" cards in in {color}_cards.csv have been tagged.\n')

## Background
def tag_backgrounds(df, color):
    # Iterate through each {color}_cards.csv file to find Background cards
    # Also check for cards that care about Backgrounds
    # Tag for Backgrounds
    print(f'Tagging cards in {color}_cards.csv that have the "Background" type.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if 'Background' in row['type']:
            tag_type = ['Backgrounds Matter', 'Enchantments Matter']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    # Tag for cares about Background
    print(f'Tagging cards in {color}_cards.csv that have "Choose a Background".')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('Choose a Background' in row['text']
                ):
                tag_type = ['Backgrounds Matter', 'Enchantments Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    # Overwrite file with Room tag added
    print(f'Cards that are or care about "Backgrounds" in {color}_cards.csv have been tagged.\n')

## Shrines
def tag_shrines(df, color):
    # Iterate through each {color}_cards.csv file to find Shrine cards
    # Tag for Shrines
    print(f'Tagging cards in {color}_cards.csv that have the "Shrine" type.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if 'Shrine' in row['type']:
            tag_type = ['Enchantments Matter', 'Shrines Matter']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
    
    # Overwrite file with Room tag added
    print(f'"Shrines" in {color}_cards.csv have been tagged.\n')

### Exile Matters
## Exile Matter effects, such as Impuse draw, foretell, etc...
def tag_for_exile_matters(df, color):
    print(f'Checking {color}_cards.csv for "Exile Matters" cards\n')
    print('\n===============\n')
    tag_for_cascade(df, color)
    print('\n==========\n')
    tag_for_discover(df, color)
    print('\n==========\n')
    tag_for_foretell(df, color)
    print('\n==========\n')
    tag_for_imprint(df, color)
    print('\n==========\n')
    tag_for_impulse(df, color)
    print('\n==========\n')
    tag_for_plot(df, color)
    print('\n==========\n')
    tag_for_suspend(df, color)
    print('\n==========\n')

    print(f'Checking {color}_cards.csv for general "Exile Matters" cards.')
    # Tagging for imprint effects
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if 'Exile Matters' in theme_tags:
            continue
        if (pd.notna(row['text'])
            ):
            if (
                'cards in exile' in row['text'].lower()
                or 'cast a spell from exile' in row['text'].lower()
                or 'cast but don\'t own' in row['text'].lower()
                or 'cast from exile' in row['text'].lower()
                or 'casts a spell from exile' in row['text'].lower()
                or 'control but don\'t own' in row['text'].lower()
                or 'exiled with' in row['text'].lower()
                or 'from anywhere but their hand' in row['text'].lower()
                or 'from anywhere but your hand' in row['text'].lower()
                or 'from exile' in row['text'].lower()
                or 'own in exile' in row['text'].lower()
                or 'play a card from exile' in row['text'].lower()
                or 'plays a card from exile' in row['text'].lower()
                or 'play a land from exile' in row['text'].lower()
                or 'plays a land from exile' in row['text'].lower()
                or 'put into exile' in row['text'].lower()
                or 'remains exiled' in row['text'].lower()
                ):
                tag_type = ['Exile Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
    # Overwrite file with "Exile Matters" tags
    print(f'"Exile Matters" cards tagged in {color}_cards.csv.\n')

## Cascade cards
def tag_for_cascade(df, color):
    print(f'Checking {color}_cards.csv for "Cascade" cards.')
    
    # Tagging for Cascade effects
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('gain cascade' in row['text'].lower()
                or 'has cascade' in row['text'].lower()
                or 'have cascade' in row['text'].lower()
                or 'have "cascade' in row['text'].lower()
                or 'with cascade' in row['text'].lower()
                ):
                tag_type = ['Cascade', 'Exile Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
                
        if pd.notna(row['keywords']):
            if ('Cascade' in row['keywords']):
                tag_type = ['Cascade', 'Exile Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    # Overwrite file with Cascade tags
    print(f'"Cascade" cards tagged in {color}_cards.csv.\n')

## Dsicover cards
def tag_for_discover(df, color):
    print(f'Checking {color}_cards.csv for "Discover" cards.')
    
    # Tagging for Discover effects
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if (pd.notna(row['keywords'])
            ):
            if ('Discover' in row['keywords']):
                tag_type = ['Discover', 'Exile Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    # Overwrite file with creature type tags
    #df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
    print(f'"Discover" cards tagged in {color}_cards.csv.\n')

## Foretell cards, and cards that care about foretell
def tag_for_foretell(df, color):
    print(f'Checking {color}_cards.csv for "Foretell" cards.')
    
    # Tagging for imprint effects
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('foretell' in row['text'].lower()
                ):
                tag_type = ['Exile Matters', 'Foretell']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        if pd.notna(row['keywords']):
            if ('Foretell' in row['keywords']):
                tag_type = ['Exile Matters', 'Foretell']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    # Overwrite file with Forell tags
    print(f'"Foretell" cards tagged in {color}_cards.csv.\n')

## Cards that have or care about imprint
def tag_for_imprint(df, color):
    print(f'Checking {color}_cards.csv for "Imprint" cards.')
    
    # Tagging for imprint effects
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        
        if pd.notna(row['text']):
            if ('imprint' in row['text'].lower()
                ):
                tag_type = ['Exile Matters', 'Imprint']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        if pd.notna(row['keywords']):
            if ('Imprint' in row['keywords']
                ):
                tag_type = ['Exile Matters', 'Imprint']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    # Overwrite file with creature type tags
    print(f'"Imprint" cards tagged in {color}_cards.csv.\n')

## Cards that have or care about impulse
def tag_for_impulse(df, color):
    print(f'Checking {color}_cards.csv for "Impulse" cards.\n'
            '"Impulse" cards in this case are cards that will exile one ore more cards from the top of a library\n'
            'and allow you to play them, usually until the end of the current turn, or until your next end step.\n')
    
    # Check for impulse effects
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        # Tagging cards that should match, but need specific wording
        if ('daxos of meletis' in row['name'].lower()
            or 'bloodsoaked insight' in row['name'].lower()
            or 'florian, voldaren scion' in row['name'].lower()
            or 'possibility storm' in row['name'].lower()
            or 'ragava, nimble pilferer' in row['name'].lower()
            or 'rakdos, the muscle' in row['name'].lower()
            or 'stolen strategy' in row['name'].lower()
            or 'urabrask, heretic praetor' in row['name'].lower()
            or 'valakut exploration' in row['name'].lower()
            or 'wild wasteland' in row['name'].lower()
            ):
            if ('Impulse' not in theme_tags
                and 'Imprint' not in theme_tags):
                tag_type = ['Exile Matters', 'Impulse']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        if pd.notna(row['text']):
            # Setting exclusions that may result in erroneous matches
            if ('damage to each' not in row['text'].lower()
                or 'damage to target' not in row['text'].lower()
                or 'deals combat damage' not in row['text'].lower()
                or 'planeswalker' not in row['type'].lower()
                or 'raid' not in row['text'].lower()
                or 'target opponent\'s hand' not in row['text'].lower()):
                if ('each opponent' in row['text'].lower()
                    or 'morph' in row['text'].lower()
                    or 'opponent\'s library' in row['text'].lower()
                    or 'skip your draw' in row['text'].lower()
                    or 'target opponent' in row['text'].lower()
                    or 'that player\'s' in row['text'].lower()
                    or 'you may look at the top card' in row['text'].lower()
                    ):
                    continue
                
            # Tagging cards that match based on the phrasing of 'exile the top' cards then 'you may {play/cast}'
            if ('exile the top'in row['text'].lower()
                or 'exiles the top' in row['text'].lower()
                ):
                if ('may cast' in row['text'].lower()
                    or 'may play' in row['text'].lower()):
                    if ('Impulse' not in theme_tags
                    and 'Imprint' not in theme_tags):
                        tag_type = ['Exile Matters', 'Impulse']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
            
            # Tagging cards that create junk tokens
            if ('junk token' in row['text'].lower()):
                if ('Impulse' not in theme_tags
                    and 'Imprint' not in theme_tags):
                    tag_type = ['Exile Matters', 'Impulse', 'Junk Tokens']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
            
    # Overwrite file with creature type tags 
    print(f'"Impulse" cards tagged in {color}_cards.csv.\n')

## Cards that have or care about plotting
def tag_for_plot(df, color):
    print(f'Checking {color}_cards.csv for "Plot" cards.')
    
    # Tagging for imprint effects
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        
        if pd.notna(row['text']):
            if ('becomes plotted' in row['text'].lower()
                or 'plot cost' in row['text'].lower()
                or 'plotting' in row['text'].lower()
                ):
                tag_type = ['Exile Matters', 'Plot']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        if pd.notna(row['keywords']):
            if ('Plot' in row['keywords']
                ):
                tag_type = ['Exile Matters', 'Plot']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    # Overwrite file with creature type tags
    print(f'"Plot" cards tagged in {color}_cards.csv.\n')

## Cards that have or care about suspend
def tag_for_suspend(df, color):
    print(f'Checking {color}_cards.csv for "Suspend" cards.')
    
    # Tagging for imprint effects
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('has suspend' in row['text'].lower()
                or 'have suspend' in row['text'].lower()
                or 'gains suspend' in row['text'].lower()
                or 'suspended card' in row['text'].lower()
                or 'suspend cost' in row['text'].lower()
                ):
                tag_type = ['Exile Matters', 'Plot']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        if pd.notna(row['keywords']):
            if ('Suspend' in row['keywords']):
                tag_type = ['Exile Matters', 'Plot']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    # Overwrite file with creature type tags
    print(f'"Suspend" cards tagged in {color}_cards.csv.\n')

### Tokens
def tag_for_tokens(df, color):
    # Tag for other token creation
    print(f'Tagging cards in {color}_cards.csv that create or modify creation of tokens.\n')
    print('\n===============\n')
    print('Checking for creature token generators.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            # Excluding false positives
            if ('fabricate' in row['text'].lower()
                or 'modular' in row['text'].lower()
                
                # Spefically named cards
                or 'agatha\'s soul cauldron' in row['name'].lower()
                ):
                continue
            
            # Tagging cards that create creature tokens
            if ('create' in row['text'].lower()
                or 'put' in row['text'].lower()
                ):
                for tokens in num_to_search:
                    if (f'{tokens}' in row['text']
                        and 'token' in row['text']):
                        if ('creature' in row['text'].lower()):
                            tag_type = ['Creature Tokens', 'Tokens Matter']
                            for tag in tag_type:
                                if tag not in theme_tags:
                                    theme_tags.extend([tag])
                                    df.at[index, 'themeTags'] = theme_tags
        
    print(f'Cards in {color}_cards.csv that are creature token generators have been tagged.\n')
    print('\n==========\n')
    print('Checking for token creation modifiers.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        # Excluding false positives
        if ('cloakwood swarmkeeper' in row['name'].lower()
            or 'neyali, sun\'s vanguard' in row['name'].lower()
            or 'staff of the storyteller' in row['name'].lower()
            ):
            continue
        
        # Tagging replacement effects (i.e. doublers, create different tokens instead, or additional tokens)
        if pd.notna(row['text']):
            if ('create one or more' in row['text']
                or 'one or more creature' in row['text']
                or 'one or more tokens would be created' in row['text']
                or 'one or more tokens would be put' in row['text']
                or 'one or more tokens would enter' in row['text']
                or 'one or more tokens you control' in row['text']
                or 'put one or more' in row['text']
                ):
                if ('token' in row['text']):
                    if ('instead' in row['text']
                        or 'plus' in row['text']
                        ):
                        tag_type = ['Tokens', 'Token Modification', 'Tokens Matter']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
        
        
    print(f'Cards in {color}_cards.csv that are token creation modifiers have been tagged.\n')
    
    # Overwrite file with token tag added
    print(f'Token cards tagged in {color}_cards.csv.\n')

### Life Matters
def tag_for_life_matters(df, color):
    # Tag for Life gain cares cards
    print(f'Tagging cards in {color}_cards.csv that gain life or care about life gain.\n')
    print('\n===============\n')
    print('Checking for life gain cards.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            # Excluding replacement effects
            if ('if you would gain life' in row['text'].lower()
                or 'whenever you gain life' in row['text'].lower()
                ):
                continue
            
            # Tagging food token creation
            if ('food token' in row['text'].lower()
                or 'food' in row['type'].lower()):
                tag_type = ['Food Tokens', 'Lifegain', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
                continue
        
            # Tagging for cards that gain specific amounts of life between 1 - 10 and X
            for life_gained in num_to_search:
                if (f'gain {life_gained} life' in row['text'].lower()
                    or f'gains {life_gained} life' in row['text'].lower()):
                    tag_type = ['Lifegain', 'Life Matters']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
                        
            # Tagging for cards that gain life
            if ('gain life' in row['text'].lower()
                or 'gains life' in row['text'].lower()
                ):
                tag_type = ['Lifegain', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
            # Tagging for cards that have or give lifelink
            if ('lifelink' in row['text'].lower()
                ):
                tag_type = ['Lifelink', 'Lifegain', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Tagging for cards that gain life on life loss
            if ('deals damage' not in row['text'].lower()
                ):
                if ('loses life' in row['text'].lower()):
                    if ('gain that much life' in row['text'].lower()
                    ):
                        tag_type = ['Lifelink', 'Lifegain', 'Life Matters']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
            
            # Tagging for lifelink-like effects that aren't exactly lifelink
            if ('deals damage, you gain that much life' in row['text'].lower()
                ):
                tag_type = ['Lifegain', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
        # Tagging for creature types that commonly care about life gain
        if ('Angel' in row['creatureTypes']
            or 'Bat' in row['creatureTypes']
            or 'Cleric' in row['creatureTypes']
            or 'Vampire' in row['creatureTypes']
            ):
            tag_type = ['Lifegain', 'Life Matters']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
                    
    print(f'Cards in {color}_cards.csv that gain life or grant lifelink have been tagged.\n')
    print('\n==========\n')
    
    # Checking for life gain modifiers or trigger on life gain
    print('Checking for life gain modifications or triggers.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('if you would gain life' in row['text'].lower()
                or 'whenever you gain life' in row['text'].lower()
                ):
                tag_type = ['Lifegain', 'Lifegain Triggers', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
    print(f'Cards in {color}_cards.csv that modify life gain or trigger on life gain have been tagged.\n')
    print('\n==========\n')
    
    # Checking for life loss modifiers or trigger on life loss
    print('Checking for life loss triggers.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        if pd.notna(row['text']):
            if ('Bat' in row['creatureTypes']
                or 'you lost life' in row['text'].lower()
                or 'you gained and lost life' in row['text'].lower()
                or 'you gained or lost life' in row['text'].lower()
                or 'you would lose life' in row['text'].lower()
                or 'you\'ve gained and lost life this turn' in row['text'].lower()
                or 'you\'ve lost life' in row['text'].lower()
                or 'whenever you gain or lose life' in row['text'].lower()
                or 'whenever you lose life' in row['text'].lower()
                ):
                tag_type = ['Lifeloss', 'Lifeloss Triggers', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
    
    print(f'Cards in {color}_cards.csv that modify life gain or trigger on life gain have been tagged.\n')
    
    # Overwrite file with Life tags added
    print(f'Life Matters cards tagged in {color}_cards.csv.\n')

### Counters
def tag_for_counters(df, color):
    # Iterate through each {color}_cards.csv file to find cards that add counters
    # Also check for cards that care about counters
    # Tag for counters matter
    print(f'Tagging cards in {color}_cards.csv that fit the "Counters Matter" theme.')
    for index, row in df.iterrows():
        theme_tags = row['themeTags']
        
        # Specifically named cards
        if ('banner of kinship' in row['name'].lower()
            or 'damning verdict' in row['name'].lower()
            or 'ozolith' in row['name'].lower()
            ):
            tag_type = ['Counters Matter']
            for tag in tag_type:
                if tag not in theme_tags:
                    theme_tags.extend([tag])
                    df.at[index, 'themeTags'] = theme_tags
        
        # Tagging for things that care about counters in general
        if pd.notna(row['text']):
            if ('choose a kind of counter' in row['text'].lower()
                or 'if it had counters' in row['text'].lower()
                or 'move a counter' in row['text'].lower()
                or 'one or more counters' in row['text'].lower()
                or 'one or more +1/+1 counter' in row['text'].lower()
                or 'proliferate' in row['text'].lower()
                or 'remove a counter' in row['text'].lower()
                or 'with counters on them' in row['text'].lower()
                ):
                tag_type = ['Counters Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        
            # Tagging for specifically +1/+1
            if ('+1/+1 counter' in row['text'].lower()
                or 'if it had counters' in row['text'].lower()
                or 'one or more counter' in row['text'].lower()
                or 'one or more +1/+1 counter' in row['text'].lower()
                or 'proliferate' in row['text'].lower()
                or 'undying' in row['text'].lower()
                or 'with counters on them' in row['text'].lower()
                
                # Specific creature types
                or 'Hydra' in row['creatureTypes']
                
                # Speficially named cards
                or 'damning verdict' in row['name'].lower()
                or 'ozolith' in row['name'].lower()
                ):
                tag_type = ['+1/+1 Counters', 'Counters Matter', 'Voltron']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Tagging for specifically -1/-1
            if ('-1/-1 counter' in row['text'].lower()
                or 'if it had counters' in row['text'].lower()
                or 'infect' in row['text'].lower()
                or 'one or more counter' in row['text'].lower()
                or 'one of more -1/-1 counter' in row['text'].lower()
                or 'persist' in row['text'].lower()
                or 'proliferate' in row['text'].lower()
                or 'wither' in row['text'].lower()
                
                # Specifically named cards
                or 'damning verdict' in row['name'].lower()
                ):
                tag_type = ['-1/-1 Counters', 'Counters Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Tagging for other counters (i.e. oil, lore, etc...)
            for counter_type in counter_types:
                if f'{counter_type} counter'.lower() in row['text'].lower():
                    tag_type = [f'{counter_type} Counters', 'Counters Matter']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
        
    # Overwrite file with counters matter tag added
    print(f'"Counters Matter" themed cards in {color}_cards.csv have been tagged.\n')

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


regenerate_csv_by_color('colorless')
#for color in colors:
#    load_dataframe(color)
load_dataframe('colorless')