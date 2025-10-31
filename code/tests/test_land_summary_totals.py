from __future__ import annotations

from typing import Dict, Any, List

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from code.deck_builder.phases.phase6_reporting import ReportingMixin
from code.deck_builder.summary_telemetry import get_mdfc_metrics, _reset_metrics_for_test


class DummyBuilder(ReportingMixin):
    def __init__(self, card_library: Dict[str, Dict[str, Any]], colors: List[str]):
        self.card_library = card_library
        self.color_identity = colors
        self.output_lines: List[str] = []
        self.output_func = self.output_lines.append
        self._full_cards_df = None
        self._combined_cards_df = None
        self.include_exclude_diagnostics = None
        self.include_cards = []
        self.exclude_cards = []


@pytest.fixture()
def sample_card_library() -> Dict[str, Dict[str, Any]]:
    return {
        "Mountain": {"Card Type": "Land", "Count": 35, "Mana Cost": "", "Role": "", "Tags": []},
        "Branchloft Pathway // Boulderloft Pathway": {
            "Card Type": "Land",
            "Count": 1,
            "Mana Cost": "",
            "Role": "",
            "Tags": [],
        },
        "Valakut Awakening // Valakut Stoneforge": {
            "Card Type": "Instant",
            "Count": 2,
            "Mana Cost": "{2}{R}",
            "Role": "",
            "Tags": [],
        },
        "Cultivate": {"Card Type": "Sorcery", "Count": 1, "Mana Cost": "{2}{G}", "Role": "", "Tags": []},
    }


@pytest.fixture()
def fake_matrix(monkeypatch):
    matrix = {
        "Mountain": {"R": 1},
        "Branchloft Pathway // Boulderloft Pathway": {"G": 1, "W": 1, "_dfc_land": True},
        "Valakut Awakening // Valakut Stoneforge": {
            "R": 1,
            "_dfc_land": True,
            "_dfc_counts_as_extra": True,
        },
        "Cultivate": {},
    }

    def _fake_compute(card_library, *_):
        return matrix

    monkeypatch.setattr("deck_builder.builder_utils.compute_color_source_matrix", _fake_compute)
    return matrix


@pytest.fixture(autouse=True)
def reset_mdfc_metrics():
    _reset_metrics_for_test()
    yield
    _reset_metrics_for_test()


def test_build_deck_summary_includes_mdfc_totals(sample_card_library, fake_matrix):
    builder = DummyBuilder(sample_card_library, ["R", "G"])
    summary = builder.build_deck_summary()

    land_summary = summary.get("land_summary")
    assert land_summary["traditional"] == 36
    assert land_summary["dfc_lands"] == 2
    assert land_summary["with_dfc"] == 38
    assert land_summary["headline"] == "Lands: 36 (38 with DFC)"

    dfc_cards = {card["name"]: card for card in land_summary["dfc_cards"]}
    branch = dfc_cards["Branchloft Pathway // Boulderloft Pathway"]
    assert branch["count"] == 1
    assert set(branch["colors"]) == {"G", "W"}
    assert branch["adds_extra_land"] is False
    assert branch["counts_as_land"] is True
    assert branch["note"] == "Counts as land slot"
    assert "faces" in branch
    assert isinstance(branch["faces"], list) and branch["faces"]
    assert all("mana_cost" in face for face in branch["faces"])

    valakut = dfc_cards["Valakut Awakening // Valakut Stoneforge"]
    assert valakut["count"] == 2
    assert valakut["colors"] == ["R"]
    assert valakut["adds_extra_land"] is True
    assert valakut["counts_as_land"] is False
    assert valakut["note"] == "Adds extra land slot"
    assert any(face.get("produces_mana") for face in valakut.get("faces", []))

    mana_cards = summary["mana_generation"]["cards"]
    red_sources = {item["name"]: item for item in mana_cards["R"]}
    assert red_sources["Valakut Awakening // Valakut Stoneforge"]["dfc"] is True
    assert red_sources["Mountain"]["dfc"] is False


def test_cli_summary_mentions_mdfc_totals(sample_card_library, fake_matrix):
    builder = DummyBuilder(sample_card_library, ["R", "G"])
    builder.print_type_summary()
    joined = "\n".join(builder.output_lines)
    assert "Lands: 36 (38 with DFC)" in joined
    assert "MDFC sources:" in joined


def test_deck_summary_template_renders_land_copy(sample_card_library, fake_matrix):
    builder = DummyBuilder(sample_card_library, ["R", "G"])
    summary = builder.build_deck_summary()

    env = Environment(
        loader=FileSystemLoader("code/web/templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("partials/deck_summary.html")
    html = template.render(
        summary=summary,
        synergies=[],
        game_changers=[],
        owned_set=set(),
        combos=[],
        commander=None,
    )

    assert "Lands: 36 (38 with DFC)" in html
    assert "DFC land" in html


def test_deck_summary_records_mdfc_telemetry(sample_card_library, fake_matrix):
    builder = DummyBuilder(sample_card_library, ["R", "G"])
    builder.build_deck_summary()

    metrics = get_mdfc_metrics()
    assert metrics["total_builds"] == 1
    assert metrics["builds_with_mdfc"] == 1
    assert metrics["total_mdfc_lands"] == 2
    assert metrics["last_summary"]["dfc_lands"] == 2
    top_cards = metrics.get("top_cards") or {}
    assert top_cards.get("Valakut Awakening // Valakut Stoneforge") == 2
    assert top_cards.get("Branchloft Pathway // Boulderloft Pathway") == 1
