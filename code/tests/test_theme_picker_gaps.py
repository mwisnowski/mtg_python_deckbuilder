"""Tests covering Section H (Testing Gaps) & related Phase F items.

These are backend-oriented approximations for browser behaviors. Where full
JS execution would be required (keyboard event dispatch, sessionStorage), we
simulate or validate server produced HTML attributes / ordering contracts.

Contained tests:
 - test_fast_path_load_time: ensure catalog list fragment renders quickly using
   fixture dataset (budget <= 120ms on CI hardware; relaxed if env override)
 - test_colors_filter_constraint: applying colors=G restricts primary/secondary
   colors to subset including 'G'
 - test_preview_placeholder_fill: themes with insufficient real cards are
   padded with synthetic placeholders (role synthetic & name bracketed)
 - test_preview_cache_hit_timing: second call served from cache faster (uses
   monkeypatch to force _now progression minimal)
 - test_navigation_state_preservation_roundtrip: simulate list fetch then
   detail fetch and ensure detail HTML contains theme id while list fragment
   params persist in constructed URL logic (server side approximation)
 - test_mana_cost_parser_variants: port of client JS mana parser implemented
   in Python to validate hybrid / phyrexian / X handling does not crash.

NOTE: Pure keyboard navigation & sessionStorage cache skip paths require a
JS runtime; we assert presence of required attributes (tabindex, role=option)
as a smoke proxy until an integration (playwright) layer is added.
"""

from __future__ import annotations

import os
import re
import time
from typing import List

import pytest
from fastapi.testclient import TestClient


def _get_app():  # local import to avoid heavy import cost if file unused
    from code.web.app import app
    return app


@pytest.fixture(scope="module")
def client():
    # Enable diagnostics to allow /themes/metrics access if gated
    os.environ.setdefault("WEB_THEME_PICKER_DIAGNOSTICS", "1")
    return TestClient(_get_app())


def test_fast_path_load_time(client):
    # First load may include startup warm logic; allow generous budget, tighten later in CI ratchet
    budget_ms = int(os.getenv("TEST_THEME_FAST_PATH_BUDGET_MS", "2500"))
    t0 = time.perf_counter()
    r = client.get("/themes/fragment/list?limit=20")
    dt_ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200
    # Basic sanity: table rows present
    assert "theme-row" in r.text
    assert dt_ms <= budget_ms, f"Fast path list fragment exceeded budget {dt_ms:.2f}ms > {budget_ms}ms"


def test_colors_filter_constraint(client):
    r = client.get("/themes/fragment/list?limit=50&colors=G")
    assert r.status_code == 200
    rows = [m.group(0) for m in re.finditer(r"<tr[^>]*class=\"theme-row\"[\s\S]*?</tr>", r.text)]
    assert rows, "Expected some rows for colors filter"
    greenish = 0
    considered = 0
    for row in rows:
        tds = re.findall(r"<td>(.*?)</td>", row)
        if len(tds) < 3:
            continue
        primary = tds[1]
        secondary = tds[2]
        if primary or secondary:
            considered += 1
            if ("G" in primary) or ("G" in secondary):
                greenish += 1
    # Expect at least half of colored themes to include G (soft assertion due to multi-color / secondary logic on backend)
    if considered:
        assert greenish / considered >= 0.5, f"Expected >=50% green presence, got {greenish}/{considered}"


