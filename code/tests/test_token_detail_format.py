from __future__ import annotations

from code.tagging.tag_utils import format_token_detail_tag


def test_creature_with_keywords():
    # Aligned Heart's Monk token (Roadmap 39 regression case).
    tag = format_token_detail_tag(
        is_creature=True, power="1", toughness="1", colors=["W"],
        creature_type="Monk", keywords=["Prowess"], text="Prowess",
    )
    assert tag == "Token Detail: 1/1 White Monk - Prowess"


def test_creature_with_text_fallback():
    tag = format_token_detail_tag(
        is_creature=True, power="2", toughness="2", colors=["B"],
        creature_type="Zombie", keywords=None, text="",
    )
    assert tag == "Token Detail: 2/2 Black Zombie"


def test_vanilla_creature_no_trailer():
    tag = format_token_detail_tag(
        is_creature=True, power="1", toughness="1", colors=["R"],
        creature_type="Elemental",
    )
    assert tag == "Token Detail: 1/1 Red Elemental"


def test_multicolor_and_multi_subtype():
    tag = format_token_detail_tag(
        is_creature=True, power="4", toughness="4", colors=["W", "R"],
        creature_type=["Human", "Soldier"], keywords=["Flying", "Vigilance"],
    )
    assert tag == "Token Detail: 4/4 White and Red Human Soldier - Flying, Vigilance"


def test_non_creature_token():
    tag = format_token_detail_tag(is_creature=False, token_type="Treasure")
    assert tag == "Token Detail: Treasure Token"


def test_non_creature_role_token():
    tag = format_token_detail_tag(is_creature=False, token_type="Monster Role")
    assert tag == "Token Detail: Monster Role Token"
