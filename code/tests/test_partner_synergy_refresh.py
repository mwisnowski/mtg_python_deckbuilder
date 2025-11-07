from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, Optional

from code.web.services import orchestrator


def _setup_fake_root(tmp_path: Path) -> Path:
    root = tmp_path
    scripts_dir = root / "code" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "build_partner_suggestions.py").write_text("print('noop')\n", encoding="utf-8")

    (root / "config" / "themes").mkdir(parents=True, exist_ok=True)
    (root / "csv_files").mkdir(parents=True, exist_ok=True)
    (root / "deck_files").mkdir(parents=True, exist_ok=True)

    (root / "config" / "themes" / "theme_list.json").write_text("{}\n", encoding="utf-8")
    (root / "csv_files" / "commander_cards.csv").write_text("name\nTest Commander\n", encoding="utf-8")

    return root


def _invoke_helper(
    root: Path,
    monkeypatch,
    *,
    force: bool = False,
    out_func: Optional[Callable[[str], None]] = None,
) -> list[tuple[list[str], str]]:
    calls: list[tuple[list[str], str]] = []

    def _fake_run(cmd, check=False, cwd=None):
        calls.append((list(cmd), cwd))
        class _Completed:
            returncode = 0
        return _Completed()

    monkeypatch.setattr(orchestrator.subprocess, "run", _fake_run)
    orchestrator._maybe_refresh_partner_synergy(out_func, force=force, root=str(root))
    return calls


def test_partner_synergy_refresh_invokes_script_when_missing(tmp_path, monkeypatch) -> None:
    root = _setup_fake_root(tmp_path)
    calls = _invoke_helper(root, monkeypatch, force=False)
    assert len(calls) == 1
    cmd, cwd = calls[0]
    assert cmd[0] == orchestrator.sys.executable
    assert cmd[1].endswith("build_partner_suggestions.py")
    assert cwd == str(root)


def test_partner_synergy_refresh_skips_when_dataset_fresh(tmp_path, monkeypatch) -> None:
    root = _setup_fake_root(tmp_path)
    analytics_dir = root / "config" / "analytics"
    analytics_dir.mkdir(parents=True, exist_ok=True)
    dataset = analytics_dir / "partner_synergy.json"
    dataset.write_text("{}\n", encoding="utf-8")

    now = time.time()
    os.utime(dataset, (now, now))
    source_time = now - 120
    for rel in ("config/themes/theme_list.json", "csv_files/commander_cards.csv"):
        src = root / rel
        os.utime(src, (source_time, source_time))

    calls = _invoke_helper(root, monkeypatch, force=False)
    assert calls == []


def test_partner_synergy_refresh_honors_force_flag(tmp_path, monkeypatch) -> None:
    root = _setup_fake_root(tmp_path)
    analytics_dir = root / "config" / "analytics"
    analytics_dir.mkdir(parents=True, exist_ok=True)
    dataset = analytics_dir / "partner_synergy.json"
    dataset.write_text("{}\n", encoding="utf-8")
    now = time.time()
    os.utime(dataset, (now, now))
    for rel in ("config/themes/theme_list.json", "csv_files/commander_cards.csv"):
        src = root / rel
        os.utime(src, (now, now))

    calls = _invoke_helper(root, monkeypatch, force=True)
    assert len(calls) == 1
    cmd, cwd = calls[0]
    assert cmd[1].endswith("build_partner_suggestions.py")
    assert cwd == str(root)
