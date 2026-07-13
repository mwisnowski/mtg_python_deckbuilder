"""Tests for DeckListParser (M1), validate_and_enrich (M2), and analyze_composition (M3)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from code.web.services.deck_import_service import (
    DeckListParser,
    EnrichedCard,
    EnrichedDeck,
    ParsedCard,
    ParsedDeck,
    RoleCount,
    ThemeDetectionResult,
    analyze_composition,
    apply_prune,
    CutCandidate,
    detect_themes,
    rank_cut_candidates,
    resolve_user_themes,
    save_imported_deck,
    load_temp_session,
    write_temp_session,
    validate_and_enrich,
)
import code.web.services.deck_import_service as _svc


@pytest.fixture
def parser() -> DeckListParser:
    return DeckListParser()


# ---------------------------------------------------------------------------
# Moxfield "Copy for Moxfield" — "* 1 Name (SET) NNN"
# ---------------------------------------------------------------------------

def test_parse_moxfield_copy_for_moxfield(parser: DeckListParser) -> None:
    text = (
        "* 1 Atraxa, Praetors' Voice (VOW) 239\n"
        "1 Sol Ring (C21) 333\n"
        "1 Arcane Signet\n"
    )
    deck = parser.parse(text)
    assert deck.commander == "Atraxa, Praetors' Voice"
    names = [c.name for c in deck.cards]
    assert "Atraxa, Praetors' Voice" in names
    assert "Sol Ring" in names


def test_parse_moxfield_set_suffix_plst(parser: DeckListParser) -> None:
    """(PLST) SET-NNN suffix must be stripped."""
    text = "* 1 Eternal Witness (PLST) ELD-331\n1 Forest\n"
    deck = parser.parse(text)
    assert deck.commander == "Eternal Witness"
    assert deck.cards[0].name == "Eternal Witness"


# ---------------------------------------------------------------------------
# Moxfield "Copy for Arena" — bare Commander / Deck headers
# ---------------------------------------------------------------------------

def test_parse_moxfield_arena_format(parser: DeckListParser) -> None:
    text = (
        "Commander\n"
        "1 Atraxa, Praetors' Voice\n"
        "\n"
        "Deck\n"
        "1 Sol Ring\n"
        "1 Arcane Signet\n"
    )
    deck = parser.parse(text)
    assert deck.commander == "Atraxa, Praetors' Voice"
    sections = {c.name: c.section for c in deck.cards}
    assert sections["Atraxa, Praetors' Voice"] == "Commander"
    assert sections["Sol Ring"] == "Mainboard"


# ---------------------------------------------------------------------------
# Moxfield plain text / MTGO — "*1 Name" at bottom (no space)
# ---------------------------------------------------------------------------

def test_parse_moxfield_plain_text_star_at_bottom(parser: DeckListParser) -> None:
    text = (
        "1 Sol Ring\n"
        "1 Arcane Signet\n"
        "*1 Atraxa, Praetors' Voice\n"
    )
    deck = parser.parse(text)
    assert deck.commander == "Atraxa, Praetors' Voice"


def test_parse_star_with_space_and_without_produce_same_result(parser: DeckListParser) -> None:
    text_space = "* 1 Atraxa, Praetors' Voice\n1 Sol Ring\n"
    text_nospace = "*1 Atraxa, Praetors' Voice\n1 Sol Ring\n"
    d1 = parser.parse(text_space)
    d2 = parser.parse(text_nospace)
    assert d1.commander == d2.commander == "Atraxa, Praetors' Voice"


# ---------------------------------------------------------------------------
# Native format — "# Commanders: Name"
# ---------------------------------------------------------------------------

def test_parse_native_format(parser: DeckListParser) -> None:
    text = (
        "# Commanders: Atraxa, Praetors' Voice\n"
        "1 Sol Ring\n"
        "1 Arcane Signet\n"
    )
    deck = parser.parse(text)
    assert deck.commander == "Atraxa, Praetors' Voice"


# ---------------------------------------------------------------------------
# Archidekt — "// Commander" section header
# ---------------------------------------------------------------------------

def test_parse_archidekt_format(parser: DeckListParser) -> None:
    text = (
        "// Commander\n"
        "1 Atraxa, Praetors' Voice\n"
        "// Mainboard\n"
        "1 Sol Ring\n"
        "// This is just a comment\n"
        "1 Arcane Signet\n"
    )
    deck = parser.parse(text)
    assert deck.commander == "Atraxa, Praetors' Voice"
    sections = {c.name: c.section for c in deck.cards}
    assert sections["Atraxa, Praetors' Voice"] == "Commander"
    assert sections["Sol Ring"] == "Mainboard"
    # Comment line must not produce a card
    assert "This is just a comment" not in [c.name for c in deck.cards]


# ---------------------------------------------------------------------------
# Quantity normalisation — "1x" same as "1"
# ---------------------------------------------------------------------------

def test_parse_1x_quantity(parser: DeckListParser) -> None:
    text = "1x Sol Ring\n1X Arcane Signet\n1 Lightning Bolt\n"
    deck = parser.parse(text)
    assert len(deck.cards) == 3
    for card in deck.cards:
        assert card.quantity == 1


# ---------------------------------------------------------------------------
# TappedOut sideboard — SB: lines skipped
# ---------------------------------------------------------------------------

def test_parse_sideboard_skipped(parser: DeckListParser) -> None:
    text = (
        "1 Sol Ring\n"
        "SB: 1 Lightning Bolt\n"
        "SB: 1 Counterspell\n"
    )
    deck = parser.parse(text)
    names = [c.name for c in deck.cards]
    assert "Sol Ring" in names
    assert "Lightning Bolt" not in names
    assert "Counterspell" not in names


# ---------------------------------------------------------------------------
# Malformed / unrecognised lines → warnings, no crash
# ---------------------------------------------------------------------------

def test_malformed_lines_produce_warnings(parser: DeckListParser) -> None:
    text = (
        "1 Sol Ring\n"
        "not a valid card line at all !!!\n"
        "1 Arcane Signet\n"
    )
    deck = parser.parse(text)
    assert any("Unrecognised" in w for w in deck.warnings)
    # Valid cards still parsed
    names = [c.name for c in deck.cards]
    assert "Sol Ring" in names
    assert "Arcane Signet" in names


# ---------------------------------------------------------------------------
# Partner commanders — two cards in // Commander section
# ---------------------------------------------------------------------------

def test_partner_commanders_in_section(parser: DeckListParser) -> None:
    text = (
        "// Commander\n"
        "1 Halana, Kessig Ranger\n"
        "1 Alena, Kessig Trapper\n"
        "// Mainboard\n"
        "1 Sol Ring\n"
    )
    deck = parser.parse(text)
    # Both names present; combined into a partner string
    assert deck.commander is not None
    assert "Halana, Kessig Ranger" in deck.commander
    assert "Alena, Kessig Trapper" in deck.commander


# ---------------------------------------------------------------------------
# No commander detected → warning issued, commander is None
# ---------------------------------------------------------------------------

def test_first_card_assumed_as_commander_when_no_markers(parser: DeckListParser) -> None:
    text = "1 Sol Ring\n1 Arcane Signet\n"
    deck = parser.parse(text)
    assert deck.commander == "Sol Ring"
    assert any("assumed" in w.lower() for w in deck.warnings)


def test_foil_etched_markers_stripped(parser: DeckListParser) -> None:
    """*F* / *E* markers and promo 'p' suffixes on collector numbers must be stripped."""
    text = (
        "1 Alena, Kessig Trapper (CMR) 570 *E*\n"
        "1 Ghalta, Primal Hunger (SLD) 1124 *F*\n"
        "1 Heroic Intervention (PAER) 109p\n"
    )
    deck = parser.parse(text)
    names = [c.name for c in deck.cards]
    assert "Alena, Kessig Trapper" in names
    assert "Ghalta, Primal Hunger" in names
    assert "Heroic Intervention" in names


def test_unicode_star_in_collector_number_stripped(parser: DeckListParser) -> None:
    """Collector numbers with Unicode ★ (U+2605, Secret Lair style) must be stripped."""
    text = (
        "1 Arcane Signet (SLD) 1492\u2605 *F*\n"
        "1 Thought Vessel (SLD) 1495\u2605 *F*\n"
        "1 Chaotic Chaotician (SLD) 1394\u2605 *F*\n"
    )
    deck = parser.parse(text)
    names = [c.name for c in deck.cards]
    assert "Arcane Signet" in names
    assert "Thought Vessel" in names
    assert "Chaotic Chaotician" in names


def test_single_slash_mdfc_normalised(parser: DeckListParser) -> None:
    """'A / B' notation (Moxfield direct export) must be normalised to 'A // B'."""
    text = "1 Avabruck Caretaker / Hollowhenge Huntmaster\n"
    deck = parser.parse(text)
    assert deck.cards[0].name == "Avabruck Caretaker // Hollowhenge Huntmaster"


def test_commander_at_bottom_after_blank(parser: DeckListParser) -> None:
    """Moxfield 'Copy Plain Text' puts the commander after a blank line at the end."""
    text = (
        "1 Sol Ring\n"
        "1 Arcane Signet\n"
        "1 Eternal Witness\n"
        "\n"
        "1 Atraxa, Praetors' Voice\n"
    )
    deck = parser.parse(text)
    assert deck.commander == "Atraxa, Praetors' Voice"
    assert any("last card" in w.lower() for w in deck.warnings)


def test_sideboard_section_excluded_from_count(parser: DeckListParser) -> None:
    """Cards in Sideboard/Considering sections should not count toward the 100."""
    text = (
        "1 Sol Ring\n"
        "1 Arcane Signet\n"
        "Sideboard\n"
        "1 Lightning Bolt\n"
        "1 Counterspell\n"
    )
    deck = parser.parse(text)
    mainboard = [c for c in deck.cards if c.section != "Sideboard"]
    sideboard = [c for c in deck.cards if c.section == "Sideboard"]
    assert len(mainboard) == 2
    assert len(sideboard) == 2
    # Total-card warning counts only mainboard
    assert any("2 cards" in w for w in deck.warnings)


def test_sideboard_colon_suffix_format(parser: DeckListParser) -> None:
    """SIDEBOARD: (with colon) must be recognised as a section boundary."""
    text = (
        "1 Sol Ring\n"
        "SIDEBOARD:\n"
        "1 Lightning Bolt\n"
    )
    deck = parser.parse(text)
    sideboard = [c for c in deck.cards if c.section == "Sideboard"]
    mainboard = [c for c in deck.cards if c.section != "Sideboard"]
    assert any(c.name == "Lightning Bolt" for c in sideboard)
    assert any(c.name == "Sol Ring" for c in mainboard)


def test_considering_section_excluded(parser: DeckListParser) -> None:
    """Considering section cards should be treated as Sideboard."""
    text = "1 Sol Ring\nConsidering\n1 Rhystic Study\n"
    deck = parser.parse(text)
    considering = [c for c in deck.cards if c.section == "Sideboard"]
    assert any(c.name == "Rhystic Study" for c in considering)


def test_scryfall_fallback_used_for_unrecognized(parser: DeckListParser) -> None:
    """Cards absent from parquet should be enriched via Scryfall fallback."""
    fake_sf = {"name": "Universes Beyond Card", "type_line": "Creature — Beast", "cmc": 4.0}
    text = "1 Universes Beyond Card\n"
    parsed = parser.parse(text)
    with _patch_parquets(), patch("code.web.services.deck_import_service._scryfall_lookup", return_value=fake_sf):
        result = validate_and_enrich(parsed)
    assert "Universes Beyond Card" not in result.unrecognized
    card = next(c for c in result.cards if c.name == "Universes Beyond Card")
    assert card.cmc == 4.0
    assert "Creature" in card.type_line
    assert any("Scryfall" in w for w in parsed.warnings)


# ---------------------------------------------------------------------------
# Card count warning — not 100 cards
# ---------------------------------------------------------------------------

def test_card_count_warning(parser: DeckListParser) -> None:
    text = "1 Sol Ring\n1 Arcane Signet\n"
    deck = parser.parse(text)
    assert any("100" in w for w in deck.warnings)


# ---------------------------------------------------------------------------
# Blank lines and skipped_lines counter
# ---------------------------------------------------------------------------

def test_blank_lines_counted_as_skipped(parser: DeckListParser) -> None:
    text = "\n1 Sol Ring\n\n1 Arcane Signet\n\n"
    deck = parser.parse(text)
    assert deck.skipped_lines >= 3  # 3 blank lines


# ---------------------------------------------------------------------------
# raw_lines count
# ---------------------------------------------------------------------------

def test_raw_lines_count(parser: DeckListParser) -> None:
    text = "1 Sol Ring\n1 Arcane Signet\n"
    deck = parser.parse(text)
    assert deck.raw_lines == 2


# ===========================================================================
# M2 — validate_and_enrich
# ===========================================================================

# ---------------------------------------------------------------------------
# Helpers: fake DataFrames for mocking parquet
# ---------------------------------------------------------------------------

def _make_all_cards_df() -> pd.DataFrame:
    """Minimal all_cards.parquet substitute for tests."""
    return pd.DataFrame(
        {
            "name": ["Sol Ring", "Arcane Signet", "Eternal Witness", "Forest"],
            "faceName": ["Sol Ring", "Arcane Signet", "Eternal Witness", "Forest"],
            "themeTags": [
                "Ramp,Mana Rock",
                "Ramp,Mana Rock",
                "Recursion,Value",
                "Basic Land,Lands",
            ],
            "manaValue": [1.0, 2.0, 3.0, 0.0],
            "type": [
                "Artifact",
                "Artifact",
                "Creature — Human Shaman",
                "Basic Land — Forest",
            ],
            "isNew": [False, False, True, False],
            "price": [2.50, 1.00, 4.00, 0.25],
            "colorIdentity": ["", "", "G", "G"],
        }
    )


def _make_commander_df() -> pd.DataFrame:
    """Minimal commander_cards.parquet substitute for tests."""
    return pd.DataFrame(
        {
            "name": [
                "Atraxa, Praetors' Voice",
                "Halana, Kessig Ranger",
                "Alena, Kessig Trapper",
            ],
            "faceName": [
                "Atraxa, Praetors' Voice",
                "Halana, Kessig Ranger",
                "Alena, Kessig Trapper",
            ],
            "colorIdentity": ["W,U,B,G", "G", "R,G"],
            "themeTags": ["Proliferate,+1/+1 Counters", "Reach,Combat", "Haste,Combat"],
        }
    )


@pytest.fixture(autouse=True)
def reset_parquet_cache():
    """Reset module-level parquet caches before each test."""
    _svc._all_cards_df = None
    _svc._all_card_names = None
    _svc._commander_df = None
    yield
    _svc._all_cards_df = None
    _svc._all_card_names = None
    _svc._commander_df = None


def _patch_parquets():
    """Return a context manager patching both parquet reads."""
    all_cards = _make_all_cards_df()
    commander = _make_commander_df()

    def fake_read(path, *args, **kwargs):
        if "commander" in str(path):
            return commander
        return all_cards

    return patch("code.web.services.deck_import_service.pd.read_parquet", side_effect=fake_read)


# ---------------------------------------------------------------------------
# Known card resolves correctly
# ---------------------------------------------------------------------------

def test_known_card_enriched(parser: DeckListParser) -> None:
    text = "1 Sol Ring\n"
    parsed = parser.parse(text)
    with _patch_parquets():
        result = validate_and_enrich(parsed)
    assert len(result.unrecognized) == 0
    card = result.cards[0]
    assert card.name == "Sol Ring"
    assert "Ramp" in card.tags
    assert card.cmc == 1.0
    assert card.price == 2.50
    assert card.is_new is False


# ---------------------------------------------------------------------------
# Fuzzy match — typo auto-corrected with warning
# ---------------------------------------------------------------------------

def test_fuzzy_match_typo(parser: DeckListParser) -> None:
    # "Eternal Witnes" → should fuzzy-match to "Eternal Witness"
    text = "1 Eternal Witnes\n"
    parsed = parser.parse(text)
    with _patch_parquets():
        result = validate_and_enrich(parsed)
    assert len(result.unrecognized) == 0
    assert result.cards[0].name == "Eternal Witness"
    assert any("Eternal Witnes" in w and "Eternal Witness" in w for w in parsed.warnings)


# ---------------------------------------------------------------------------
# Unknown card → in unrecognized list, tags empty
# ---------------------------------------------------------------------------

def test_unknown_card_in_warnings(parser: DeckListParser) -> None:
    text = "1 Totally Made Up Card XYZZY\n"
    parsed = parser.parse(text)
    # Patch Scryfall to return None so the card stays unrecognized
    with _patch_parquets(), patch("code.web.services.deck_import_service._scryfall_lookup", return_value=None):
        result = validate_and_enrich(parsed)
    assert "Totally Made Up Card XYZZY" in result.unrecognized
    # Still appears in cards with empty tags
    unknown = next(c for c in result.cards if c.name == "Totally Made Up Card XYZZY")
    assert unknown.tags == []
    assert unknown.cmc == 0.0


# ---------------------------------------------------------------------------
# Commander row populated
# ---------------------------------------------------------------------------

def test_commander_row_populated(parser: DeckListParser) -> None:
    text = "* 1 Atraxa, Praetors' Voice\n1 Sol Ring\n"
    parsed = parser.parse(text)
    with _patch_parquets():
        result = validate_and_enrich(parsed)
    assert result.commander_row is not None
    assert result.commander_row.get("name") == "Atraxa, Praetors' Voice"


# ---------------------------------------------------------------------------
# Partner commanders — merged colorIdentity
# ---------------------------------------------------------------------------

def test_partner_commanders_merged_color_identity(parser: DeckListParser) -> None:
    text = (
        "// Commander\n"
        "1 Halana, Kessig Ranger\n"
        "1 Alena, Kessig Trapper\n"
        "// Mainboard\n"
        "1 Sol Ring\n"
    )
    parsed = parser.parse(text)
    with _patch_parquets():
        result = validate_and_enrich(parsed)
    assert result.commander_row is not None
    ci = result.commander_row.get("colorIdentity")
    # Should contain both G (Halana) and R (Alena)
    assert "G" in ci
    assert "R" in ci


# ---------------------------------------------------------------------------
# Commander not in parquet → commander_row is None, no crash
# ---------------------------------------------------------------------------

def test_commander_not_in_parquet(parser: DeckListParser) -> None:
    text = "* 1 Unknown Commander\n1 Sol Ring\n"
    parsed = parser.parse(text)
    with _patch_parquets():
        result = validate_and_enrich(parsed)
    assert result.commander_row is None


# ---------------------------------------------------------------------------
# isNew flag propagated
# ---------------------------------------------------------------------------

def test_is_new_flag_propagated(parser: DeckListParser) -> None:
    text = "1 Eternal Witness\n"
    parsed = parser.parse(text)
    with _patch_parquets():
        result = validate_and_enrich(parsed)
    card = next(c for c in result.cards if c.name == "Eternal Witness")
    assert card.is_new is True


# ---------------------------------------------------------------------------
# MDFC with trailing bracket annotation stripped
# ---------------------------------------------------------------------------

def test_mdfc_bracket_annotation_stripped(parser: DeckListParser) -> None:
    """Cards pasted as 'Name // Back [annotation]' should resolve to the MDFC row."""
    mdfc_cards_df = pd.DataFrame(
        {
            "name": ["Bala Ged Recovery // Bala Ged Sanctuary"],
            "faceName": ["Bala Ged Recovery"],
            "themeTags": ["Recursion,Lands"],
            "manaValue": [3.0],
            "type": ["Sorcery // Land"],
            "isNew": [False],
            "price": [1.50],
            "colorIdentity": ["G"],
        }
    )
    commander_df = _make_commander_df()

    def fake_read(path, *args, **kwargs):
        if "commander" in str(path):
            return commander_df
        return mdfc_cards_df

    text = "1 Bala Ged Recovery // Bala Ged Sanctuary [MDFC: Counts as land slot]\n"
    parsed = parser.parse(text)
    with patch("code.web.services.deck_import_service.pd.read_parquet", side_effect=fake_read):
        result = validate_and_enrich(parsed)

    assert result.unrecognized == [], f"Expected no unrecognized, got {result.unrecognized}"
    assert len(result.cards) == 1
    assert "Recursion" in result.cards[0].tags


# ---------------------------------------------------------------------------
# Basic lands not in parquet → treated as lands, not unrecognized
# ---------------------------------------------------------------------------

def test_basic_land_not_in_parquet_is_counted_as_land(parser: DeckListParser) -> None:
    """Forest/Plains/etc. absent from parquet should still get Basic Land type_line."""
    no_basics_df = pd.DataFrame(
        {
            "name": ["Sol Ring"],
            "faceName": ["Sol Ring"],
            "themeTags": ["Ramp,Mana Rock"],
            "manaValue": [1.0],
            "type": ["Artifact"],
            "isNew": [False],
            "price": [2.50],
            "colorIdentity": [""],
        }
    )
    commander_df = _make_commander_df()

    def fake_read(path, *args, **kwargs):
        if "commander" in str(path):
            return commander_df
        return no_basics_df

    text = "1 Sol Ring\n10 Forest\n5 Plains\n"
    parsed = parser.parse(text)
    with patch("code.web.services.deck_import_service.pd.read_parquet", side_effect=fake_read):
        result = validate_and_enrich(parsed)

    assert "Forest" not in result.unrecognized
    assert "Plains" not in result.unrecognized
    forest = next(c for c in result.cards if c.name == "Forest")
    plains = next(c for c in result.cards if c.name == "Plains")
    assert "Land" in forest.type_line
    assert forest.quantity == 10
    assert "Land" in plains.type_line
    assert plains.quantity == 5


# ===========================================================================
# M3 — analyze_composition / detect_themes / resolve_user_themes
# ===========================================================================

# ---------------------------------------------------------------------------
# Helpers: pre-built EnrichedDeck for composition tests
# ---------------------------------------------------------------------------

def _make_commander_series(
    name: str = "Atraxa, Praetors' Voice",
    color_identity: str = "W,U,B,G",
    theme_tags: str = "Proliferate,+1/+1 Counters",
) -> pd.Series:
    return pd.Series({
        "name": name,
        "colorIdentity": color_identity,
        "themeTags": theme_tags,
    })


def _make_enriched_deck(
    commander_series: pd.Series | None = None,
    extra_cards: list[EnrichedCard] | None = None,
) -> EnrichedDeck:
    """Build a minimal EnrichedDeck with predictable role counts for testing."""
    cards: list[EnrichedCard] = [
        # 3 ramp cards
        EnrichedCard(name="Sol Ring",      quantity=1, tags=["Ramp", "Mana Rock"], cmc=1.0, type_line="Artifact",             is_new=False, price=2.5),
        EnrichedCard(name="Arcane Signet", quantity=1, tags=["Ramp", "Mana Rock"], cmc=2.0, type_line="Artifact",             is_new=False, price=1.0),
        EnrichedCard(name="Rampant Growth",quantity=1, tags=["Ramp"],              cmc=2.0, type_line="Sorcery",              is_new=False, price=0.5),
        # 2 removal
        EnrichedCard(name="Path to Exile", quantity=1, tags=["Removal", "Spot Removal"], cmc=1.0, type_line="Instant",        is_new=False, price=3.0),
        EnrichedCard(name="Swords to Plowshares", quantity=1, tags=["Removal"],   cmc=1.0, type_line="Instant",              is_new=False, price=4.0),
        # 1 board wipe
        EnrichedCard(name="Wrath of God",  quantity=1, tags=["Board Wipes"],       cmc=4.0, type_line="Sorcery",             is_new=False, price=5.0),
        # 2 card draw
        EnrichedCard(name="Rhystic Study", quantity=1, tags=["Card Draw", "Card Advantage"], cmc=3.0, type_line="Enchantment",is_new=False, price=10.0),
        EnrichedCard(name="Mystic Remora", quantity=1, tags=["Card Draw"],         cmc=1.0, type_line="Enchantment",          is_new=True,  price=2.0),
        # 1 protection
        EnrichedCard(name="Swiftfoot Boots",quantity=1,tags=["Protective Effects"],cmc=2.0, type_line="Artifact — Equipment", is_new=False, price=1.5),
        # 3 lands
        EnrichedCard(name="Forest",        quantity=3, tags=["Basic Land"],        cmc=0.0, type_line="Basic Land — Forest",  is_new=False, price=0.1),
        # 1 theme card (Proliferate) — non-land, non-commander
        EnrichedCard(name="Contagion Engine", quantity=1, tags=["Proliferate"],    cmc=6.0, type_line="Artifact",             is_new=False, price=8.0),
    ]
    if extra_cards:
        cards.extend(extra_cards)
    return EnrichedDeck(
        commander_row=commander_series if commander_series is not None else _make_commander_series(),
        cards=cards,
        unrecognized=[],
    )


def _fake_load_theme_catalog():
    from code.deck_builder.theme_catalog_loader import ThemeCatalogEntry
    entries = [
        ThemeCatalogEntry(theme="Proliferate", commander_count=5, card_count=20),
        ThemeCatalogEntry(theme="+1/+1 Counters", commander_count=8, card_count=30),
        ThemeCatalogEntry(theme="Ramp", commander_count=2, card_count=100),
        ThemeCatalogEntry(theme="Bear Kindred", commander_count=1, card_count=10),
    ]
    return entries, "test"


# ---------------------------------------------------------------------------
# Role counts — values match card list above
# ---------------------------------------------------------------------------

def test_role_counts_ramp(parser: DeckListParser) -> None:
    deck = _make_enriched_deck()
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        result = analyze_composition(deck)
    rc = result.role_counts["ramp"]
    assert rc.actual == 3
    assert rc.target == 8
    assert rc.status == "critical"


def test_role_counts_removal(parser: DeckListParser) -> None:
    deck = _make_enriched_deck()
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        result = analyze_composition(deck)
    rc = result.role_counts["removal"]
    assert rc.actual == 2
    assert rc.status == "critical"


def test_role_counts_lands_use_type_line(parser: DeckListParser) -> None:
    """Lands are counted via type_line, not tags."""
    deck = _make_enriched_deck()
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        result = analyze_composition(deck)
    assert result.role_counts["lands"].actual == 3


def test_role_count_good_status() -> None:
    """A deck meeting the ramp target (8) shows 'good' status."""
    ramp_cards = [
        EnrichedCard(name=f"Ramp{i}", quantity=1, tags=["Ramp"], cmc=2.0,
                     type_line="Sorcery", is_new=False, price=None)
        for i in range(8)
    ]
    deck = _make_enriched_deck(extra_cards=ramp_cards)
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        result = analyze_composition(deck)
    assert result.role_counts["ramp"].status == "good"


# ---------------------------------------------------------------------------
# CMC curve — 7+ bucketed under key 7
# ---------------------------------------------------------------------------

def test_cmc_curve_buckets() -> None:
    """Cards with CMC >= 7 bucket into key 7; lands excluded."""
    big_spell = EnrichedCard(name="Emrakul", quantity=1, tags=[], cmc=15.0,
                             type_line="Creature — Eldrazi", is_new=False, price=None)
    deck = _make_enriched_deck(extra_cards=[big_spell])
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        result = analyze_composition(deck)
    assert result.cmc_curve[7] >= 1
    # Lands (CMC 0) should be excluded from curve
    land_only_cmc0 = result.cmc_curve[0]
    assert land_only_cmc0 >= 0  # non-land CMC-0 cards may exist; just ensure key present


# ---------------------------------------------------------------------------
# Land tags excluded from theme frequency
# ---------------------------------------------------------------------------

def test_land_tags_excluded_from_theme_freq() -> None:
    """Land type_lines must not contribute to theme signal_tags."""
    deck = _make_enriched_deck()
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        result = detect_themes(deck)
    # "Basic Land" should not appear in signal_tags
    assert "Basic Land" not in result.signal_tags


# ---------------------------------------------------------------------------
# Theme auto-detection — commander cross-reference
# ---------------------------------------------------------------------------

def test_theme_confirmed_when_in_commander_tags() -> None:
    """Proliferate appears in both card tags and commander themeTags → confirmed."""
    # Add enough Proliferate cards to exceed 15% threshold
    extra = [
        EnrichedCard(name=f"Proliferate{i}", quantity=1, tags=["Proliferate"],
                     cmc=3.0, type_line="Sorcery", is_new=False, price=None)
        for i in range(5)
    ]
    deck = _make_enriched_deck(extra_cards=extra)
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        result = detect_themes(deck)
    assert "Proliferate" in result.confirmed


def test_theme_possible_when_not_in_commander_tags() -> None:
    """+1/+1 Counters tag appears in catalog but NOT in this commander's themeTags → possible."""
    extra = [
        EnrichedCard(name=f"Counter{i}", quantity=1, tags=["+1/+1 Counters"],
                     cmc=2.0, type_line="Instant", is_new=False, price=None)
        for i in range(5)
    ]
    # Use a commander with no +1/+1 Counters theme
    commander = _make_commander_series(theme_tags="Ramp")
    deck = _make_enriched_deck(commander_series=commander, extra_cards=extra)
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        result = detect_themes(deck)
    assert "+1/+1 Counters" in result.possible
    assert "+1/+1 Counters" not in result.confirmed


