from __future__ import annotations

import json
import sys
from pathlib import Path

import importlib

import pytest

hr = importlib.import_module("code.headless_runner")


def _parse_cli(args: list[str]) -> object:
    parser = hr._build_arg_parser()
    return parser.parse_args(args)


def test_cli_partner_options_in_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DECK_SECONDARY_COMMANDER", raising=False)
    monkeypatch.delenv("ENABLE_PARTNER_MECHANICS", raising=False)
    args = _parse_cli(
        [
            "--commander",
            "Halana, Kessig Ranger",
            "--secondary-commander",
            "Alena, Kessig Trapper",
            "--enable-partner-mechanics",
            "true",
            "--dry-run",
        ]
    )
    json_cfg: dict[str, object] = {}
    secondary = hr._resolve_string_option(args.secondary_commander, "DECK_SECONDARY_COMMANDER", json_cfg, "secondary_commander")
    background = hr._resolve_string_option(args.background, "DECK_BACKGROUND", json_cfg, "background")
    partner_flag = hr._resolve_bool_option(args.enable_partner_mechanics, "ENABLE_PARTNER_MECHANICS", json_cfg, "enable_partner_mechanics")
    assert secondary == "Alena, Kessig Trapper"
    assert background is None
    assert partner_flag is True


def test_cli_background_option_in_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DECK_BACKGROUND", raising=False)
    monkeypatch.delenv("ENABLE_PARTNER_MECHANICS", raising=False)
    args = _parse_cli(
        [
            "--commander",
            "Lae'zel, Vlaakith's Champion",
            "--background",
            "Scion of Halaster",
            "--enable-partner-mechanics",
            "true",
            "--dry-run",
        ]
    )
    json_cfg: dict[str, object] = {}
    background = hr._resolve_string_option(args.background, "DECK_BACKGROUND", json_cfg, "background")
    partner_flag = hr._resolve_bool_option(args.enable_partner_mechanics, "ENABLE_PARTNER_MECHANICS", json_cfg, "enable_partner_mechanics")
    assert background == "Scion of Halaster"
    assert partner_flag is True


def test_env_flag_enables_partner_mechanics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_PARTNER_MECHANICS", "1")
    args = _parse_cli(
        [
            "--commander",
            "Halana, Kessig Ranger",
            "--secondary-commander",
            "Alena, Kessig Trapper",
            "--dry-run",
        ]
    )
    json_cfg: dict[str, object] = {}
    partner_flag = hr._resolve_bool_option(args.enable_partner_mechanics, "ENABLE_PARTNER_MECHANICS", json_cfg, "enable_partner_mechanics")
    assert partner_flag is True


def _extract_json_payload(stdout: str) -> dict[str, object]:
    start = stdout.find("{")
    end = stdout.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise AssertionError(f"Expected JSON object in output, received: {stdout!r}")
    snippet = stdout[start : end + 1]
    return json.loads(snippet)


def test_json_config_secondary_commander_parsing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    config_path = cfg_dir / "deck.json"
    config_payload = {
        "commander": "Halana, Kessig Ranger",
        "secondary_commander": "Alena, Kessig Trapper",
        "enable_partner_mechanics": True,
    }
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")

    monkeypatch.setattr(hr, "_ensure_data_ready", lambda: None)
    monkeypatch.delenv("DECK_SECONDARY_COMMANDER", raising=False)
    monkeypatch.delenv("ENABLE_PARTNER_MECHANICS", raising=False)
    monkeypatch.delenv("DECK_BACKGROUND", raising=False)
    monkeypatch.setattr(sys, "argv", ["headless_runner.py", "--config", str(config_path), "--dry-run"])

    exit_code = hr._main()
    assert exit_code == 0

    captured = capsys.readouterr()
    payload = _extract_json_payload(captured.out.strip())
    assert payload["secondary_commander"] == "Alena, Kessig Trapper"
    assert payload["background"] is None
    assert payload["enable_partner_mechanics"] is True


def test_json_config_background_parsing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir(exist_ok=True)
    config_path = cfg_dir / "deck.json"
    config_payload = {
        "commander": "Lae'zel, Vlaakith's Champion",
        "background": "Scion of Halaster",
        "enable_partner_mechanics": True,
    }
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")

    monkeypatch.setattr(hr, "_ensure_data_ready", lambda: None)
    monkeypatch.delenv("DECK_SECONDARY_COMMANDER", raising=False)
    monkeypatch.delenv("ENABLE_PARTNER_MECHANICS", raising=False)
    monkeypatch.delenv("DECK_BACKGROUND", raising=False)
    monkeypatch.setattr(sys, "argv", ["headless_runner.py", "--config", str(config_path), "--dry-run"])

    exit_code = hr._main()
    assert exit_code == 0

    captured = capsys.readouterr()
    payload = _extract_json_payload(captured.out.strip())
    assert payload["background"] == "Scion of Halaster"
    assert payload["secondary_commander"] is None
    assert payload["enable_partner_mechanics"] is True