"""Tests for Roadmap 14 M1: Smart Land Base Analysis.

Covers:
  - compute_pip_density() in builder_utils
  - analyze_curve() in builder_utils
  - LandAnalysisMixin._determine_profile()
  - LandAnalysisMixin._basics_for_profile()
  - LandAnalysisMixin.run_land_analysis() integration (env guards, overrides)
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional
from unittest.mock import patch

import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from code.deck_builder import builder_utils as bu
from code.deck_builder.phases.phase2_lands_analysis import LandAnalysisMixin


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------

def _make_card(mana_cost: str, card_type: str = 'Instant') -> dict:
    return {'Mana Cost': mana_cost, 'Card Type': card_type, 'Count': 1}


class _StubDeck(LandAnalysisMixin):
    """Minimal DeckBuilder stand-in for mixin tests."""

    def __init__(
        self,
        color_identity: list,
        commander_cmc: float = 3.5,
        card_library: Optional[Dict[str, dict]] = None,
        budget_total: Optional[float] = None,
    ):
        self.color_identity = color_identity
        self.commander_dict = {'CMC': commander_cmc}
        self.card_library = card_library or {}
        self.ideal_counts: Dict[str, Any] = {'lands': 35, 'basic_lands': 15}
        self.budget_total = budget_total
        self.output_func = lambda *a, **kw: None


# ---------------------------------------------------------------------------
# compute_pip_density
# ---------------------------------------------------------------------------

class TestComputePipDensity:
    def _lib(self, *cards: dict) -> dict:
        return {f'card_{i}': c for i, c in enumerate(cards)}

    def test_single_pip_counted(self):
        lib = self._lib(_make_card('{W}'), _make_card('{W}'))
        result = bu.compute_pip_density(lib, ['W'])
        assert result['W']['single'] == 2

    def test_double_pip_counted(self):
        lib = self._lib(_make_card('{W}{W}'))
        result = bu.compute_pip_density(lib, ['W'])
        assert result['W']['double'] == 1

    def test_triple_pip_counted(self):
        lib = self._lib(_make_card('{W}{W}{W}'))
        result = bu.compute_pip_density(lib, ['W'])
        assert result['W']['triple'] == 1

    def test_phyrexian_pip_counted(self):
        # Internal format uses {WP} (no slash) for Phyrexian mana
        lib = self._lib(_make_card('{WP}'))
        result = bu.compute_pip_density(lib, ['W'])
        assert result['W']['phyrexian'] == 1

    def test_hybrid_pip_splits(self):
        # Hybrid symbols ({W/U}) credit 0.5 weight each; by design they do NOT
        # reach any whole-pip bucket threshold, but they zero out if the color
        # is not in the identity. Both colors in identity → each stays at 0 pips.
        lib = self._lib(_make_card('{W/U}'))
        result = bu.compute_pip_density(lib, ['W', 'U'])
        # Neither color reaches a whole-pip bucket (0.5 < 1)
        assert result['W']['single'] == 0 and result['U']['single'] == 0
        # But colors outside identity are also 0 — confirm B is 0
        assert result['B']['single'] == 0

    def test_lands_excluded(self):
        lib = self._lib(_make_card('{W}', card_type='Basic Land'))
        result = bu.compute_pip_density(lib, ['W'])
        assert result['W']['single'] == 0

    def test_colors_not_in_identity_zeroed(self):
        lib = self._lib(_make_card('{W}'), _make_card('{U}'))
        result = bu.compute_pip_density(lib, ['W'])  # only W in identity
        assert result['U']['single'] == 0

    def test_all_zeros_for_empty_library(self):
        result = bu.compute_pip_density({}, ['W', 'U'])
        for c in ('W', 'U', 'B', 'R', 'G'):
            for bucket in ('single', 'double', 'triple', 'phyrexian'):
                assert result[c][bucket] == 0


# ---------------------------------------------------------------------------
# analyze_curve
# ---------------------------------------------------------------------------

class TestAnalyzeCurve:
    def test_fast_deck(self):
        result = bu.analyze_curve(2.5, 2)
        assert result['speed_category'] == 'fast'
        assert result['land_target'] == 33

    def test_mid_deck(self):
        result = bu.analyze_curve(3.5, 3)
        assert result['speed_category'] == 'mid'
        assert result['land_target'] == 35

    def test_slow_deck_scales_with_colors(self):
        result_4c = bu.analyze_curve(5.0, 4)
        result_2c = bu.analyze_curve(5.0, 2)
        assert result_4c['speed_category'] == 'slow'
        assert result_2c['speed_category'] == 'slow'
        # More colors → more lands for slow decks (up to LAND_COUNT_SLOW_MAX)
        assert result_4c['land_target'] >= result_2c['land_target']

    def test_slow_deck_caps_at_max(self):
        result = bu.analyze_curve(6.0, 10)  # absurd color count
        from code.deck_builder.builder_constants import LAND_COUNT_SLOW_MAX
        assert result['land_target'] <= LAND_COUNT_SLOW_MAX

    def test_basic_target_present(self):
        result = bu.analyze_curve(3.0, 2)
        assert 'basic_target' in result
        assert isinstance(result['basic_target'], int)


# ---------------------------------------------------------------------------
# LandAnalysisMixin._determine_profile
# ---------------------------------------------------------------------------

class TestDetermineProfile:
    def _mixin(self) -> LandAnalysisMixin:
        return _StubDeck(['W', 'U'])

    def _empty_density(self) -> Dict[str, Dict[str, int]]:
        return {c: {'single': 0, 'double': 0, 'triple': 0, 'phyrexian': 0} for c in 'WUBRG'}

    def test_5_color_always_fixing(self):
        result = self._mixin()._determine_profile(self._empty_density(), 5)
        assert result == 'fixing'

    def test_1_color_always_basics(self):
        result = self._mixin()._determine_profile(self._empty_density(), 1)
        assert result == 'basics'

    def test_3_color_high_double_pips_fixing(self):
        density = self._empty_density()
        density['W']['double'] = 8
        density['U']['double'] = 8  # total 16 >= 15
        result = self._mixin()._determine_profile(density, 3)
        assert result == 'fixing'

    def test_3_color_high_triple_pips_fixing(self):
        density = self._empty_density()
        density['B']['triple'] = 3
        result = self._mixin()._determine_profile(density, 3)
        assert result == 'fixing'

    def test_2_color_low_pips_basics(self):
        density = self._empty_density()
        density['W']['double'] = 2  # < 5
        result = self._mixin()._determine_profile(density, 2)
        assert result == 'basics'

    def test_2_color_moderate_pips_mid(self):
        density = self._empty_density()
        density['W']['double'] = 5
        result = self._mixin()._determine_profile(density, 2)
        assert result == 'mid'

    def test_4_color_low_pips_mid(self):
        # 4 colors but low density → not basics (color count > 2), not obviously fixing
        density = self._empty_density()
        result = self._mixin()._determine_profile(density, 4)
        # 4 colors, 0 doubles/triples — doesn't meet fixing threshold, doesn't meet basics rule
        assert result == 'mid'


# ---------------------------------------------------------------------------
# LandAnalysisMixin._basics_for_profile
# ---------------------------------------------------------------------------

class TestBasicsForProfile:
    def _mixin(self) -> LandAnalysisMixin:
        return _StubDeck(['W', 'U', 'B'])

    def test_basics_profile_60pct(self):
        mixin = self._mixin()
        # 60% of 35 = 21, clamped to 35-5=30; max(21, color_count=3) = 21
        result = mixin._basics_for_profile('basics', 3, 35)
        assert result == 21

    def test_fixing_profile_per_color(self):
        mixin = self._mixin()
        # 3 colors * 2 per color = 6
        result = mixin._basics_for_profile('fixing', 3, 35)
        assert result == 6

    def test_mid_profile_uses_default(self):
        mixin = self._mixin()
        from code.deck_builder.builder_constants import DEFAULT_BASIC_LAND_COUNT
        result = mixin._basics_for_profile('mid', 3, 35)
        assert result == DEFAULT_BASIC_LAND_COUNT

    def test_basics_clamped_by_headroom(self):
        mixin = self._mixin()
        # 60% of 10 = 6, headroom: 10-5=5; so result = 5; max(5, 3) = 5
        result = mixin._basics_for_profile('basics', 3, 10)
        assert result == 5

    def test_basics_minimum_is_color_count(self):
        mixin = self._mixin()
        # 60% of 6 = 3.6 → 4, clamped to 6-5=1; max(1, 3)=3
        result = mixin._basics_for_profile('basics', 3, 6)
        assert result == 3


# ---------------------------------------------------------------------------
# run_land_analysis integration
# ---------------------------------------------------------------------------

class TestRunLandAnalysis:
    def test_no_op_when_flag_not_set(self):
        deck = _StubDeck(['W', 'U', 'B'])
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('ENABLE_SMART_LANDS', None)
            deck.run_land_analysis()
        # ideal_counts must be untouched
        assert deck.ideal_counts['lands'] == 35
        assert deck.ideal_counts['basic_lands'] == 15

    def test_mutates_ideal_counts_when_enabled(self):
        deck = _StubDeck(['W', 'U'], commander_cmc=2.5)
        with patch.dict(os.environ, {'ENABLE_SMART_LANDS': '1'}):
            deck.run_land_analysis()
        assert deck.ideal_counts['lands'] == 33  # fast deck
        assert hasattr(deck, '_land_profile')

    def test_land_profile_env_override(self):
        deck = _StubDeck(['W', 'U', 'B'], commander_cmc=3.5)
        with patch.dict(os.environ, {'ENABLE_SMART_LANDS': '1', 'LAND_PROFILE': 'fixing'}):
            deck.run_land_analysis()
        assert deck._land_profile == 'fixing'

    def test_land_count_env_override(self):
        deck = _StubDeck(['W', 'U'], commander_cmc=3.5)
        with patch.dict(os.environ, {'ENABLE_SMART_LANDS': '1', 'LAND_COUNT': '38'}):
            deck.run_land_analysis()
        assert deck.ideal_counts['lands'] == 38

    def test_budget_forces_basics_profile_3c(self):
        deck = _StubDeck(['W', 'U', 'B'], commander_cmc=4.0, budget_total=30.0)
        with patch.dict(os.environ, {'ENABLE_SMART_LANDS': '1'}):
            deck.run_land_analysis()
        assert deck._land_profile == 'basics'

    def test_budget_does_not_force_basics_for_1c(self):
        # Budget check only applies to 3+ colors
        deck = _StubDeck(['W'], commander_cmc=4.0, budget_total=10.0)
        with patch.dict(os.environ, {'ENABLE_SMART_LANDS': '1'}):
            deck.run_land_analysis()
        # 1-color deck → basics anyway (from rule 2), but this tests the branch not the budget
        assert deck._land_profile == 'basics'

    def test_exception_sets_mid_fallback(self):
        deck = _StubDeck(['W', 'U'])
        # Force a crash inside _run_land_analysis_inner by making ideal_counts non-subscriptable
        deck.ideal_counts = None  # type: ignore[assignment]
        with patch.dict(os.environ, {'ENABLE_SMART_LANDS': '1'}):
            deck.run_land_analysis()  # must not re-raise
        assert deck._land_profile == 'mid'
        assert deck._speed_category == 'mid'

    def test_speed_category_set(self):
        deck = _StubDeck(['W', 'U', 'B'], commander_cmc=5.5)
        with patch.dict(os.environ, {'ENABLE_SMART_LANDS': '1'}):
            deck.run_land_analysis()
        assert deck._speed_category == 'slow'

    def test_land_report_data_populated(self):
        deck = _StubDeck(['W', 'U'], commander_cmc=3.0)
        with patch.dict(os.environ, {'ENABLE_SMART_LANDS': '1'}):
            deck.run_land_analysis()
        report = deck._land_report_data
        assert 'profile' in report
        assert 'speed_category' in report
        assert 'land_target' in report
        assert 'rationale' in report