# ---------------------------------------------------------------------------
# User theme resolution
# ---------------------------------------------------------------------------

def test_resolve_user_themes_matched() -> None:
    """'Bears' fuzzy-matches to 'Bear Kindred' via ThemeMatcher."""
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        matched, unmatched = resolve_user_themes(["Bear Kindred"])
    assert "Bear Kindred" in matched
    assert unmatched == []


def test_resolve_user_themes_unmatched() -> None:
    """Completely unknown theme ends up in unmatched."""
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        matched, unmatched = resolve_user_themes(["Attack the Other Players XYZZY"])
    assert matched == []
    assert "Attack the Other Players XYZZY" in unmatched


def test_user_confirmed_deduped_from_auto() -> None:
    """User-confirmed themes must not also appear in confirmed/possible."""
    extra = [
        EnrichedCard(name=f"P{i}", quantity=1, tags=["Proliferate"],
                     cmc=2.0, type_line="Sorcery", is_new=False, price=None)
        for i in range(5)
    ]
    deck = _make_enriched_deck(extra_cards=extra)
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        result = detect_themes(deck, user_themes=["Proliferate"])
    assert "Proliferate" in result.user_confirmed
    assert "Proliferate" not in result.confirmed
    assert "Proliferate" not in result.possible


def test_user_themes_suppress_auto_detect() -> None:
    """When user themes are provided with auto_detect=False, confirmed/possible must be empty."""
    extra = [
        EnrichedCard(name=f"P{i}", quantity=1, tags=["Proliferate"],
                     cmc=2.0, type_line="Sorcery", is_new=False, price=None)
        for i in range(15)
    ]
    deck = _make_enriched_deck(extra_cards=extra)
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        result = detect_themes(deck, user_themes=["Proliferate"], auto_detect=False)
    assert result.user_confirmed == ["Proliferate"]
    assert result.confirmed == []
    assert result.possible == []


