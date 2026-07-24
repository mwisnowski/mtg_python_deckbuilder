"""Tests for fetch-land shape/type tagging (Roadmap 31, Milestone 2)."""
import pandas as pd

from tagging import tag_utils
from tagging.tagger import tag_for_fetch_lands


def _land_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df['themeTags'] = [[] for _ in range(len(df))]
    return df


def _tags_for(df: pd.DataFrame, name: str) -> list[str]:
    return df.loc[df['name'] == name, 'themeTags'].iloc[0]


def test_classic_fetchland_shape_and_types():
    df = _land_df([
        {
            'name': 'Arid Mesa',
            'type': 'Land',
            'text': '{T}, Pay 1 life, Sacrifice this land: Search your library for a Mountain or '
                    'Plains card, put it onto the battlefield, then shuffle.',
        },
    ])
    tag_for_fetch_lands(df, 'r')
    tags = _tags_for(df, 'Arid Mesa')
    assert set(tags) == {'Fetchland', 'Mountain Fetch', 'Plains Fetch'}


def test_untapped_no_life_fetchland_shape():
    """The Fallen Empires cycle (Bad River, Flood Plain, Grasslands,
    Mountain Valley, Rocky Tar Pit) shares the Fetchland shape (named
    types, fetched land enters untapped) but doesn't pay life -- the land
    itself enters tapped instead."""
    df = _land_df([
        {
            'name': 'Flood Plain',
            'type': 'Land',
            'text': 'This land enters tapped.\n{T}, Sacrifice this land: Search your library for a '
                    'Plains or Island card, put it onto the battlefield, then shuffle.',
        },
    ])
    tag_for_fetch_lands(df, 'w')
    tags = _tags_for(df, 'Flood Plain')
    assert set(tags) == {'Fetchland', 'Plains Fetch', 'Island Fetch'}


def test_panorama_shape_and_types():
    df = _land_df([
        {
            'name': 'Bant Panorama',
            'type': 'Land',
            'text': '{T}: Add {C}.\n{1}, {T}, Sacrifice this land: Search your library for a basic '
                    'Forest, Plains, or Island card, put it onto the battlefield tapped, then shuffle.',
        },
    ])
    tag_for_fetch_lands(df, 'w')
    tags = _tags_for(df, 'Bant Panorama')
    assert set(tags) == {'Panorama Land', 'Alt Fetchland', 'Forest Fetch', 'Plains Fetch', 'Island Fetch'}


def test_new_capenna_shape_and_types():
    df = _land_df([
        {
            'name': 'Brokers Hideout',
            'type': 'Land',
            'text': 'When this land enters, sacrifice it. When you do, search your library for a basic '
                    'Forest, Plains, or Island card, put it onto the battlefield tapped, then shuffle and '
                    'you gain 1 life.',
        },
    ])
    tag_for_fetch_lands(df, 'g')
    tags = _tags_for(df, 'Brokers Hideout')
    assert set(tags) == {'New Capenna Land', 'Alt Fetchland', 'Forest Fetch', 'Plains Fetch', 'Island Fetch'}


def test_landscape_shape_requires_real_cycling_keyword():
    df = _land_df([
        {
            'name': 'Bountiful Landscape',
            'type': 'Land',
            'text': '{T}: Add {C}.\n{T}, Sacrifice this land: Search your library for a basic Forest, '
                    'Island, or Mountain card, put it onto the battlefield tapped, then shuffle.\n'
                    'Cycling {G}{U}{R} ({G}{U}{R}, Discard this card: Draw a card.)',
        },
    ])
    tag_for_fetch_lands(df, 'g')
    tags = _tags_for(df, 'Bountiful Landscape')
    assert set(tags) == {'Landscape Land', 'Alt Fetchland', 'Forest Fetch', 'Island Fetch', 'Mountain Fetch'}


def test_catch_all_any_basic_fetch():
    df = _land_df([
        {
            'name': 'Fabled Passage',
            'type': 'Land',
            'text': '{T}, Sacrifice this land: Search your library for a basic land card, put it onto '
                    'the battlefield tapped, then shuffle. Then if you control four or more lands, untap '
                    'that land.',
        },
        {
            'name': 'Myriad Landscape',
            'type': 'Land',
            'text': 'This land enters tapped.\n{T}: Add {C}.\n{2}, {T}, Sacrifice this land: Search your '
                    'library for up to two basic land cards that share a land type, put them onto the '
                    'battlefield tapped, then shuffle.',
        },
        {
            'name': 'Thawing Glaciers',
            'type': 'Land',
            'text': 'This land enters tapped.\n{1}, {T}: Search your library for a basic land card, put '
                    "that card onto the battlefield tapped, then shuffle. Return this land to its owner's "
                    'hand at the beginning of the next cleanup step.',
        },
    ])
    tag_for_fetch_lands(df, 'c')
    assert set(_tags_for(df, 'Fabled Passage')) == {'Alt Fetchland', 'Any Basic Fetch'}
    assert set(_tags_for(df, 'Myriad Landscape')) == {'Alt Fetchland', 'Any Basic Fetch'}
    assert set(_tags_for(df, 'Thawing Glaciers')) == {'Alt Fetchland', 'Any Basic Fetch'}


