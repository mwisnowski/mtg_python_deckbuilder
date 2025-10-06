from __future__ import annotations

import logging
from types import SimpleNamespace

import pandas as pd
import pytest

from deck_builder.combined_commander import PartnerMode
from deck_builder.partner_selection import apply_partner_inputs
from exceptions import CommanderPartnerError


class _StubBuilder:
    def __init__(self, dataframe: pd.DataFrame) -> None:
        self._df = dataframe

    def load_commander_data(self) -> pd.DataFrame:
        return self._df.copy(deep=True)


@pytest.fixture()
def builder() -> _StubBuilder:
    data = [
        {
            "name": "Halana, Kessig Ranger",
            "faceName": "Halana, Kessig Ranger",
            "colorIdentity": ["G"],
            "themeTags": ["Aggro"],
            "text": "Reach\nPartner (You can have two commanders if both have partner.)",
            "type": "Legendary Creature — Human Archer",
        },
        {
            "name": "Alena, Kessig Trapper",
            "faceName": "Alena, Kessig Trapper",
            "colorIdentity": ["R"],
            "themeTags": ["Aggro"],
            "text": "First strike\nPartner",
            "type": "Legendary Creature — Human Scout",
        },
        {
            "name": "Lae'zel, Vlaakith's Champion",
            "faceName": "Lae'zel, Vlaakith's Champion",
            "colorIdentity": ["W"],
            "themeTags": ["Counters"],
            "text": "If you would put one or more counters on a creature... Choose a Background (You can have a Background as a second commander.)",
            "type": "Legendary Creature — Gith Warrior",
        },
        {
            "name": "Commander A",
            "faceName": "Commander A",
            "colorIdentity": ["W"],
            "themeTags": ["Value"],
            "text": "Partner with Commander B (When this creature enters the battlefield, target player may put Commander B into their hand from their library, then shuffle.)",
            "type": "Legendary Creature — Advisor",
        },
        {
            "name": "Commander B",
            "faceName": "Commander B",
            "colorIdentity": ["B"],
            "themeTags": ["Graveyard"],
            "text": "Partner with Commander A",
            "type": "Legendary Creature — Advisor",
        },
        {
            "name": "The Tenth Doctor",
            "faceName": "The Tenth Doctor",
            "colorIdentity": ["U", "R"],
            "themeTags": ["Time", "Doctor"],
            "text": "Whenever you cast a spell with cascade, put a time counter on target permanent",
            "type": "Legendary Creature — Time Lord Doctor",
        },
        {
            "name": "Donna Noble",
            "faceName": "Donna Noble",
            "colorIdentity": ["W"],
            "themeTags": ["Support"],
            "text": "Vigilance\nDoctor's companion (You can have two commanders if the other is a Doctor.)",
            "type": "Legendary Creature — Human Advisor",
        },
        {
            "name": "Amy Pond",
            "faceName": "Amy Pond",
            "colorIdentity": ["R"],
            "themeTags": ["Aggro", "Doctor's Companion", "Partner With"],
            "text": (
                "Partner with Rory Williams\\nWhenever Amy Pond deals combat damage to a player, "
                "choose a suspended card you own and remove that many time counters from it.\\n"
                "Doctor's companion (You can have two commanders if the other is the Doctor.)"
            ),
            "type": "Legendary Creature — Human",
        },
        {
            "name": "Rory Williams",
            "faceName": "Rory Williams",
            "colorIdentity": ["W", "U"],
            "themeTags": ["Human", "Doctor's Companion", "Partner With"],
            "text": (
                "Partner with Amy Pond\\nFirst strike, lifelink\\n"
                "Doctor's companion (You can have two commanders if the other is a Doctor.)"
            ),
            "type": "Legendary Creature — Human Soldier",
        },
    ]
    df = pd.DataFrame(data)
    return _StubBuilder(df)


def _background_catalog() -> SimpleNamespace:
    card = SimpleNamespace(
        name="Scion of Halaster",
        display_name="Scion of Halaster",
        color_identity=("B",),
        themes=("Backgrounds Matter",),
        theme_tags=("Backgrounds Matter",),
        oracle_text="Commander creatures you own have menace.",
        type_line="Legendary Enchantment — Background",
        is_background=True,
    )

    class _Catalog:
        def __init__(self, entry: SimpleNamespace) -> None:
            self._entry = entry
            self.entries = (entry,)

        def get(self, name: str) -> SimpleNamespace | None:
            lowered = name.strip().casefold()
            if lowered in {
                self._entry.name.casefold(),
                self._entry.display_name.casefold(),
            }:
                return self._entry
            return None

    return _Catalog(card)


def test_feature_disabled_returns_none(builder: _StubBuilder) -> None:
    result = apply_partner_inputs(
        builder,
        primary_name="Halana, Kessig Ranger",
        secondary_name="Alena, Kessig Trapper",
        feature_enabled=False,
        background_catalog=_background_catalog(),
    )
    assert result is None


def test_conflicting_inputs_raise_error(builder: _StubBuilder) -> None:
    with pytest.raises(CommanderPartnerError):
        apply_partner_inputs(
            builder,
            primary_name="Halana, Kessig Ranger",
            secondary_name="Alena, Kessig Trapper",
            background_name="Scion of Halaster",
            feature_enabled=True,
            background_catalog=_background_catalog(),
        )


def test_background_requires_primary_support(builder: _StubBuilder) -> None:
    with pytest.raises(CommanderPartnerError):
        apply_partner_inputs(
            builder,
            primary_name="Halana, Kessig Ranger",
            background_name="Scion of Halaster",
            feature_enabled=True,
            background_catalog=_background_catalog(),
        )


