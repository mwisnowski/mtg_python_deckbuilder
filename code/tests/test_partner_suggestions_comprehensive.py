"""
Comprehensive Partner Suggestions Tests

This file consolidates partner suggestions tests from multiple sources:
- test_partner_suggestions_service.py (2 tests)
- test_partner_suggestions_pipeline.py (1 test)

Total: 3 tests organized into logical sections
"""

from __future__ import annotations

import json
from pathlib import Path

from code.web.services.partner_suggestions import (
    configure_dataset_path,
    get_partner_suggestions,
)
from code.scripts import build_partner_suggestions as pipeline


# ============================================================================
# Helper Functions & Test Data
# ============================================================================

def _write_dataset(path: Path) -> Path:
    payload = {
        "metadata": {
            "generated_at": "2025-10-06T12:00:00Z",
            "version": "test-fixture",
        },
        "commanders": {
            "akiri_line_slinger": {
                "name": "Akiri, Line-Slinger",
                "display_name": "Akiri, Line-Slinger",
                "color_identity": ["R", "W"],
                "themes": ["Artifacts", "Aggro", "Legends Matter", "Partner"],
                "role_tags": ["Aggro"],
                "partner": {
                    "has_partner": True,
                    "partner_with": ["Silas Renn, Seeker Adept"],
                    "supports_backgrounds": False,
                },
            },
            "silas_renn_seeker_adept": {
                "name": "Silas Renn, Seeker Adept",
                "display_name": "Silas Renn, Seeker Adept",
                "color_identity": ["U", "B"],
                "themes": ["Artifacts", "Value"],
                "role_tags": ["Value"],
                "partner": {
                    "has_partner": True,
                    "partner_with": ["Akiri, Line-Slinger"],
                    "supports_backgrounds": False,
                },
            },
            "ishai_ojutai_dragonspeaker": {
                "name": "Ishai, Ojutai Dragonspeaker",
                "display_name": "Ishai, Ojutai Dragonspeaker",
                "color_identity": ["W", "U"],
                "themes": ["Artifacts", "Counters", "Historics Matter", "Partner - Survivors"],
                "role_tags": ["Aggro"],
                "partner": {
                    "has_partner": True,
                    "partner_with": [],
                    "supports_backgrounds": False,
                },
            },
            "reyhan_last_of_the_abzan": {
                "name": "Reyhan, Last of the Abzan",
                "display_name": "Reyhan, Last of the Abzan",
                "color_identity": ["B", "G"],
                "themes": ["Counters", "Artifacts", "Partner"],
                "role_tags": ["Counters"],
                "partner": {
                    "has_partner": True,
                    "partner_with": [],
                    "supports_backgrounds": False,
                },
            },
        },
        "pairings": {
            "records": [
                {
                    "mode": "partner_with",
                    "primary_canonical": "akiri_line_slinger",
                    "secondary_canonical": "silas_renn_seeker_adept",
                    "count": 12,
                },
                {
                    "mode": "partner",
                    "primary_canonical": "akiri_line_slinger",
                    "secondary_canonical": "ishai_ojutai_dragonspeaker",
                    "count": 6,
                },
                {
                    "mode": "partner",
                    "primary_canonical": "akiri_line_slinger",
                    "secondary_canonical": "reyhan_last_of_the_abzan",
                    "count": 4,
                },
            ]
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


CSV_CONTENT = """name,faceName,colorIdentity,themeTags,roleTags,text,type,partnerWith,supportsBackgrounds,isPartner,isBackground,isDoctor,isDoctorsCompanion
"Halana, Kessig Ranger","Halana, Kessig Ranger","['G']","['Counters','Partner']","['Aggro']","Reach. Partner with Alena, Kessig Trapper.","Legendary Creature — Human Archer","['Alena, Kessig Trapper']",False,True,False,False,False
"Alena, Kessig Trapper","Alena, Kessig Trapper","['R']","['Aggro','Partner']","['Ramp']","First strike. Partner with Halana, Kessig Ranger.","Legendary Creature — Human Scout","['Halana, Kessig Ranger']",False,True,False,False,False
"Wilson, Refined Grizzly","Wilson, Refined Grizzly","['G']","['Teamwork','Backgrounds Matter']","['Aggro']","Choose a Background (You can have a Background as a second commander.)","Legendary Creature — Bear Warrior","[]",True,False,False,False,False
"Guild Artisan","Guild Artisan","['R']","['Background']","[]","Commander creatures you own have \"Whenever this creature attacks...\"","Legendary Enchantment — Background","[]",False,False,True,False,False
"The Tenth Doctor","The Tenth Doctor","['U','R','G']","['Time Travel']","[]","Doctor's companion (You can have two commanders if the other is a Doctor's companion.)","Legendary Creature — Time Lord Doctor","[]",False,False,False,True,False
"Rose Tyler","Rose Tyler","['W']","['Companions']","[]","Doctor's companion","Legendary Creature — Human","[]",False,False,False,False,True
"""


def _write_summary(path: Path, primary: str, secondary: str | None, mode: str, tags: list[str]) -> None:
    payload = {
        "meta": {
            "commander": primary,
            "tags": tags,
        },
        "summary": {
            "commander": {
                "names": [name for name in [primary, secondary] if name],
                "primary": primary,
                "secondary": secondary,
                "partner_mode": mode,
                "color_identity": [],
                "combined": {
                    "primary_name": primary,
                    "secondary_name": secondary,
                    "partner_mode": mode,
                    "color_identity": [],
                },
            }
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, primary: str, secondary: str | None, mode: str) -> None:
    lines = []
    if secondary:
        lines.append(f"# Commanders: {primary}, {secondary}")
    else:
        lines.append(f"# Commander: {primary}")
    lines.append(f"# Partner Mode: {mode}")
    lines.append(f"1 {primary}")
    if secondary:
        lines.append(f"1 {secondary}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ============================================================================
# Partner Suggestions Service Tests
# ============================================================================

def test_get_partner_suggestions_produces_visible_and_hidden(tmp_path: Path) -> None:
    dataset_path = _write_dataset(tmp_path / "partner_synergy.json")
    try:
        configure_dataset_path(dataset_path)
        result = get_partner_suggestions("Akiri, Line-Slinger", limit_per_mode=5)
        assert result is not None
        assert result.total >= 3
        partner_names = [
            "Silas Renn, Seeker Adept",
            "Ishai, Ojutai Dragonspeaker",
            "Reyhan, Last of the Abzan",
        ]
        visible, hidden = result.flatten(partner_names, [], visible_limit=2)
        assert len(visible) == 2
        assert any(item["name"] == "Silas Renn, Seeker Adept" for item in visible)
        assert hidden, "expected additional hidden suggestions"
        assert result.metadata.get("generated_at") == "2025-10-06T12:00:00Z"
    finally:
        configure_dataset_path(None)


def test_noise_themes_suppressed_in_shared_theme_summary(tmp_path: Path) -> None:
    dataset_path = _write_dataset(tmp_path / "partner_synergy.json")
    try:
        configure_dataset_path(dataset_path)
        result = get_partner_suggestions("Akiri, Line-Slinger", limit_per_mode=5)
        assert result is not None
        partner_entries = result.by_mode.get("partner") or []
        target = next((entry for entry in partner_entries if entry["name"] == "Ishai, Ojutai Dragonspeaker"), None)
        assert target is not None, "expected Ishai suggestions to be present"
        assert "Legends Matter" not in target["shared_themes"]
        assert "Historics Matter" not in target["shared_themes"]
        assert "Partner" not in target["shared_themes"]
        assert "Partner - Survivors" not in target["shared_themes"]
        assert all(theme not in {"Legends Matter", "Historics Matter", "Partner", "Partner - Survivors"} for theme in target["candidate_themes"])
        assert "Legends Matter" not in target["summary"]
        assert "Partner" not in target["summary"]
    finally:
        configure_dataset_path(None)


# ============================================================================
# Partner Suggestions Pipeline Tests
# ============================================================================

def test_build_partner_suggestions_creates_dataset(tmp_path: Path) -> None:
    commander_csv = tmp_path / "commander_cards.csv"
    commander_csv.write_text(CSV_CONTENT, encoding="utf-8")

    deck_dir = tmp_path / "deck_files"
    deck_dir.mkdir()

    # Partner deck
    _write_summary(
        deck_dir / "halana_partner.summary.json",
        primary="Halana, Kessig Ranger",
        secondary="Alena, Kessig Trapper",
        mode="partner",
        tags=["Counters", "Aggro"],
    )
    _write_text(
        deck_dir / "halana_partner.txt",
        primary="Halana, Kessig Ranger",
        secondary="Alena, Kessig Trapper",
        mode="partner",
    )

    # Background deck
    _write_summary(
        deck_dir / "wilson_background.summary.json",
        primary="Wilson, Refined Grizzly",
        secondary="Guild Artisan",
        mode="background",
        tags=["Teamwork", "Aggro"],
    )
    _write_text(
        deck_dir / "wilson_background.txt",
        primary="Wilson, Refined Grizzly",
        secondary="Guild Artisan",
        mode="background",
    )

    # Doctor/Companion deck
    _write_summary(
        deck_dir / "doctor_companion.summary.json",
        primary="The Tenth Doctor",
        secondary="Rose Tyler",
        mode="doctor_companion",
        tags=["Time Travel", "Companions"],
    )
    _write_text(
        deck_dir / "doctor_companion.txt",
        primary="The Tenth Doctor",
        secondary="Rose Tyler",
        mode="doctor_companion",
    )

    output_path = tmp_path / "partner_synergy.json"
    result = pipeline.build_partner_suggestions(
        commander_csv=commander_csv,
        deck_dir=deck_dir,
        output_path=output_path,
        max_examples=3,
    )

    assert output_path.exists(), "Expected partner synergy dataset to be created"
    data = json.loads(output_path.read_text(encoding="utf-8"))

    metadata = data["metadata"]
    assert metadata["deck_exports_processed"] == 3
    assert metadata["deck_exports_with_pairs"] == 3
    assert "version_hash" in metadata

    overrides = data["curated_overrides"]
    assert overrides["version"] == metadata["version_hash"]
    assert overrides["entries"] == {}

    mode_counts = data["pairings"]["mode_counts"]
    assert mode_counts == {
        "background": 1,
        "doctor_companion": 1,
        "partner": 1,
    }

    records = data["pairings"]["records"]
    partner_entry = next(item for item in records if item["mode"] == "partner")
    assert partner_entry["primary"] == "Halana, Kessig Ranger"
    assert partner_entry["secondary"] == "Alena, Kessig Trapper"
    assert partner_entry["combined_colors"] == ["R", "G"]

    commanders = data["commanders"]
    halana = commanders["halana, kessig ranger"]
    assert halana["partner"]["has_partner"] is True
    guild_artisan = commanders["guild artisan"]
    assert guild_artisan["partner"]["is_background"] is True

    themes = data["themes"]
    aggro = themes["aggro"]
    assert aggro["deck_count"] == 2
    assert set(aggro["co_occurrence"].keys()) == {"counters", "teamwork"}

    doctor_usage = commanders["the tenth doctor"]["usage"]
    assert doctor_usage == {"primary": 1, "secondary": 0, "total": 1}

    rose_usage = commanders["rose tyler"]["usage"]
    assert rose_usage == {"primary": 0, "secondary": 1, "total": 1}

    partner_tags = partner_entry["tags"]
    assert partner_tags == ["Aggro", "Counters"]

    # round-trip result returned from function should mirror file payload
    assert result == data
