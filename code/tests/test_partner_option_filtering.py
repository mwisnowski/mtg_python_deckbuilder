from __future__ import annotations

from code.web.services.commander_catalog_loader import (
    CommanderRecord,
    _row_to_record,
    shared_restricted_partner_label,
)


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
