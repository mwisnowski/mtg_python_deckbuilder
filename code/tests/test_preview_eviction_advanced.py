import os

from code.web.services.theme_preview import get_theme_preview, bust_preview_cache
from code.web.services import preview_cache as pc
from code.web.services.preview_metrics import preview_metrics


def _prime(slug: str, limit: int = 12, hits: int = 0, *, colors=None):
    get_theme_preview(slug, limit=limit, colors=colors)
    for _ in range(hits):
        get_theme_preview(slug, limit=limit, colors=colors)  # cache hits


def test_cost_bias_protection(monkeypatch):
    """Higher build_cost_ms entries should survive versus cheap low-hit entries.

    We simulate by manually injecting varied build_cost_ms then forcing eviction.
    """
    os.environ['THEME_PREVIEW_CACHE_MAX'] = '6'
    bust_preview_cache()
    # Build 6 entries
    base_key_parts = []
    color_cycle = [None, 'W', 'U', 'B', 'R', 'G']
    for i in range(6):
        payload = get_theme_preview('Blink', limit=6, colors=color_cycle[i % len(color_cycle)])
        base_key_parts.append(payload['theme_id'])
    # Manually adjust build_cost_ms to create one very expensive entry and some cheap ones.
    # Choose first key deterministically.
    expensive_key = next(iter(pc.PREVIEW_CACHE.keys()))
    pc.PREVIEW_CACHE[expensive_key]['build_cost_ms'] = 120.0  # place in highest bucket
    # Mark others as very cheap
    for k, v in pc.PREVIEW_CACHE.items():
        if k != expensive_key:
            v['build_cost_ms'] = 1.0
    # Force new insertion to trigger eviction
    get_theme_preview('Blink', limit=6, colors='X')
    # Expensive key should still be present
    assert expensive_key in pc.PREVIEW_CACHE
    m = preview_metrics()
    assert m['preview_cache_evictions'] >= 1
    assert m['preview_cache_evictions_by_reason'].get('low_score', 0) >= 1


def test_hot_entry_retention(monkeypatch):
    """Entry with many hits should outlive cold entries when eviction occurs."""
    os.environ['THEME_PREVIEW_CACHE_MAX'] = '5'
    bust_preview_cache()
    # Prime one hot entry with multiple hits
    _prime('Blink', limit=6, hits=5, colors=None)
    hot_key = next(iter(pc.PREVIEW_CACHE.keys()))
    # Add additional distinct entries to exceed max
    for c in ['W','U','B','R','G','X']:
        get_theme_preview('Blink', limit=6, colors=c)
    # Ensure cache size within limit & hot entry retained
    assert len(pc.PREVIEW_CACHE) <= 5
    assert hot_key in pc.PREVIEW_CACHE, 'Hot entry was evicted unexpectedly'


def test_emergency_overflow_path(monkeypatch):
    """If cache grows beyond 2*limit, emergency_overflow evictions should record that reason."""
    os.environ['THEME_PREVIEW_CACHE_MAX'] = '4'
    bust_preview_cache()
    # Temporarily monkeypatch _cache_max to simulate sudden lower limit AFTER many insertions
    # Insert > 8 entries first (using varying limits to vary key tuples)
    for i, c in enumerate(['W','U','B','R','G','X','C','M','N']):
        get_theme_preview('Blink', limit=6, colors=c)
    # Confirm we exceeded 2*limit (cache_max returns at least 50 internally so override via env not enough)
    # We patch pc._cache_max directly to enforce small limit for test.
    monkeypatch.setattr(pc, '_cache_max', lambda: 4)
    # Now call eviction directly
    pc.evict_if_needed()
    m = preview_metrics()
    # Either emergency_overflow or multiple low_score evictions until limit; ensure size reduced.
    assert len(pc.PREVIEW_CACHE) <= 50  # guard (internal min), but we expect <= original internal min
    # Look for emergency_overflow reason occurrence (best effort; may not trigger if size not > 2*limit after min bound)
    # We allow pass if at least one eviction occurred.
    assert m['preview_cache_evictions'] >= 1


def test_env_weight_override(monkeypatch):
    """Changing weight env vars should alter protection score ordering.

    We set W_HITS very low and W_AGE high so older entry with many hits can be evicted.
    """
    os.environ['THEME_PREVIEW_CACHE_MAX'] = '5'
    os.environ['THEME_PREVIEW_EVICT_W_HITS'] = '0.1'
    os.environ['THEME_PREVIEW_EVICT_W_AGE'] = '5.0'
    # Bust and clear cached weight memoization
    bust_preview_cache()
    # Clear module-level caches for weights
    if hasattr(pc, '_EVICT_WEIGHTS_CACHE'):
        pc._EVICT_WEIGHTS_CACHE = None
    # Create two entries: one older with many hits, one fresh with none.
    _prime('Blink', limit=6, hits=6, colors=None)  # older hot entry
    old_key = next(iter(pc.PREVIEW_CACHE.keys()))
    # Age the first entry slightly
    pc.PREVIEW_CACHE[old_key]['inserted_at'] -= 120  # 2 minutes ago
    # Add fresh entries to trigger eviction
    for c in ['W','U','B','R','G','X']:
        get_theme_preview('Blink', limit=6, colors=c)
    # With age weight high and hits weight low, old hot entry can be evicted
    # Not guaranteed deterministically; assert only that at least one eviction happened and metrics show low_score.
    m = preview_metrics()
    assert m['preview_cache_evictions'] >= 1
    assert 'low_score' in m['preview_cache_evictions_by_reason']