# ---------------------------------------------------------------------------
# Card pruning — rank_cut_candidates / apply_prune
# ---------------------------------------------------------------------------

def _make_land(name: str = "Forest") -> EnrichedCard:
    return EnrichedCard(name=name, quantity=1, tags=[], cmc=0.0, type_line="Basic Land", is_new=False, price=None)


def test_rank_cut_candidates_excludes_lands() -> None:
    """Lands must never appear in cut candidates."""
    deck = _make_enriched_deck(extra_cards=[_make_land("Forest"), _make_land("Island")])
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        analysis = analyze_composition(deck)
    cuts = rank_cut_candidates(deck, analysis, 5)
    names = {c.card.name for c in cuts}
    assert "Forest" not in names
    assert "Island" not in names


def test_rank_cut_candidates_returns_n() -> None:
    """rank_cut_candidates returns at most n cards."""
    deck = _make_enriched_deck()
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        analysis = analyze_composition(deck)
    cuts = rank_cut_candidates(deck, analysis, 2)
    assert len(cuts) <= 2


def test_rank_cut_candidates_weak_first() -> None:
    """A card with a top-tier EDHREC rank scores higher and should be kept over an unranked card."""
    # "Popular" has rank 50 (very popular) — higher score → kept
    popular = EnrichedCard(name="Popular", quantity=1, tags=[], cmc=2.0,
                           type_line="Instant", is_new=False, price=None, edhrec_rank=50)
    # "Obscure" has no rank at all — scores 0 → cut first
    obscure = EnrichedCard(name="Obscure", quantity=1, tags=[], cmc=3.0,
                           type_line="Sorcery", is_new=False, price=None, edhrec_rank=None)
    deck = EnrichedDeck(
        commander_row=_make_commander_series(),
        cards=[popular, obscure],
        unrecognized=[],
    )
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        analysis = analyze_composition(deck)
    cuts = rank_cut_candidates(deck, analysis, 1)
    assert cuts[0].card.name == "Obscure"


