"""Tests for self-token-copy tagging (roadmap_39, Milestone 4)."""
import pandas as pd

from tagging.tagger import tag_for_self_token_copies


def _df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df['themeTags'] = [[] for _ in range(len(df))]
    return df


def _tags_for(df: pd.DataFrame, name: str) -> list[str]:
    return df.loc[df['name'] == name, 'themeTags'].iloc[0]


def test_offspring_gets_token_copy_tag():
    df = _df([
        {'name': 'Agate Instigator', 'keywords': 'Offspring'},
    ])
    tag_for_self_token_copies(df, 'w')
    assert 'Token Copy: Offspring' in _tags_for(df, 'Agate Instigator')


def test_embalm_gets_token_copy_tag():
    df = _df([
        {'name': 'Anointer Priest', 'keywords': 'Embalm'},
    ])
    tag_for_self_token_copies(df, 'w')
    assert 'Token Copy: Embalm' in _tags_for(df, 'Anointer Priest')


def test_card_without_matching_keyword_untagged():
    df = _df([
        {'name': 'Grizzly Bears', 'keywords': ''},
    ])
    tag_for_self_token_copies(df, 'g')
    assert _tags_for(df, 'Grizzly Bears') == []


def test_multiple_self_copy_keywords_get_multiple_tags():
    df = _df([
        {'name': 'Rare Dual Keyword Card', 'keywords': 'Embalm, Eternalize'},
    ])
    tag_for_self_token_copies(df, 'w')
    tags = _tags_for(df, 'Rare Dual Keyword Card')
    assert 'Token Copy: Embalm' in tags
    assert 'Token Copy: Eternalize' in tags
