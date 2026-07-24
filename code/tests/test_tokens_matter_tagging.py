"""Tests for generic (copy-into-token) token creation tagging (Roadmap 31, Milestone 4)."""
import pandas as pd

from tagging.tagger import tag_for_tokens


def _token_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df['themeTags'] = [[] for _ in range(len(df))]
    return df


def _tags_for(df: pd.DataFrame, name: str) -> list[str]:
    return df.loc[df['name'] == name, 'themeTags'].iloc[0]


def test_copy_into_token_without_creature_token_phrase():
    df = _token_df([
        {
            'name': "Hashaton, Scarab's Fist",
            'type': 'Legendary Creature - Zombie',
            'text': 'Whenever you discard a creature card, you may pay {2}{U}. If you do, create a '
                    "tapped token that's a copy of that card, except it's a 4/4 black Zombie.",
        },
    ])
    tag_for_tokens(df, 'u')
    tags = _tags_for(df, "Hashaton, Scarab's Fist")
    assert 'Tokens Matter' in tags
    assert 'Token Creation' in tags


def test_kiki_jiki_copy_effect():
    df = _token_df([
        {
            'name': 'Kiki-Jiki, Mirror Breaker',
            'type': 'Legendary Creature - Goblin Shaman',
            'text': "{T}: Create a token that's a copy of target nonlegendary creature you control, "
                    "except it's not legendary and it gains haste. Sacrifice it at the beginning of "
                    'the next end step.',
        },
    ])
    tag_for_tokens(df, 'r')
    tags = _tags_for(df, 'Kiki-Jiki, Mirror Breaker')
    assert 'Tokens Matter' in tags
    assert 'Token Creation' in tags
