"""Targeted tests for the commander-eligibility check in
code/scripts/generate_theme_editorial_suggestions.py.
"""
from code.scripts.generate_theme_editorial_suggestions import _is_commander_eligible


def test_legendary_creature_is_eligible():
    assert _is_commander_eligible('Legendary Creature — Human Wizard', 'Tap: draw a card.') is True


def test_legendary_non_creature_permanent_is_not_eligible():
    # e.g. Nicol Bolas, Dragon-God / Sword of the Animist style cards previously
    # false-positived as commander-eligible via a crude "Legendary" substring check.
    assert _is_commander_eligible('Legendary Planeswalker — Bolas', 'Static ability text.') is False
    assert _is_commander_eligible('Legendary Artifact — Equipment', 'Equip {2}') is False


def test_can_be_your_commander_text_is_eligible():
    assert _is_commander_eligible('Planeswalker — Bolas', 'This planeswalker can be your commander.') is True


def test_background_type_is_eligible():
    assert _is_commander_eligible('Legendary Enchantment — Background', 'Choose a Background.') is True
