from __future__ import annotations

from dataclasses import dataclass

import pytest

from code.deck_builder.combined_commander import (
    CombinedCommander,
    PartnerMode,
    build_combined_commander,
)
from exceptions import CommanderPartnerError


@dataclass
class FakeCommander:
    name: str
    display_name: str
    color_identity: tuple[str, ...]
    themes: tuple[str, ...] = ()
    partner_with: tuple[str, ...] = ()
    is_partner: bool = False
    supports_backgrounds: bool = False
    is_background: bool = False
    oracle_text: str = ""
    type_line: str = "Legendary Creature"


@dataclass
class FakeBackground:
    name: str
    display_name: str
    color_identity: tuple[str, ...]
    theme_tags: tuple[str, ...] = ()
    is_background: bool = True
    oracle_text: str = "Commander creatures you own have menace."
    type_line: str = "Legendary Enchantment — Background"


def test_build_combined_commander_none_mode() -> None:
    primary = FakeCommander(
        name="Primary",
        display_name="Primary",
        color_identity=("R", "G"),
        themes=("Aggro", "Tokens"),
    )

    combined = build_combined_commander(primary, None, PartnerMode.NONE)

    assert isinstance(combined, CombinedCommander)
    assert combined.secondary_name is None
    assert combined.color_identity == ("R", "G")
    assert combined.theme_tags == ("Aggro", "Tokens")
    assert combined.warnings == tuple()
    assert combined.raw_tags_secondary == tuple()


def test_build_combined_commander_partner_mode() -> None:
    primary = FakeCommander(
        name="Halana",
        display_name="Halana",
        color_identity=("G",),
        themes=("Aggro",),
        is_partner=True,
    )
    secondary = FakeCommander(
        name="Alena",
        display_name="Alena",
        color_identity=("U",),
        themes=("Control",),
        is_partner=True,
    )

    combined = build_combined_commander(primary, secondary, PartnerMode.PARTNER)

    assert combined.secondary_name == "Alena"
    assert combined.color_identity == ("U", "G")
    assert combined.theme_tags == ("Aggro", "Control")
    assert combined.raw_tags_primary == ("Aggro",)
    assert combined.raw_tags_secondary == ("Control",)


def test_partner_mode_requires_partner_keyword() -> None:
    primary = FakeCommander(
        name="Halana",
        display_name="Halana",
        color_identity=("G",),
        themes=("Aggro",),
        is_partner=True,
    )
    secondary = FakeCommander(
        name="NonPartner",
        display_name="NonPartner",
        color_identity=("U",),
        themes=("Control",),
        is_partner=False,
    )

    with pytest.raises(CommanderPartnerError):
        build_combined_commander(primary, secondary, PartnerMode.PARTNER)


def test_partner_with_mode_requires_matching_pairs() -> None:
    primary = FakeCommander(
        name="Commander A",
        display_name="Commander A",
        color_identity=("W",),
        themes=("Value",),
        partner_with=("Commander B",),
    )
    secondary = FakeCommander(
        name="Commander B",
        display_name="Commander B",
        color_identity=("B",),
        themes=("Graveyard",),
        partner_with=("Commander A",),
    )

    combined = build_combined_commander(primary, secondary, PartnerMode.PARTNER_WITH)

    assert combined.secondary_name == "Commander B"
    assert combined.color_identity == ("W", "B")
    assert combined.theme_tags == ("Value", "Graveyard")


def test_partner_with_mode_invalid_pair_raises() -> None:
    primary = FakeCommander(
        name="Commander A",
        display_name="Commander A",
        color_identity=("W",),
        partner_with=("Commander X",),
    )
    secondary = FakeCommander(
        name="Commander B",
        display_name="Commander B",
        color_identity=("B",),
        partner_with=("Commander A",),
    )

    with pytest.raises(CommanderPartnerError):
        build_combined_commander(primary, secondary, PartnerMode.PARTNER_WITH)


def test_background_mode_success() -> None:
    primary = FakeCommander(
        name="Lae'zel",
        display_name="Lae'zel",
        color_identity=("W",),
        themes=("Counters",),
        supports_backgrounds=True,
    )
    background = FakeBackground(
        name="Scion of Halaster",
        display_name="Scion of Halaster",
        color_identity=("B",),
        theme_tags=("Backgrounds Matter",),
    )

    combined = build_combined_commander(primary, background, PartnerMode.BACKGROUND)

    assert combined.secondary_name == "Scion of Halaster"
    assert combined.color_identity == ("W", "B")
    assert combined.theme_tags == ("Counters", "Backgrounds Matter")


def test_background_mode_requires_support() -> None:
    primary = FakeCommander(
        name="Halana",
        display_name="Halana",
        color_identity=("G",),
        themes=("Aggro",),
        supports_backgrounds=False,
    )
    background = FakeBackground(
        name="Scion of Halaster",
        display_name="Scion of Halaster",
        color_identity=("B",),
    )

    with pytest.raises(CommanderPartnerError):
        build_combined_commander(primary, background, PartnerMode.BACKGROUND)


def test_duplicate_commander_not_allowed() -> None:
    primary = FakeCommander(name="A", display_name="Same", color_identity=("G",), is_partner=True)
    secondary = FakeCommander(name="B", display_name="Same", color_identity=("U",), is_partner=True)

    with pytest.raises(CommanderPartnerError):
        build_combined_commander(primary, secondary, PartnerMode.PARTNER)


def test_colorless_partner_with_colored_results_in_colored_identity_only() -> None:
    primary = FakeCommander(name="Ulamog", display_name="Ulamog", color_identity=tuple(), is_partner=True)
    secondary = FakeCommander(name="Tana", display_name="Tana", color_identity=("G",), is_partner=True)

    combined = build_combined_commander(primary, secondary, PartnerMode.PARTNER)

    assert combined.color_identity == ("G",)


def test_warning_emitted_for_multi_mode_primary() -> None:
    primary = FakeCommander(
        name="Wilson",
        display_name="Wilson",
        color_identity=("G",),
        themes=("Aggro",),
        is_partner=True,
        supports_backgrounds=True,
    )

    combined = build_combined_commander(primary, None, PartnerMode.NONE)

    assert combined.warnings == (
        "Wilson has both Partner and Background abilities; ensure the selected mode is intentional.",
    )


def test_partner_mode_rejects_background_secondary() -> None:
    primary = FakeCommander(
        name="Halana",
        display_name="Halana",
        color_identity=("G",),
        themes=("Aggro",),
        is_partner=True,
    )
    background = FakeBackground(
        name="Scion of Halaster",
        display_name="Scion of Halaster",
        color_identity=("B",),
    )

    with pytest.raises(CommanderPartnerError):
        build_combined_commander(primary, background, PartnerMode.PARTNER)


def test_theme_tags_deduplicate_preserving_order() -> None:
    primary = FakeCommander(
        name="Commander A",
        display_name="Commander A",
        color_identity=("W",),
        themes=("Value", "Control"),
        is_partner=True,
    )
    secondary = FakeCommander(
        name="Commander B",
        display_name="Commander B",
        color_identity=("U",),
        themes=("Control", "Tempo"),
        is_partner=True,
    )

    combined = build_combined_commander(primary, secondary, PartnerMode.PARTNER)

    assert combined.theme_tags == ("Value", "Control", "Tempo")