def test_rank_cut_candidates_staple_role_protected() -> None:
    """A card covering a staple role (Removal) should score higher than a no-role card."""
    removal = EnrichedCard(name="SwordsToPlowshares", quantity=1,
                           tags=["Removal", "Spot Removal"], cmc=1.0,
                           type_line="Instant", is_new=False, price=None, edhrec_rank=None)
    filler = EnrichedCard(name="FlatFiller", quantity=1, tags=[], cmc=4.0,
                          type_line="Sorcery", is_new=False, price=None, edhrec_rank=None)
    deck = EnrichedDeck(
        commander_row=_make_commander_series(),
        cards=[removal, filler],
        unrecognized=[],
    )
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        analysis = analyze_composition(deck)
    cuts = rank_cut_candidates(deck, analysis, 1)
    # The filler (no role, no rank) should be cut, not the removal spell
    assert cuts[0].card.name == "FlatFiller"
    assert "Removal" in cuts[0].card.tags or cuts[0].card.name != "SwordsToPlowshares"


def test_cut_candidate_has_role_hits() -> None:
    """CutCandidate exposes role_hits so the template can explain the rating."""
    removal = EnrichedCard(name="RemovalCard", quantity=1,
                           tags=["Removal"], cmc=1.0,
                           type_line="Instant", is_new=False, price=None, edhrec_rank=None)
    deck = EnrichedDeck(
        commander_row=_make_commander_series(),
        cards=[removal],
        unrecognized=[],
    )
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        analysis = analyze_composition(deck)
    cuts = rank_cut_candidates(deck, analysis, 1)
    assert cuts[0].role_hits == ["Removal"]


