from __future__ import annotations

from code.deck_builder.partner_background_utils import (
    PartnerBackgroundInfo,
    analyze_partner_background,
    extract_partner_with_names,
)


def test_extract_partner_with_names_handles_multiple() -> None:
    text = "Partner with Foo, Bar and Baz (Each half of the pair may be your commander.)"
    assert extract_partner_with_names(text) == ("Foo", "Bar", "Baz")


def test_extract_partner_with_names_deduplicates() -> None:
    text = "Partner with Foo, Foo, Bar. Partner with Baz"
    assert extract_partner_with_names(text) == ("Foo", "Bar", "Baz")


def test_analyze_partner_background_detects_keywords() -> None:
    info = analyze_partner_background(
        type_line="Legendary Creature — Ally",
        oracle_text="Partner (You can have two commanders if both have partner.)",
        theme_tags=("Legends Matter",),
    )
    assert info == PartnerBackgroundInfo(
        has_partner=True,
        partner_with=tuple(),
        choose_background=False,
        is_background=False,
        is_doctor=False,
        is_doctors_companion=False,
        has_plain_partner=True,
        has_restricted_partner=False,
        restricted_partner_labels=tuple(),
    )


def test_analyze_partner_background_detects_choose_background_via_theme() -> None:
    info = analyze_partner_background(
        type_line="Legendary Creature",
        oracle_text="",
        theme_tags=("Choose a Background",),
    )
    assert info.choose_background is True


def test_choose_background_commander_not_marked_as_background() -> None:
    info = analyze_partner_background(
        type_line="Legendary Creature — Human Warrior",
        oracle_text=(
            "Choose a Background (You can have a Background as a second commander.)"
        ),
        theme_tags=("Backgrounds Matter", "Choose a Background"),
    )
    assert info.choose_background is True
    assert info.is_background is False


def test_analyze_partner_background_detects_background_from_type() -> None:
    info = analyze_partner_background(
        type_line="Legendary Enchantment — Background",
        oracle_text="Commander creatures you own have menace.",
        theme_tags=(),
    )
    assert info.is_background is True


def test_analyze_partner_background_rejects_false_positive() -> None:
    info = analyze_partner_background(
        type_line="Legendary Creature — Human",
        oracle_text="This creature enjoys partnership events.",
        theme_tags=("Legends Matter",),
    )
    assert info.has_partner is False
    assert info.has_plain_partner is False
    assert info.has_restricted_partner is False


def test_analyze_partner_background_detects_partner_with_as_restricted() -> None:
    info = analyze_partner_background(
        type_line="Legendary Creature — Human",
        oracle_text="Partner with Foo (They go on adventures together.)",
        theme_tags=(),
    )
    assert info.has_partner is True
    assert info.has_plain_partner is False
    assert info.has_restricted_partner is True


def test_analyze_partner_background_requires_time_lord_for_doctor() -> None:
    info = analyze_partner_background(
        type_line="Legendary Creature — Time Lord Doctor",
        oracle_text="When you cast a spell, do the thing.",
        theme_tags=(),
    )
    assert info.is_doctor is True

    non_time_lord = analyze_partner_background(
        type_line="Legendary Creature — Doctor",
        oracle_text="When you cast a spell, do the other thing.",
        theme_tags=("Doctor",),
    )
    assert non_time_lord.is_doctor is False

    tagged_only = analyze_partner_background(
        type_line="Legendary Creature — Doctor",
        oracle_text="When you cast a spell, do the other thing.",
        theme_tags=("Time Lord Doctor",),
    )
    assert tagged_only.is_doctor is False


def test_analyze_partner_background_extracts_dash_restriction_label() -> None:
    info = analyze_partner_background(
        type_line="Legendary Creature — Survivor",
        oracle_text="Partner - Survivors (They can only team up with their own.)",
        theme_tags=(),
    )
    assert info.restricted_partner_labels == ("Survivors",)


def test_analyze_partner_background_uses_theme_restriction_label() -> None:
    info = analyze_partner_background(
        type_line="Legendary Creature — God Warrior",
        oracle_text="Partner — Father & Son (They go to battle together.)",
        theme_tags=("Partner - Father & Son",),
    )
    assert info.restricted_partner_labels[0].casefold() == "father & son"


def test_analyze_partner_background_detects_restricted_partner_keyword() -> None:
    info = analyze_partner_background(
        type_line="Legendary Creature — Survivor",
        oracle_text="Partner — Survivors (They stand together.)",
        theme_tags=(),
    )
    assert info.has_partner is True
    assert info.has_plain_partner is False
    assert info.has_restricted_partner is True


def test_analyze_partner_background_detects_ascii_dash_partner_restriction() -> None:
    info = analyze_partner_background(
        type_line="Legendary Creature — Survivor",
        oracle_text="Partner - Survivors (They can only team up with their own.)",
        theme_tags=(),
    )
    assert info.has_partner is True
    assert info.has_plain_partner is False
    assert info.has_restricted_partner is True


def test_analyze_partner_background_marks_friends_forever_as_restricted() -> None:
    info = analyze_partner_background(
        type_line="Legendary Creature — Human",
        oracle_text="Friends forever (You can have two commanders if both have friends forever.)",
        theme_tags=(),
    )
    assert info.has_partner is True
    assert info.has_plain_partner is False
    assert info.has_restricted_partner is True