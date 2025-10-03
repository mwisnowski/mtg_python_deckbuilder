from __future__ import annotations

from types import MethodType

from deck_builder.builder import DeckBuilder


def _builder_with_forest() -> DeckBuilder:
    builder = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
    builder.card_library = {
        "Forest": {"Card Name": "Forest", "Card Type": "Land", "Count": 5},
    }
    return builder


def _stub_modal_matrix(builder: DeckBuilder) -> None:
    def fake_matrix(self: DeckBuilder):
        return {
            "Bala Ged Recovery": {"G": 1, "_dfc_counts_as_extra": True},
            "Forest": {"G": 1},
        }

    builder._compute_color_source_matrix = MethodType(fake_matrix, builder)  # type: ignore[attr-defined]


def test_modal_dfc_swaps_basic_when_enabled():
    builder = _builder_with_forest()
    builder.swap_mdfc_basics = True
    _stub_modal_matrix(builder)

    builder.add_card("Bala Ged Recovery", card_type="Instant")

    assert builder.card_library["Forest"]["Count"] == 4
    assert "Bala Ged Recovery" in builder.card_library


def test_modal_dfc_does_not_swap_when_disabled():
    builder = _builder_with_forest()
    builder.swap_mdfc_basics = False
    _stub_modal_matrix(builder)

    builder.add_card("Bala Ged Recovery", card_type="Instant")

    assert builder.card_library["Forest"]["Count"] == 5
    assert "Bala Ged Recovery" in builder.card_library