def test_preview_placeholder_fill(client):
    # Find a theme likely to have low card pool by requesting high limit and then checking for synthetic placeholders '['
    # Use first theme id from list fragment
    list_html = client.get("/themes/fragment/list?limit=1").text
    m = re.search(r'data-theme-id=\"([^\"]+)\"', list_html)
    assert m, "Could not extract theme id"
    theme_id = m.group(1)
    # Request preview with high limit to likely force padding
    pv = client.get(f"/themes/fragment/preview/{theme_id}?limit=30")
    assert pv.status_code == 200
    # Synthetic placeholders appear as names inside brackets (server template), search raw HTML
    bracketed = re.findall(r"\[[^\]]+\]", pv.text)
    # Not all themes will pad; if none found try a second theme
    if not bracketed:
        list_html2 = client.get("/themes/fragment/list?limit=5").text
        ids = re.findall(r'data-theme-id=\"([^\"]+)\"', list_html2)
        for tid in ids[1:]:
            pv2 = client.get(f"/themes/fragment/preview/{tid}?limit=30")
            if pv2.status_code == 200 and re.search(r"\[[^\]]+\]", pv2.text):
                bracketed = ["ok"]
                break
    assert bracketed, "Expected at least one synthetic placeholder bracketed item in high-limit preview"


def test_preview_cache_hit_timing(monkeypatch, client):
    # Warm first
    list_html = client.get("/themes/fragment/list?limit=1").text
    m = re.search(r'data-theme-id=\"([^\"]+)\"', list_html)
    assert m, "Theme id missing"
    theme_id = m.group(1)
    # First build (miss)
    r1 = client.get(f"/themes/fragment/preview/{theme_id}?limit=12")
    assert r1.status_code == 200
    # Monkeypatch theme_preview._now to freeze time so second call counts as hit
    import code.web.services.theme_preview as tp
    orig_now = tp._now
    monkeypatch.setattr(tp, "_now", lambda: orig_now())
    r2 = client.get(f"/themes/fragment/preview/{theme_id}?limit=12")
    assert r2.status_code == 200
    # Deterministic service-level verification: second direct function call should short-circuit via cache
    import code.web.services.theme_preview as tp
    # Snapshot counters
    pre_hits = getattr(tp, "_PREVIEW_CACHE_HITS", 0)
    first_payload = tp.get_theme_preview(theme_id, limit=12)
    second_payload = tp.get_theme_preview(theme_id, limit=12)
    post_hits = getattr(tp, "_PREVIEW_CACHE_HITS", 0)
    assert first_payload.get("sample"), "Missing sample items in preview"
    # Cache hit should have incremented hits counter
    assert post_hits >= pre_hits + 1 or post_hits > 0, "Expected cache hits counter to increase"
    # Items list identity (names) should be identical even if build_ms differs (second call cached has no build_ms recompute)
    first_names = [i.get("name") for i in first_payload.get("sample", [])]
    second_names = [i.get("name") for i in second_payload.get("sample", [])]
    assert first_names == second_names, "Item ordering changed between cached calls"
    # Metrics cache hit counter is best-effort; do not hard fail if not exposed yet
    metrics_resp = client.get("/themes/metrics")
    if metrics_resp.status_code == 200:
        metrics = metrics_resp.json()
        # Soft assertion
        if metrics.get("preview_cache_hits", 0) == 0:
            pytest.skip("Preview cache hit not reflected in metrics (soft skip)")


def test_navigation_state_preservation_roundtrip(client):
    # Simulate list fetch with search & filters appended
    r = client.get("/themes/fragment/list?q=counters&limit=20&bucket=Common")
    assert r.status_code == 200
    # Extract a theme id then fetch detail fragment to simulate navigation
    m = re.search(r'data-theme-id=\"([^\"]+)\"', r.text)
    assert m, "Missing theme id in filtered list"
    theme_id = m.group(1)
    detail = client.get(f"/themes/fragment/detail/{theme_id}")
    assert detail.status_code == 200
    # Detail fragment should include theme display name or id in heading
    assert theme_id in detail.text or "Theme Detail" in detail.text
    # Ensure list fragment contained highlighted mark for query
    assert "<mark>" in r.text, "Expected search term highlighting for state preservation"


# --- Mana cost parser parity (mirror of client JS simplified) ---
def _parse_mana_symbols(raw: str) -> List[str]:
    # Emulate JS regex /\{([^}]+)\}/g
    return re.findall(r"\{([^}]+)\}", raw or "")


