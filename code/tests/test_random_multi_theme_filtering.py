from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

from deck_builder import random_entrypoint


def _patch_commanders(monkeypatch, rows: Sequence[dict[str, object]]) -> None:
    df = pd.DataFrame(rows)
    monkeypatch.setattr(random_entrypoint, "_load_commanders_df", lambda: df)


def _make_row(name: str, tags: Iterable[str]) -> dict[str, object]:
    return {"name": name, "themeTags": list(tags)}


def test_random_multi_theme_exact_triple_success(monkeypatch) -> None:
    _patch_commanders(
        monkeypatch,
        [_make_row("Triple Threat", ["aggro", "tokens", "equipment"])],
    )

    res = random_entrypoint.build_random_deck(
        primary_theme="aggro",
        secondary_theme="tokens",
        tertiary_theme="equipment",
        seed=1313,
    )

    assert res.commander == "Triple Threat"
    assert res.resolved_themes == ["aggro", "tokens", "equipment"]
    assert res.combo_fallback is False
    assert res.synergy_fallback is False
    assert res.fallback_reason is None


def test_random_multi_theme_fallback_to_ps(monkeypatch) -> None:
    _patch_commanders(
        monkeypatch,
        [
            _make_row("PrimarySecondary", ["Aggro", "Tokens"]),
            _make_row("Other Commander", ["Tokens", "Equipment"]),
        ],
    )

    res = random_entrypoint.build_random_deck(
        primary_theme="Aggro",
        secondary_theme="Tokens",
        tertiary_theme="Equipment",
        seed=2024,
    )

    assert res.commander == "PrimarySecondary"
    assert res.resolved_themes == ["Aggro", "Tokens"]
    assert res.combo_fallback is True
    assert res.synergy_fallback is False
    assert "Primary+Secondary" in (res.fallback_reason or "")


def test_random_multi_theme_fallback_to_pt(monkeypatch) -> None:
    _patch_commanders(
        monkeypatch,
        [
            _make_row("PrimaryTertiary", ["Aggro", "Equipment"]),
            _make_row("Tokens Only", ["Tokens"]),
        ],
    )

    res = random_entrypoint.build_random_deck(
        primary_theme="Aggro",
        secondary_theme="Tokens",
        tertiary_theme="Equipment",
        seed=777,
    )

    assert res.commander == "PrimaryTertiary"
    assert res.resolved_themes == ["Aggro", "Equipment"]
    assert res.combo_fallback is True
    assert res.synergy_fallback is False
    assert "Primary+Tertiary" in (res.fallback_reason or "")


def test_random_multi_theme_fallback_primary_only(monkeypatch) -> None:
    _patch_commanders(
        monkeypatch,
        [
            _make_row("PrimarySolo", ["Aggro"]),
            _make_row("Tokens Solo", ["Tokens"]),
        ],
    )

    res = random_entrypoint.build_random_deck(
        primary_theme="Aggro",
        secondary_theme="Tokens",
        tertiary_theme="Equipment",
        seed=9090,
    )

    assert res.commander == "PrimarySolo"
    assert res.resolved_themes == ["Aggro"]
    assert res.combo_fallback is True
    assert res.synergy_fallback is False
    assert "Primary only" in (res.fallback_reason or "")


def test_random_multi_theme_synergy_fallback(monkeypatch) -> None:
    _patch_commanders(
        monkeypatch,
        [
            _make_row("Synergy Commander", ["aggro surge"]),
            _make_row("Unrelated", ["tokens"]),
        ],
    )

    res = random_entrypoint.build_random_deck(
        primary_theme="aggro swarm",
        secondary_theme="treasure",
        tertiary_theme="artifacts",
        seed=5150,
    )

    assert res.commander == "Synergy Commander"
    assert res.resolved_themes == ["aggro", "swarm"]
    assert res.combo_fallback is True
    assert res.synergy_fallback is True
    assert "synergy overlap" in (res.fallback_reason or "")


def test_random_multi_theme_full_pool_fallback(monkeypatch) -> None:
    _patch_commanders(
        monkeypatch,
        [_make_row("Any Commander", ["control"])],
    )

    res = random_entrypoint.build_random_deck(
        primary_theme="nonexistent",
        secondary_theme="made up",
        tertiary_theme="imaginary",
        seed=6060,
    )

    assert res.commander == "Any Commander"
    assert res.resolved_themes == []
    assert res.combo_fallback is True
    assert res.synergy_fallback is True
    assert "full commander pool" in (res.fallback_reason or "")


def test_random_multi_theme_sidecar_fields_present(monkeypatch, tmp_path) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    commander_name = "Tri Commander"
    _patch_commanders(
        monkeypatch,
        [_make_row(commander_name, ["Aggro", "Tokens", "Equipment"])],
    )

    import headless_runner

    def _fake_run(
        command_name: str,
        seed: int | None = None,
        primary_choice: int | None = None,
        secondary_choice: int | None = None,
        tertiary_choice: int | None = None,
    ):
        base_path = export_dir / command_name.replace(" ", "_")
        csv_path = base_path.with_suffix(".csv")
        txt_path = base_path.with_suffix(".txt")
        csv_path.write_text("Name\nCard\n", encoding="utf-8")
        txt_path.write_text("Decklist", encoding="utf-8")

        class DummyBuilder:
            def __init__(self) -> None:
                self.commander_name = command_name
                self.commander = command_name
                self.selected_tags = ["Aggro", "Tokens", "Equipment"]
                self.primary_tag = "Aggro"
                self.secondary_tag = "Tokens"
                self.tertiary_tag = "Equipment"
                self.bracket_level = 3
                self.last_csv_path = str(csv_path)
                self.last_txt_path = str(txt_path)
                self.custom_export_base = command_name

            def build_deck_summary(self) -> dict[str, object]:
                return {"meta": {"existing": True}, "counts": {"total": 100}}

            def compute_and_print_compliance(self, base_stem: str | None = None):
                return {"ok": True}

        return DummyBuilder()

    monkeypatch.setattr(headless_runner, "run", _fake_run)

    result = random_entrypoint.build_random_full_deck(
        primary_theme="Aggro",
        secondary_theme="Tokens",
        tertiary_theme="Equipment",
        seed=4242,
    )

    assert result.summary is not None
    meta = result.summary.get("meta")
    assert meta is not None
    assert meta["primary_theme"] == "Aggro"
    assert meta["secondary_theme"] == "Tokens"
    assert meta["tertiary_theme"] == "Equipment"
    assert meta["resolved_themes"] == ["aggro", "tokens", "equipment"]
    assert meta["combo_fallback"] is False
    assert meta["synergy_fallback"] is False
    assert meta["fallback_reason"] is None

    assert result.csv_path is not None
    sidecar_path = Path(result.csv_path).with_suffix(".summary.json")
    assert sidecar_path.is_file()

    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar_meta = payload["meta"]
    assert sidecar_meta["primary_theme"] == "Aggro"
    assert sidecar_meta["secondary_theme"] == "Tokens"
    assert sidecar_meta["tertiary_theme"] == "Equipment"
    assert sidecar_meta["resolved_themes"] == ["aggro", "tokens", "equipment"]
    assert sidecar_meta["random_primary_theme"] == "Aggro"
    assert sidecar_meta["random_resolved_themes"] == ["aggro", "tokens", "equipment"]

    # cleanup
    sidecar_path.unlink(missing_ok=True)
    Path(result.csv_path).unlink(missing_ok=True)
    txt_candidate = Path(result.csv_path).with_suffix(".txt")
    txt_candidate.unlink(missing_ok=True)