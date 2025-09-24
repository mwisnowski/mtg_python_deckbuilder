import os
import time
import json
from code.web.services.theme_preview import get_theme_preview, preview_metrics, bust_preview_cache  # type: ignore


def test_colors_filter_constraint_green_subset():
    """colors=G should only return cards whose color identities are subset of {G} or colorless ('' list)."""
    payload = get_theme_preview('Blink', limit=8, colors='G')  # pick any theme; data-driven
    for card in payload['sample']:
        if not card['colors']:
            continue
        assert set(card['colors']).issubset({'G'}), f"Card {card['name']} had colors {card['colors']} outside filter"


def test_synthetic_placeholder_fill_present_when_short():
    # Force scarcity via impossible color filter letter ensuring empty real pool -> synthetic placeholders
    payload = get_theme_preview('Blink', limit=50, colors='Z')
    # All real cards filtered out; placeholders must appear
    synthetic_roles = [c for c in payload['sample'] if 'synthetic' in (c.get('roles') or [])]
    assert synthetic_roles, 'Expected at least one synthetic placeholder entry under restrictive color filter'
    assert any('synthetic_synergy_placeholder' in (c.get('reasons') or []) for c in synthetic_roles), 'Missing synthetic placeholder reason'


def test_cache_hit_timing_and_log(monkeypatch, capsys):
    os.environ['WEB_THEME_PREVIEW_LOG'] = '1'
    # Force fresh build
    bust_preview_cache()
    payload1 = get_theme_preview('Blink', limit=6)
    assert payload1['cache_hit'] is False
    # Second call should hit cache
    payload2 = get_theme_preview('Blink', limit=6)
    assert payload2['cache_hit'] is True
    captured = capsys.readouterr().out.splitlines()
    assert any('theme_preview_build' in line for line in captured), 'Missing build log'
    assert any('theme_preview_cache_hit' in line for line in captured), 'Missing cache hit log'


def test_per_theme_percentiles_and_raw_counts():
    bust_preview_cache()
    for _ in range(5):
        get_theme_preview('Blink', limit=6)
    metrics = preview_metrics()
    per = metrics['per_theme']
    assert 'blink' in per, 'Expected theme slug in per_theme metrics'
    blink_stats = per['blink']
    assert 'p50_ms' in blink_stats and 'p95_ms' in blink_stats, 'Missing percentile metrics'
    assert 'curated_total' in blink_stats and 'sampled_total' in blink_stats, 'Missing raw curated/sample per-theme totals'


def test_structured_log_contains_new_fields(capsys):
    os.environ['WEB_THEME_PREVIEW_LOG'] = '1'
    bust_preview_cache()
    get_theme_preview('Blink', limit=5)
    out_lines = capsys.readouterr().out.splitlines()
    build_lines = [line for line in out_lines if 'theme_preview_build' in line]
    assert build_lines, 'No build log lines found'
    parsed = [json.loads(line) for line in build_lines]
    obj = parsed[-1]
    assert 'curated_total' in obj and 'sampled_total' in obj and 'role_counts' in obj, 'Missing expected structured log fields'


def test_warm_index_latency_reduction():
    bust_preview_cache()
    t0 = time.time()
    get_theme_preview('Blink', limit=6)
    cold = time.time() - t0
    t1 = time.time()
    get_theme_preview('Blink', limit=6)
    warm = time.time() - t1
    # Warm path should generally be faster; allow flakiness with generous factor
    # If cold time is extremely small (timer resolution), skip strict assertion
    if cold < 0.0005:  # <0.5ms treat as indistinguishable; skip to avoid flaky failure
        return
    assert warm <= cold * 1.2, f"Expected warm path faster or near equal (cold={cold}, warm={warm})"
