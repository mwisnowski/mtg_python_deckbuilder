import pandas as pd

from deck_builder.random_entrypoint import _ensure_theme_tag_cache, _filter_multi


def _build_df() -> pd.DataFrame:
    data = {
        "name": ["Alpha", "Beta", "Gamma"],
        "themeTags": [
            ["Aggro", "Tokens"],
            ["LifeGain", "Control"],
            ["Artifacts", "Combo"],
        ],
    }
    df = pd.DataFrame(data)
    return _ensure_theme_tag_cache(df)


def test_and_filter_uses_cached_index():
    df = _build_df()
    filtered, diag = _filter_multi(df, "Aggro", "Tokens", None)

    assert list(filtered["name"].values) == ["Alpha"]
    assert diag["resolved_themes"] == ["Aggro", "Tokens"]
    assert not diag["combo_fallback"]
    assert "aggro" in df.attrs["_ltag_index"]
    assert "tokens" in df.attrs["_ltag_index"]


def test_synergy_fallback_partial_match_uses_index_union():
    df = _build_df()

    filtered, diag = _filter_multi(df, "Life Gain", None, None)

    assert list(filtered["name"].values) == ["Beta"]
    assert diag["combo_fallback"]
    assert diag["synergy_fallback"]
    assert diag["resolved_themes"] == ["life", "gain"]
    assert diag["fallback_reason"] is not None
