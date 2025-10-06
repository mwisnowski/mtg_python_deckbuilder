from __future__ import annotations

import json
from pathlib import Path

from code.web.services.partner_suggestions import (
    configure_dataset_path,
    get_partner_suggestions,
)


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