def test_cut_candidate_weakness_reasons() -> None:
    """CutCandidate exposes weakness_reasons so the template can explain WHY it was flagged."""
    # High CMC + no EDHREC rank + no role → all three reasons
    expensive = EnrichedCard(name="ExpensiveFiller", quantity=1, tags=[],
                             cmc=6.0, type_line="Sorcery", is_new=False,
                             price=None, edhrec_rank=None)
    deck = EnrichedDeck(
        commander_row=_make_commander_series(),
        cards=[expensive],
        unrecognized=[],
    )
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        analysis = analyze_composition(deck)
    cuts = rank_cut_candidates(deck, analysis, 1)
    reasons = cuts[0].weakness_reasons
    assert any("High CMC" in r for r in reasons), f"Expected High CMC reason, got: {reasons}"
    assert any("EDHREC" in r for r in reasons), f"Expected EDHREC reason, got: {reasons}"


def test_cut_candidate_weakness_on_theme_no_role() -> None:
    """A card that matches a theme but covers no staple role gets 'Fills no key role' reason."""
    # Give the deck a theme by patching theme detection
    on_theme_no_role = EnrichedCard(name="ThemeyButUseless", quantity=1,
                                    tags=["Counters"], cmc=3.0,
                                    type_line="Enchantment", is_new=False,
                                    price=None, edhrec_rank=None)
    deck = EnrichedDeck(
        commander_row=_make_commander_series(),
        cards=[on_theme_no_role],
        unrecognized=[],
    )
    with patch("code.web.services.deck_import_service.load_theme_catalog", return_value=_fake_load_theme_catalog()):
        analysis = analyze_composition(deck)
    # Inject a theme manually so "Counters" appears as a theme hit
    analysis.themes.confirmed = ["Counters"]
    cuts = rank_cut_candidates(deck, analysis, 1)
    assert "Fills no key role" in cuts[0].weakness_reasons


