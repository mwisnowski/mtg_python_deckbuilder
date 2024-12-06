from __future__ import annotations

import inquirer.prompt # type: ignore
import pandas as pd # type: ignore

from fuzzywuzzy import fuzz, process # type: ignore
from IPython.display import display

pd.set_option('display.max_colwidth', None)
pd.set_option('display.expand_frame_repr', True) 
pd.options.mode.chained_assignment = None

def get_card_info():
    question = [
        inquirer.Text(
            'card_prompt',
            message='Enter a card name:'
            )
    ]
    answer = inquirer.prompt(question)
    card_choice = answer['card_prompt']
    
    df = pd.read_csv('csv_files/cards.csv', low_memory=False)
    fuzzy_card_choice = process.extractOne(card_choice, df['name'], scorer=fuzz.ratio)
    fuzzy_card_choice = fuzzy_card_choice[0]
    filtered_df = df[df['name'] == fuzzy_card_choice]
    columns_to_keep = ['name', 'colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'keywords', 'power', 'toughness', 'text']
    filtered_df = filtered_df[filtered_df['layout'].str.contains('reversible_card') == False]
    filtered_df = filtered_df[filtered_df['availability'].str.contains('arena') == False]
    filtered_df.drop_duplicates(subset='name', keep='first', inplace=True)
    filtered_df = filtered_df[columns_to_keep].astype('string') 
    columns_to_keep = ['name', 'colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'keywords', 'power', 'toughness']
    filtered_df_no_text = filtered_df[columns_to_keep]
    filtered_df_no_text.dropna(how='all', axis=1, inplace=True)
    
    display(filtered_df_no_text.to_string())
    display(filtered_df['text'].to_string())