def test_background_success(builder: _StubBuilder) -> None:
    combined = apply_partner_inputs(
        builder,
        primary_name="Lae'zel, Vlaakith's Champion",
        background_name="Scion of Halaster",
        feature_enabled=True,
        background_catalog=_background_catalog(),
    )
    assert combined is not None
    assert combined.partner_mode is PartnerMode.BACKGROUND
    assert combined.secondary_name == "Scion of Halaster"
    assert combined.color_identity == ("W", "B")


def test_partner_with_detection(builder: _StubBuilder) -> None:
    combined = apply_partner_inputs(
        builder,
        primary_name="Commander A",
        secondary_name="Commander B",
        feature_enabled=True,
        background_catalog=_background_catalog(),
    )
    assert combined is not None
    assert combined.partner_mode is PartnerMode.PARTNER_WITH
    assert combined.color_identity == ("W", "B")


def test_partner_detection(builder: _StubBuilder) -> None:
    combined = apply_partner_inputs(
        builder,
        primary_name="Halana, Kessig Ranger",
        secondary_name="Alena, Kessig Trapper",
        feature_enabled=True,
        background_catalog=_background_catalog(),
    )
    assert combined is not None
    assert combined.partner_mode is PartnerMode.PARTNER
    assert combined.color_identity == ("R", "G")


def test_doctor_companion_pairing(builder: _StubBuilder) -> None:
    combined = apply_partner_inputs(
        builder,
        primary_name="The Tenth Doctor",
        secondary_name="Donna Noble",
        feature_enabled=True,
        background_catalog=_background_catalog(),
    )
    assert combined is not None
    assert combined.partner_mode is PartnerMode.DOCTOR_COMPANION
    assert combined.secondary_name == "Donna Noble"
    assert combined.color_identity == ("W", "U", "R")


def test_doctor_requires_companion(builder: _StubBuilder) -> None:
    with pytest.raises(CommanderPartnerError):
        apply_partner_inputs(
            builder,
            primary_name="The Tenth Doctor",
            secondary_name="Halana, Kessig Ranger",
            feature_enabled=True,
            background_catalog=_background_catalog(),
        )


def test_companion_requires_doctor(builder: _StubBuilder) -> None:
    with pytest.raises(CommanderPartnerError):
        apply_partner_inputs(
            builder,
            primary_name="Donna Noble",
            secondary_name="Commander A",
            feature_enabled=True,
            background_catalog=_background_catalog(),
        )


def test_amy_prefers_partner_with_when_rory_selected(builder: _StubBuilder) -> None:
    combined = apply_partner_inputs(
        builder,
        primary_name="Amy Pond",
        secondary_name="Rory Williams",
        feature_enabled=True,
        background_catalog=_background_catalog(),
    )

    assert combined is not None
    assert combined.partner_mode is PartnerMode.PARTNER_WITH


def test_amy_can_pair_with_the_doctor(builder: _StubBuilder) -> None:
    combined = apply_partner_inputs(
        builder,
        primary_name="Amy Pond",
        secondary_name="The Tenth Doctor",
        feature_enabled=True,
        background_catalog=_background_catalog(),
    )

    assert combined is not None
    assert combined.partner_mode is PartnerMode.DOCTOR_COMPANION


def test_rory_can_partner_with_amy(builder: _StubBuilder) -> None:
    combined = apply_partner_inputs(
        builder,
        primary_name="Rory Williams",
        secondary_name="Amy Pond",
        feature_enabled=True,
        background_catalog=_background_catalog(),
    )

    assert combined is not None
    assert combined.partner_mode is PartnerMode.PARTNER_WITH


def test_logging_emits_partner_mode_selected(caplog: pytest.LogCaptureFixture, builder: _StubBuilder) -> None:
    with caplog.at_level(logging.INFO):
        combined = apply_partner_inputs(
            builder,
            primary_name="Halana, Kessig Ranger",
            secondary_name="Alena, Kessig Trapper",
            feature_enabled=True,
            background_catalog=_background_catalog(),
        )

    assert combined is not None
    records = [record for record in caplog.records if getattr(record, "event", "") == "partner_mode_selected"]
    assert records, "Expected partner_mode_selected log event"
    payload = getattr(records[-1], "payload", {})
    assert payload.get("mode") == PartnerMode.PARTNER.value
    assert payload.get("commanders", {}).get("primary") == "Halana, Kessig Ranger"
    assert payload.get("commanders", {}).get("secondary") == "Alena, Kessig Trapper"
    assert payload.get("colors_before") == ["G"]
    assert payload.get("colors_after") == ["R", "G"]
    assert payload.get("color_delta", {}).get("added") == ["R"]


def test_logging_includes_selection_source(caplog: pytest.LogCaptureFixture, builder: _StubBuilder) -> None:
    with caplog.at_level(logging.INFO):
        combined = apply_partner_inputs(
            builder,
            primary_name="Halana, Kessig Ranger",
            secondary_name="Alena, Kessig Trapper",
            feature_enabled=True,
            background_catalog=_background_catalog(),
            selection_source="suggestion",
        )

    assert combined is not None
    records = [record for record in caplog.records if getattr(record, "event", "") == "partner_mode_selected"]
    assert records, "Expected partner_mode_selected log event"
    payload = getattr(records[-1], "payload", {})
    assert payload.get("selection_source") == "suggestion"