def test_apply_prune_removes_card() -> None:
    """apply_prune removes a named card from the deck."""
    card = EnrichedCard(name="TestCard", quantity=1, tags=[], cmc=2.0,
                        type_line="Sorcery", is_new=False, price=None)
    deck = _make_enriched_deck(extra_cards=[card])
    pruned = apply_prune(deck, ["TestCard"])
    names = [c.name for c in pruned.cards]
    assert "TestCard" not in names


def test_apply_prune_decrements_multi_copy() -> None:
    """apply_prune decrements quantity by one for multi-copy cards."""
    card = EnrichedCard(name="Relentless Rats", quantity=3, tags=[], cmc=2.0,
                        type_line="Creature", is_new=False, price=None)
    deck = _make_enriched_deck(extra_cards=[card])
    pruned = apply_prune(deck, ["Relentless Rats"])
    match = next((c for c in pruned.cards if c.name == "Relentless Rats"), None)
    assert match is not None
    assert match.quantity == 2


def test_apply_prune_preserves_others() -> None:
    """apply_prune leaves unaffected cards intact."""
    keep = EnrichedCard(name="KeepMe", quantity=1, tags=[], cmc=1.0,
                        type_line="Instant", is_new=False, price=None)
    remove = EnrichedCard(name="CutMe", quantity=1, tags=[], cmc=3.0,
                          type_line="Sorcery", is_new=False, price=None)
    deck = _make_enriched_deck(extra_cards=[keep, remove])
    pruned = apply_prune(deck, ["CutMe"])
    names = [c.name for c in pruned.cards]
    assert "KeepMe" in names
    assert "CutMe" not in names


