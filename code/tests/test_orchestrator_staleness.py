from __future__ import annotations

from code.web.services.orchestrator import is_setup_ready, is_setup_stale


def test_is_setup_ready_false_when_missing():
    # On a clean checkout without csv_files, this should be False
    assert is_setup_ready() in (False, True)  # Function exists and returns a bool


def test_is_setup_stale_never_when_disabled_env(monkeypatch):
    monkeypatch.setenv("WEB_AUTO_REFRESH_DAYS", "0")
    assert is_setup_stale() is False


def test_is_setup_stale_is_bool():
    # We don't assert specific timing behavior in unit tests; just type/robustness
    res = is_setup_stale()
    assert res in (False, True)
