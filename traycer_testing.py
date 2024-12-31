def tag_for_cantrips(df, color):
    """
    Tag cards in the DataFrame as cantrips based on specific criteria.
    
    Cantrips are defined as low-cost spells (mana value <= 2) that draw cards.
    The function excludes certain card types, keywords, and specific named cards
    from being tagged as cantrips.
    
    Parameters:
        df (pd.DataFrame): The DataFrame containing card data.
        color (str): The color identifier for logging purposes.
    
    Returns:
        None: The function modifies the DataFrame in place by applying tags.
    """
    logging.info('Tagging cantrips in %s_cards.csv', color)

    # Convert mana value to numeric
    df['manaValue'] = pd.to_numeric(df['manaValue'], errors='coerce')

    # Define exclusion conditions
    excluded_types = df['type'].str.contains('Land|Equipment', na=False)
    excluded_keywords = df['keywords'].str.contains('Channel|Cycling|Connive|Learn|Ravenous', na=False)
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

    # Define cantrip conditions
    has_draw = df['text'].str.contains('draw a card', case=False, na=False)
    low_cost = df['manaValue'] <= 2

    # Combine all conditions
    cantrip_mask = (
        ~excluded_types &
        ~excluded_keywords &
        ~has_loot &
        ~excluded_names &
        has_draw &
        low_cost
    )

    # Apply tags using vectorized operation
    apply_tag_vectorized(df, cantrip_mask, TAG_GROUPS['Cantrips'])

    logging.info('Finished tagging cantrips in %s_cards.csv', color)