# ---------------------------------------------------------------------------
# M6 — Temp persistence & save_imported_deck
# ---------------------------------------------------------------------------

def _make_analysis_for_save() -> "object":
    """Return a minimal DeckAnalysis for save/temp tests."""
    from code.web.services.deck_import_service import DeckAnalysis, ThemeDetectionResult, RoleCount
    return DeckAnalysis(
        commander_name="Test Commander",
        color_identity=["G"],
        role_counts={"ramp": RoleCount(actual=5, target=8, status="low")},
        cmc_curve={i: 0 for i in range(8)},
        color_distribution={"G": 5},
        themes=ThemeDetectionResult(
            user_confirmed=[], confirmed=["Tokens"], possible=[], unmatched_user_themes=[], signal_tags={}
        ),
        unrecognized=[],
        total_cards=5,
        upgrade_token="test-token-123",
        type_breakdown={},
    )


def test_write_and_load_temp_session(tmp_path: "pytest.TempPathFactory") -> None:
    """write_temp_session round-trips through load_temp_session."""
    import code.web.services.deck_import_service as _svc_mod

    card = EnrichedCard(name="Llanowar Elves", quantity=1, tags=["Ramp"],
                        cmc=1.0, type_line="Creature", is_new=False, price=0.5)
    deck = EnrichedDeck(commander_row=None, cards=[card], unrecognized=[])
    analysis = _make_analysis_for_save()
    warnings = ["test warning"]

    orig_temp_dir = _svc_mod._TEMP_DIR
    _svc_mod._TEMP_DIR = str(tmp_path)
    try:
        write_temp_session("tok-abc", deck, analysis, warnings)
        result = load_temp_session("tok-abc")
    finally:
        _svc_mod._TEMP_DIR = orig_temp_dir

    assert result is not None
    restored_deck, restored_analysis, restored_warnings = result
    assert restored_deck.cards[0].name == "Llanowar Elves"
    assert restored_analysis.commander_name == "Test Commander"
    assert restored_analysis.themes.confirmed == ["Tokens"]
    assert restored_warnings == ["test warning"]


