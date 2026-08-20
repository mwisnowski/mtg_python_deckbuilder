"""Tests for type-family creature type tagging (Outlaw, Party, Sea Monster, Fiend, Undead, Nature)."""
from code.tagging import tag_constants, tag_utils


def test_add_type_family_adds_synthetic_type():
    result = tag_utils.add_type_family(['Zombie'], tag_constants.UNDEAD_TYPES, 'Undead')
    assert result == ['Zombie', 'Undead']


def test_add_type_family_no_match_is_noop():
    result = tag_utils.add_type_family(['Human'], tag_constants.FIEND_TYPES, 'Fiend')
    assert result == ['Human']


def test_add_type_family_does_not_double_add():
    result = tag_utils.add_type_family(['Demon', 'Fiend'], tag_constants.FIEND_TYPES, 'Fiend')
    assert result == ['Demon', 'Fiend']


def test_add_outlaw_type_still_works():
    result = tag_utils.add_outlaw_type(['Pirate'], tag_constants.OUTLAW_TYPES)
    assert result == ['Pirate', 'Outlaw']


def test_rogue_gets_both_outlaw_and_party():
    types = ['Rogue']
    types = tag_utils.add_outlaw_type(types, tag_constants.OUTLAW_TYPES)
    types = tag_utils.add_type_family(types, tag_constants.PARTY_TYPES, 'Party')
    assert types == ['Rogue', 'Outlaw', 'Party']


def test_sea_monster_family_members():
    for member in ['Kraken', 'Leviathan', 'Octopus', 'Serpent']:
        result = tag_utils.add_type_family([member], tag_constants.SEA_MONSTER_TYPES, 'Sea Monster')
        assert result == [member, 'Sea Monster']


def test_nature_family_members():
    for member in ['Plant', 'Treefolk', 'Fungus', 'Saproling']:
        result = tag_utils.add_type_family([member], tag_constants.NATURE_TYPES, 'Nature')
        assert result == [member, 'Nature']