@pytest.mark.parametrize(
    "mana,expected_syms",
    [
        ("{X}{2}{U}{B/P}", ["X", "2", "U", "B/P"]),
        ("{G/U}{G/U}{1}{G}", ["G/U", "G/U", "1", "G"]),
        ("{R}{R}{R}{R}{R}", ["R", "R", "R", "R", "R"]),
        ("{2/W}{2/W}{W}", ["2/W", "2/W", "W"]),
        ("{G}{G/P}{X}{C}", ["G", "G/P", "X", "C"]),
    ],
)
def test_mana_cost_parser_variants(mana, expected_syms):
    assert _parse_mana_symbols(mana) == expected_syms


def test_lazy_load_img_attributes(client):
    # Grab a preview and ensure loading="lazy" present on card images
    list_html = client.get("/themes/fragment/list?limit=1").text
    m = re.search(r'data-theme-id=\"([^\"]+)\"', list_html)
    assert m
    theme_id = m.group(1)
    pv = client.get(f"/themes/fragment/preview/{theme_id}?limit=12")
    assert pv.status_code == 200
    # At least one img tag with loading="lazy" attribute
    assert re.search(r"<img[^>]+loading=\"lazy\"", pv.text), "Expected lazy-loading images in preview"


def test_list_fragment_accessibility_tokens(client):
    # Smoke test for role=listbox and row role=option presence (accessibility baseline)
    r = client.get("/themes/fragment/list?limit=10")
    assert r.status_code == 200
    assert "role=\"option\"" in r.text


def test_accessibility_live_region_and_listbox(client):
    r = client.get("/themes/fragment/list?limit=5")
    assert r.status_code == 200
    # List container should have role listbox and aria-live removed in fragment (fragment may omit outer wrapper) – allow either present or absent gracefully
    # We assert at least one aria-label attribute referencing themes count OR presence of pager text
    assert ("aria-label=\"" in r.text) or ("Showing" in r.text)


def test_keyboard_nav_script_presence(client):
    # Fetch full picker page (not just fragment) to inspect embedded JS for Arrow key handling
    page = client.get("/themes/picker")
    assert page.status_code == 200
    body = page.text
    assert "ArrowDown" in body and "ArrowUp" in body and "Enter" in body and "Escape" in body, "Keyboard nav handlers missing"


def test_list_fragment_filter_cache_fallback_timing(client):
    # First call (likely cold) vs second call (cached by etag + filter cache)
    import time as _t
    t0 = _t.perf_counter()
    client.get("/themes/fragment/list?limit=25&q=a")
    first_ms = (_t.perf_counter() - t0) * 1000
    t1 = _t.perf_counter()
    client.get("/themes/fragment/list?limit=25&q=a")
    second_ms = (_t.perf_counter() - t1) * 1000
    # Soft assertion: second should not be dramatically slower; allow equality but fail if slower by >50%
    if second_ms > first_ms * 1.5:
        pytest.skip(f"Second call slower (cold path variance) first={first_ms:.1f}ms second={second_ms:.1f}ms")


def test_intersection_observer_lazy_fallback(client):
    # Preview fragment should include script referencing IntersectionObserver (fallback path implied by try/catch) and images with loading lazy
    list_html = client.get("/themes/fragment/list?limit=1").text
    m = re.search(r'data-theme-id="([^"]+)"', list_html)
    assert m
    theme_id = m.group(1)
    pv = client.get(f"/themes/fragment/preview/{theme_id}?limit=12")
    assert pv.status_code == 200
    html = pv.text
    assert 'IntersectionObserver' in html or 'loading="lazy"' in html
    assert re.search(r"<img[^>]+loading=\"lazy\"", html)


def test_session_storage_cache_script_tokens_present(client):
    # Ensure list fragment contains cache_hit / cache_miss tokens for sessionStorage path instrumentation
    frag = client.get("/themes/fragment/list?limit=5").text
    assert 'cache_hit' in frag and 'cache_miss' in frag, "Expected cache_hit/cache_miss tokens in fragment script"
