"""Comprehensive partner-related internal logic tests.

This file consolidates tests from 4 separate test files:
1. test_partner_scoring.py - Partner suggestion scoring helper tests (5 tests)
2. test_partner_option_filtering.py - Partner option filtering tests (10 tests)
3. test_partner_background_utils.py - Partner/background utility tests (14 tests)
4. test_orchestrator_partner_helpers.py - Orchestrator partner helper tests (1 test)

Total: 30 tests

The tests are organized into logical sections with clear comments for maintainability.
All test logic, imports, and assertions are preserved exactly as they were in the source files.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from code.deck_builder.builder import DeckBuilder
from code.deck_builder.combined_commander import PartnerMode
from code.deck_builder.partner_background_utils import (
    PartnerBackgroundInfo,
    analyze_partner_background,
    extract_partner_with_names,
)
from code.deck_builder.suggestions import (
    PartnerSuggestionContext,
    score_partner_candidate,
)
from code.web.services.commander_catalog_loader import (
    CommanderRecord,
    _row_to_record,
    shared_restricted_partner_label,
)
from code.web.services.orchestrator import _add_secondary_commander_card


# =============================================================================
# SECTION 1: PARTNER SCORING TESTS (from test_partner_scoring.py)
# =============================================================================


def _partner_meta(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "has_partner": False,
        "partner_with": [],
        "supports_backgrounds": False,
        "choose_background": False,
        "is_background": False,
        "is_doctor": False,
        "is_doctors_companion": False,
        "has_plain_partner": False,
        "has_restricted_partner": False,
        "restricted_partner_labels": [],
    }
    base.update(overrides)
    return base


def _commander(
    name: str,
    *,
    color_identity: tuple[str, ...] = tuple(),
    themes: tuple[str, ...] = tuple(),
    role_tags: tuple[str, ...] = tuple(),
    partner_meta: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "display_name": name,
        "color_identity": list(color_identity),
        "themes": list(themes),
        "role_tags": list(role_tags),
        "partner": partner_meta or _partner_meta(),
        "usage": {"primary": 0, "secondary": 0, "total": 0},
    }


def test_partner_with_prefers_canonical_pairing() -> None:
    context = PartnerSuggestionContext(
        theme_cooccurrence={
            "Counters": {"Ramp": 8, "Flyers": 3},
            "Ramp": {"Counters": 8},
            "Flyers": {"Counters": 3},
        },
        pairing_counts={
            ("partner_with", "Halana, Kessig Ranger", "Alena, Kessig Trapper"): 12,
            ("partner_with", "Halana, Kessig Ranger", "Ishai, Ojutai Dragonspeaker"): 1,
        },
    )

    halana = _commander(
        "Halana, Kessig Ranger",
        color_identity=("G",),
        themes=("Counters", "Removal"),
        partner_meta=_partner_meta(
            has_partner=True,
            partner_with=["Alena, Kessig Trapper"],
            has_plain_partner=True,
        ),
    )

    alena = _commander(
        "Alena, Kessig Trapper",
        color_identity=("R",),
        themes=("Ramp", "Counters"),
        role_tags=("Support",),
        partner_meta=_partner_meta(
            has_partner=True,
            partner_with=["Halana, Kessig Ranger"],
            has_plain_partner=True,
        ),
    )

    ishai = _commander(
        "Ishai, Ojutai Dragonspeaker",
        color_identity=("W", "U"),
        themes=("Flyers", "Counters"),
        partner_meta=_partner_meta(
            has_partner=True,
            has_plain_partner=True,
        ),
    )

    alena_score = score_partner_candidate(
        halana,
        alena,
        mode=PartnerMode.PARTNER_WITH,
        context=context,
    )
    ishai_score = score_partner_candidate(
        halana,
        ishai,
        mode=PartnerMode.PARTNER_WITH,
        context=context,
    )

    assert alena_score.score > ishai_score.score
    assert "partner_with_match" in alena_score.notes
    assert "missing_partner_with_link" in ishai_score.notes


def test_background_scoring_prioritizes_legal_backgrounds() -> None:
    context = PartnerSuggestionContext(
        theme_cooccurrence={
            "Counters": {"Card Draw": 6, "Aggro": 2},
            "Card Draw": {"Counters": 6},
            "Treasure": {"Aggro": 2},
        },
        pairing_counts={
            ("background", "Lae'zel, Vlaakith's Champion", "Scion of Halaster"): 9,
        },
    )

    laezel = _commander(
        "Lae'zel, Vlaakith's Champion",
        color_identity=("W",),
        themes=("Counters", "Aggro"),
        partner_meta=_partner_meta(
            supports_backgrounds=True,
        ),
    )

    scion = _commander(
        "Scion of Halaster",
        color_identity=("B",),
        themes=("Card Draw", "Dungeons"),
        partner_meta=_partner_meta(
            is_background=True,
        ),
    )

    guild = _commander(
        "Guild Artisan",
        color_identity=("R",),
        themes=("Treasure",),
        partner_meta=_partner_meta(
            is_background=True,
        ),
    )

    not_background = _commander(
        "Reyhan, Last of the Abzan",
        color_identity=("B", "G"),
        themes=("Counters",),
        partner_meta=_partner_meta(
            has_partner=True,
        ),
    )

    scion_score = score_partner_candidate(
        laezel,
        scion,
        mode=PartnerMode.BACKGROUND,
        context=context,
    )
    guild_score = score_partner_candidate(
        laezel,
        guild,
        mode=PartnerMode.BACKGROUND,
        context=context,
    )
    illegal_score = score_partner_candidate(
        laezel,
        not_background,
        mode=PartnerMode.BACKGROUND,
        context=context,
    )

    assert scion_score.score > guild_score.score
    assert guild_score.score > illegal_score.score
    assert "candidate_not_background" in illegal_score.notes


def test_doctor_companion_scoring_requires_complementary_roles() -> None:
    context = PartnerSuggestionContext(
        theme_cooccurrence={
            "Time Travel": {"Card Draw": 4},
            "Card Draw": {"Time Travel": 4},
        },
        pairing_counts={
            ("doctor_companion", "The Tenth Doctor", "Donna Noble"): 7,
        },
    )

    tenth_doctor = _commander(
        "The Tenth Doctor",
        color_identity=("U", "R"),
        themes=("Time Travel", "Card Draw"),
        partner_meta=_partner_meta(
            is_doctor=True,
        ),
    )

    donna = _commander(
        "Donna Noble",
        color_identity=("W",),
        themes=("Card Draw",),
        partner_meta=_partner_meta(
            is_doctors_companion=True,
        ),
    )

    generic = _commander(
        "Generic Companion",
        color_identity=("G",),
        themes=("Aggro",),
        partner_meta=_partner_meta(
            has_partner=True,
        ),
    )

    donna_score = score_partner_candidate(
        tenth_doctor,
        donna,
        mode=PartnerMode.DOCTOR_COMPANION,
        context=context,
    )
    generic_score = score_partner_candidate(
        tenth_doctor,
        generic,
        mode=PartnerMode.DOCTOR_COMPANION,
        context=context,
    )

    assert donna_score.score > generic_score.score
    assert "doctor_companion_match" in donna_score.notes
    assert "doctor_pairing_illegal" in generic_score.notes


def test_excluded_themes_do_not_inflate_overlap_or_trigger_theme_penalty() -> None:
    context = PartnerSuggestionContext()

    primary = _commander(
        "Sisay, Weatherlight Captain",
        themes=("Legends Matter",),
        partner_meta=_partner_meta(has_partner=True, has_plain_partner=True),
    )

    candidate = _commander(
        "Jodah, the Unifier",
        themes=("Legends Matter",),
        partner_meta=_partner_meta(has_partner=True, has_plain_partner=True),
    )

    result = score_partner_candidate(
        primary,
        candidate,
        mode=PartnerMode.PARTNER,
        context=context,
    )

    assert result.components["overlap"] == 0.0
    assert "missing_theme_metadata" not in result.notes


def test_excluded_themes_removed_from_synergy_calculation() -> None:
    context = PartnerSuggestionContext(
        theme_cooccurrence={
            "Legends Matter": {"Card Draw": 10},
            "Card Draw": {"Legends Matter": 10},
        }
    )

    primary = _commander(
        "Dihada, Binder of Wills",
        themes=("Legends Matter",),
        partner_meta=_partner_meta(has_partner=True, has_plain_partner=True),
    )

    candidate = _commander(
        "Tymna the Weaver",
        themes=("Card Draw",),
        partner_meta=_partner_meta(has_partner=True, has_plain_partner=True),
    )

    result = score_partner_candidate(
        primary,
        candidate,
        mode=PartnerMode.PARTNER,
        context=context,
    )

    assert result.components["synergy"] == 0.0


# =============================================================================
# SECTION 2: OPTION FILTERING TESTS (from test_partner_option_filtering.py)
# =============================================================================


def _build_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Test Commander",
        "faceName": "",
        "side": "",
        "colorIdentity": "G",
        "colors": "G",
        "manaCost": "",
        "manaValue": "",
        "type": "Legendary Creature — Human",
        "creatureTypes": "Human",
        "text": "",
        "power": "",
        "toughness": "",
        "keywords": "",
        "themeTags": "[]",
        "edhrecRank": "",
        "layout": "normal",
    }
    base.update(overrides)
    return base


def test_row_to_record_marks_plain_partner() -> None:
    row = _build_row(text="Partner (You can have two commanders if both have partner.)")
    record = _row_to_record(row, used_slugs=set())

    assert isinstance(record, CommanderRecord)
    assert record.has_plain_partner is True
    assert record.is_partner is True
    assert record.partner_with == tuple()


def test_row_to_record_marks_partner_with_as_restricted() -> None:
    row = _build_row(text="Partner with Foo (You can have two commanders if both have partner.)")
    record = _row_to_record(row, used_slugs=set())

    assert record.has_plain_partner is False
    assert record.is_partner is True
    assert record.partner_with == ("Foo",)


def test_row_to_record_marks_partner_dash_as_restricted() -> None:
    row = _build_row(text="Partner — Survivors (You can have two commanders if both have partner.)")
    record = _row_to_record(row, used_slugs=set())

    assert record.has_plain_partner is False
    assert record.is_partner is True
    assert record.restricted_partner_labels == ("Survivors",)


def test_row_to_record_marks_ascii_dash_partner_as_restricted() -> None:
    row = _build_row(text="Partner - Survivors (They have a unique bond.)")
    record = _row_to_record(row, used_slugs=set())

    assert record.has_plain_partner is False
    assert record.is_partner is True
    assert record.restricted_partner_labels == ("Survivors",)


def test_row_to_record_marks_friends_forever_as_restricted() -> None:
    row = _build_row(text="Friends forever (You can have two commanders if both have friends forever.)")
    record = _row_to_record(row, used_slugs=set())

    assert record.has_plain_partner is False
    assert record.is_partner is True


def test_row_to_record_excludes_doctors_companion_from_plain_partner() -> None:
    row = _build_row(text="Doctor's companion (You can have two commanders if both have a Doctor.)")
    record = _row_to_record(row, used_slugs=set())

    assert record.has_plain_partner is False
    assert record.is_partner is False


def test_shared_restricted_partner_label_detects_overlap() -> None:
    used_slugs: set[str] = set()
    primary = _row_to_record(
        _build_row(
            name="Abby, Merciless Soldier",
            type="Legendary Creature — Human Survivor",
            text="Partner - Survivors (They fight as one.)",
            themeTags="['Partner - Survivors']",
        ),
        used_slugs=used_slugs,
    )
    partner = _row_to_record(
        _build_row(
            name="Bruno, Stalwart Survivor",
            type="Legendary Creature — Human Survivor",
            text="Partner — Survivors (They rally the clan.)",
            themeTags="['Partner - Survivors']",
        ),
        used_slugs=used_slugs,
    )

    assert shared_restricted_partner_label(primary, partner) == "Survivors"
    assert shared_restricted_partner_label(primary, primary) == "Survivors"


def test_row_to_record_decodes_literal_newlines() -> None:
    row = _build_row(text="Partner with Foo\\nFirst strike")
    record = _row_to_record(row, used_slugs=set())

    assert record.partner_with == ("Foo",)


def test_row_to_record_does_not_mark_companion_as_doctor_when_type_line_lacks_subtype() -> None:
    row = _build_row(
        text="Doctor's companion (You can have two commanders if the other is a Doctor.)",
        creatureTypes="['Doctor', 'Human']",
    )
    record = _row_to_record(row, used_slugs=set())

    assert record.is_doctors_companion is True
    assert record.is_doctor is False


def test_row_to_record_requires_time_lord_for_doctor_flag() -> None:
    row = _build_row(type="Legendary Creature — Human Doctor")
    record = _row_to_record(row, used_slugs=set())

    assert record.is_doctor is False


# =============================================================================
# SECTION 3: BACKGROUND UTILS TESTS (from test_partner_background_utils.py)
# =============================================================================


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


# =============================================================================
# SECTION 4: ORCHESTRATOR HELPERS TESTS (from test_orchestrator_partner_helpers.py)
# =============================================================================


def test_add_secondary_commander_card_injects_partner() -> None:
    builder = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
    partner_name = "Pir, Imaginative Rascal"
    combined = SimpleNamespace(secondary_name=partner_name)
    commander_df = pd.DataFrame(
        [
            {
                "name": partner_name,
                "type": "Legendary Creature — Human",
                "manaCost": "{2}{G}",
                "manaValue": 3,
                "creatureTypes": ["Human", "Ranger"],
                "themeTags": ["+1/+1 Counters"],
            }
        ]
    )

    assert partner_name not in builder.card_library

    _add_secondary_commander_card(builder, commander_df, combined)

    assert partner_name in builder.card_library
    entry = builder.card_library[partner_name]
    assert entry["Commander"] is True
    assert entry["Role"] == "commander"
    assert entry["SubRole"] == "Partner"
