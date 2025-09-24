import time
from importlib import reload

from code.web.services import preview_cache as pc
from code.web.services import theme_preview as tp


def test_background_refresh_thread_flag(monkeypatch):
    # Enable background refresh via env
    monkeypatch.setenv("THEME_PREVIEW_BG_REFRESH", "1")
    # Reload preview_cache to re-evaluate env flags
    reload(pc)
    # Simulate a couple of builds to trigger ensure_bg_thread
    # Use a real theme id by invoking preview on first catalog slug
    from code.web.services.theme_catalog_loader import load_index
    idx = load_index()
    slug = sorted(idx.slug_to_entry.keys())[0]
    for _ in range(2):
        tp.get_theme_preview(slug, limit=4)
        time.sleep(0.01)
    # Background thread flag should be set if enabled
    assert getattr(pc, "_BG_REFRESH_ENABLED", False) is True
    assert getattr(pc, "_BG_REFRESH_THREAD_STARTED", False) is True, "background refresh thread did not start"