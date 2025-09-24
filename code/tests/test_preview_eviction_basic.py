import os
from code.web.services.theme_preview import get_theme_preview, bust_preview_cache  # type: ignore
from code.web.services import preview_cache as pc  # type: ignore


def test_basic_low_score_eviction(monkeypatch):
    """Populate cache past limit using distinct color filters to force eviction."""
    os.environ['THEME_PREVIEW_CACHE_MAX'] = '5'
    bust_preview_cache()
    colors_seq = [None, 'W', 'U', 'B', 'R', 'G']  # 6 unique keys (slug, limit fixed, colors vary)
    # Prime first key with an extra hit to increase protection
    first_color = colors_seq[0]
    get_theme_preview('Blink', limit=6, colors=first_color)
    get_theme_preview('Blink', limit=6, colors=first_color)  # hit
    # Insert remaining distinct keys
    for c in colors_seq[1:]:
        get_theme_preview('Blink', limit=6, colors=c)
    # Cache limit 5, inserted 6 distinct -> eviction should have occurred
    assert len(pc.PREVIEW_CACHE) <= 5
    from code.web.services.preview_metrics import preview_metrics  # type: ignore
    m = preview_metrics()
    assert m['preview_cache_evictions'] >= 1, 'Expected at least one eviction'
    assert m['preview_cache_evictions_by_reason'].get('low_score', 0) >= 1
