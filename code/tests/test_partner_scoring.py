"""Unit tests for partner suggestion scoring helper."""

from __future__ import annotations

from code.deck_builder.combined_commander import PartnerMode
from code.deck_builder.suggestions import (
    PartnerSuggestionContext,
    score_partner_candidate,
)


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