def test_opponent_benefiting_search_lands_are_excluded_by_name():
    """Ghost Quarter/Volatile Fault/Boseiju/Demolition Field match the
    generic search/shuffle shape but the search benefits an opponent (or
    whichever player's land was destroyed), not the caster -- not a real
    fetch land for deck-building purposes."""
    df = _land_df([
        {
            'name': 'Ghost Quarter',
            'type': 'Land',
            'text': '{T}: Add {C}.\n{T}, Sacrifice this land: Destroy target land. Its controller may '
                    'search their library for a basic land card, put it onto the battlefield, then '
                    'shuffle.',
        },
        {
            'name': 'Boseiju, Who Endures',
            'type': 'Legendary Land',
            'text': '{T}: Add {G}.\nChannel — {1}{G}, Discard this card: Destroy target artifact, '
                    'enchantment, or nonbasic land an opponent controls. That player may search their '
                    'library for a land card with a basic land type, put it onto the battlefield, then '
                    'shuffle.',
        },
        {
            'name': 'Volatile Fault',
            'type': 'Land — Cave',
            'text': '{T}: Add {C}.\n{1}, {T}, Sacrifice this land: Destroy target nonbasic land an '
                    'opponent controls. That player may search their library for a basic land card, put '
                    'it onto the battlefield, then shuffle. You create a Treasure token.',
        },
        {
            'name': 'Demolition Field',
            'type': 'Land',
            'text': "{T}: Add {C}.\n{2}, {T}, Sacrifice this land: Destroy target nonbasic land an "
                    "opponent controls. That land's controller may search their library for a basic land "
                    "card, put it onto the battlefield, then shuffle. You may search your library for a "
                    "basic land card, put it onto the battlefield, then shuffle.",
        },
    ])
    tag_for_fetch_lands(df, 'c')
    for name in ('Ghost Quarter', 'Boseiju, Who Endures', 'Volatile Fault', 'Demolition Field'):
        assert _tags_for(df, name) == []


def test_any_basic_fetch_does_not_get_a_named_shape():
    """A card that only searches for "a basic land card" (Any Basic Fetch)
    can only ever find a true basic, unlike named-type shapes (e.g.
    Flooded Strand's Plains/Island types can also find Godless Shrine).
    Even if the cost structure matches a named shape exactly, it must fall
    through to the Alt Fetchland catch-all instead."""
    df = _land_df([
        {
            'name': 'Prismatic Vista',
            'type': 'Land',
            'text': '{T}, Pay 1 life, Sacrifice this land: Search your library for a basic land card, '
                    'put it onto the battlefield, then shuffle.',
        },
        {
            'name': 'Shire Terrace',
            'type': 'Land',
            'text': '{T}: Add {C}.\n{1}, {T}, Sacrifice this land: Search your library for a basic land '
                    'card, put it onto the battlefield tapped, then shuffle.',
        },
    ])
    tag_for_fetch_lands(df, 'c')
    assert set(_tags_for(df, 'Prismatic Vista')) == {'Alt Fetchland', 'Any Basic Fetch'}
    assert set(_tags_for(df, 'Shire Terrace')) == {'Alt Fetchland', 'Any Basic Fetch'}


def test_land_fetch_and_gate_fetch():
    df = _land_df([
        {
            'name': "Urza's Cave",
            'type': "Land — Urza's Cave",
            'text': '{T}: Add {C}.\n{3}, {T}, Sacrifice this land: Search your library for a land card, '
                    'put it onto the battlefield tapped, then shuffle.',
        },
        {
            'name': "Maze's End",
            'type': 'Land',
            'text': "This land enters tapped.\n{T}: Add {C}.\n{3}, {T}, Return this land to its owner's "
                    "hand: Search your library for a Gate card, put it onto the battlefield, then shuffle. "
                    "If you control ten or more Gates with different names, you win the game.",
        },
    ])
    tag_for_fetch_lands(df, 'c')
    assert set(_tags_for(df, "Urza's Cave")) == {'Alt Fetchland', 'Land Fetch'}
    assert set(_tags_for(df, "Maze's End")) == {'Alt Fetchland', 'Gate Fetch'}


def test_non_land_card_is_not_tagged():
    """A tutor spell mentioning near-identical fetch phrasing must not be
    tagged -- fetch tags are scoped to actual Land permanents."""
    df = _land_df([
        {
            'name': 'Weird Tutor',
            'type': 'Sorcery',
            'text': 'Search your library for a basic land card, put it onto the battlefield tapped, '
                    'then shuffle.',
        },
    ])
    tag_for_fetch_lands(df, 'g')
    assert _tags_for(df, 'Weird Tutor') == []


def test_artifact_tutor_land_is_not_tagged():
    """Urza's Saga's Chapter III (search for an artifact, not a land) uses
    the same generic "search ... put onto the battlefield ... shuffle"
    shape but must not get any fetch-land tag."""
    df = _land_df([
        {
            'name': "Urza's Saga",
            'type': "Enchantment Land — Urza's Saga",
            'text': 'III — Search your library for an artifact card with mana cost {0} or {1}, put it '
                    'onto the battlefield, then shuffle.',
        },
    ])
    tag_for_fetch_lands(df, 'c')
    assert _tags_for(df, "Urza's Saga") == []


def test_fetch_tag_classification_split():
    # Shape tags stay theme-facing; search-target tags are metadata plumbing.
    assert tag_utils.classify_tag('Fetchland') == 'theme'
    assert tag_utils.classify_tag('Alt Fetchland') == 'theme'
    assert tag_utils.classify_tag('Plains Fetch') == 'metadata'
    assert tag_utils.classify_tag('Any Basic Fetch') == 'metadata'
    assert tag_utils.classify_tag('Land Fetch') == 'metadata'
    assert tag_utils.classify_tag('Gate Fetch') == 'metadata'