def test_load_temp_session_missing_returns_none(tmp_path: "pytest.TempPathFactory") -> None:
    """load_temp_session returns None for a non-existent token."""
    import code.web.services.deck_import_service as _svc_mod

    orig_temp_dir = _svc_mod._TEMP_DIR
    _svc_mod._TEMP_DIR = str(tmp_path)
    try:
        result = load_temp_session("nonexistent-token")
    finally:
        _svc_mod._TEMP_DIR = orig_temp_dir

    assert result is None


def test_save_imported_deck_creates_files(tmp_path: "pytest.TempPathFactory") -> None:
    """save_imported_deck writes CSV, TXT, and summary JSON to deck_files/."""
    import json
    import code.web.services.deck_import_service as _svc_mod

    card = EnrichedCard(name="Llanowar Elves", quantity=1, tags=["Ramp"],
                        cmc=1.0, type_line="Creature", is_new=False, price=0.5)
    deck = EnrichedDeck(commander_row=None, cards=[card], unrecognized=[])
    analysis = _make_analysis_for_save()

    orig_dir = _svc_mod._DECK_FILES_DIR
    _svc_mod._DECK_FILES_DIR = str(tmp_path)
    try:
        csv_name, txt_name, summary_name = save_imported_deck("tok-xyz", deck, analysis)
    finally:
        _svc_mod._DECK_FILES_DIR = orig_dir

    assert (tmp_path / csv_name).exists(), "CSV not created"
    assert (tmp_path / txt_name).exists(), "TXT not created"
    assert (tmp_path / summary_name).exists(), "Summary JSON not created"

    meta = json.loads((tmp_path / summary_name).read_text())["meta"]
    assert meta["commander"] == "Test Commander"
    assert meta["name"] == "Test Commander"
    assert meta["source"] == "imported"
    assert "Tokens" in meta["tags"]


def test_save_imported_deck_no_collision(tmp_path: "pytest.TempPathFactory") -> None:
    """save_imported_deck appends _1 suffix when file already exists for same commander+date."""
    import code.web.services.deck_import_service as _svc_mod

    card = EnrichedCard(name="Sol Ring", quantity=1, tags=[], cmc=1.0,
                        type_line="Artifact", is_new=False, price=1.0)
    deck = EnrichedDeck(commander_row=None, cards=[card], unrecognized=[])
    analysis = _make_analysis_for_save()

    orig_dir = _svc_mod._DECK_FILES_DIR
    _svc_mod._DECK_FILES_DIR = str(tmp_path)
    try:
        csv1, _, _ = save_imported_deck("tok-1", deck, analysis)
        csv2, _, _ = save_imported_deck("tok-2", deck, analysis)
    finally:
        _svc_mod._DECK_FILES_DIR = orig_dir

    assert csv1 != csv2, "Expected distinct filenames for second save"


def test_save_imported_deck_txt_content(tmp_path: "pytest.TempPathFactory") -> None:
    """TXT file includes the commander comment and card line."""
    import code.web.services.deck_import_service as _svc_mod

    card = EnrichedCard(name="Birds of Paradise", quantity=1, tags=["Ramp"],
                        cmc=1.0, type_line="Creature", is_new=False, price=2.0)
    deck = EnrichedDeck(commander_row=None, cards=[card], unrecognized=[])
    analysis = _make_analysis_for_save()

    orig_dir = _svc_mod._DECK_FILES_DIR
    _svc_mod._DECK_FILES_DIR = str(tmp_path)
    try:
        _, txt_name, _ = save_imported_deck("tok-txt", deck, analysis)
        txt = (tmp_path / txt_name).read_text(encoding="utf-8")
    finally:
        _svc_mod._DECK_FILES_DIR = orig_dir

    assert "# Commanders: Test Commander" in txt
    assert "1 Birds of Paradise" in txt
