"""Tests for background option fallback logic in the web build route."""

from __future__ import annotations

from code.web import app  # noqa: F401  # Ensure app is initialized prior to build import
from code.web.routes import build
from code.web.services.commander_catalog_loader import find_commander_record


def test_build_background_options_falls_back_to_commander_catalog(monkeypatch):
    """When the background CSV is unavailable, commander catalog data is used."""

    def _raise_missing(*_args, **_kwargs):
        raise FileNotFoundError("missing background csv")

    monkeypatch.setattr(build, "load_background_cards", _raise_missing)

    options = build._build_background_options()

    assert options, "Expected fallback to provide background options"
    names = [opt["name"] for opt in options]
    assert len(names) == len(set(name.casefold() for name in names)), "Background options should be unique"

    for name in names:
        record = find_commander_record(name)
        assert record is not None, f"Commander catalog missing background record for {name}"
        assert record.is_background, f"Expected {name} to be marked as a Background"
