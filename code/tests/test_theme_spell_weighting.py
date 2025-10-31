from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from deck_builder.theme_context import ThemeContext, ThemeTarget
from deck_builder.phases.phase4_spells import SpellAdditionMixin
from deck_builder import builder_utils as bu


class DummyRNG:
    def uniform(self, _a: float, _b: float) -> float:
        return 1.0

    def random(self) -> float:
        return 0.0

    def choice(self, seq):
        return seq[0]


class DummySpellBuilder(SpellAdditionMixin):
    def __init__(self, df: pd.DataFrame, context: ThemeContext):
        self._combined_cards_df = df
        # Pre-populate 99 cards so we target a single filler slot
        self.card_library: Dict[str, Dict[str, Any]] = {
            f"Existing{i}": {"Count": 1} for i in range(99)
        }
        self.primary_tag = context.ordered_targets[0].display if context.ordered_targets else None
        self.secondary_tag = None
        self.tertiary_tag = None
        self.tag_mode = context.combine_mode
        self.prefer_owned = False
        self.owned_card_names: set[str] = set()
        self.bracket_limits: Dict[str, Any] = {}
        self.output_log: List[str] = []
        self.output_func = self.output_log.append
        self._rng = DummyRNG()
        self._theme_context = context
        self.added_cards: List[str] = []

    def _get_rng(self) -> DummyRNG:
        return self._rng

    @property
    def rng(self) -> DummyRNG:
        return self._rng

    def get_theme_context(self) -> ThemeContext:
        return self._theme_context

    def add_card(self, name: str, **kwargs: Any) -> None:
        self.card_library[name] = {"Count": kwargs.get("count", 1)}
        self.added_cards.append(name)


def make_context(user_theme_weight: float) -> ThemeContext:
    user = ThemeTarget(
        role="user_1",
        display="Angels",
        slug="angels",
        source="user",
        weight=1.0,
    )
    return ThemeContext(
        ordered_targets=[user],
        combine_mode="AND",
        weights={"user_1": 1.0},
        commander_slugs=[],
        user_slugs=["angels"],
        resolution=None,
        user_theme_weight=user_theme_weight,
    )


def build_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "name": "Angel Song",
                "type": "Instant",
                "themeTags": ["Angels"],
                "manaValue": 2,
                "edhrecRank": 1400,
            },
        ]
    )


def test_user_theme_bonus_increases_weight(monkeypatch) -> None:
    captured: List[List[tuple[str, float]]] = []

    def fake_weighted(pool: List[tuple[str, float]], k: int, rng=None) -> List[str]:
        captured.append(list(pool))
        ranked = sorted(pool, key=lambda item: item[1], reverse=True)
        return [name for name, _ in ranked[:k]]

    monkeypatch.setattr(bu, "weighted_sample_without_replacement", fake_weighted)

    def run(user_weight: float) -> Dict[str, float]:
        start = len(captured)
        context = make_context(user_weight)
        builder = DummySpellBuilder(build_dataframe(), context)
        builder.fill_remaining_theme_spells()
        assert start < len(captured)  # ensure we captured weights
        pool = captured[start]
        return dict(pool)

    weights_no_bonus = run(1.0)
    weights_bonus = run(1.5)

    assert "Angel Song" in weights_no_bonus
    assert "Angel Song" in weights_bonus
    assert weights_bonus["Angel Song"] > weights_no_bonus["Angel Song"]
