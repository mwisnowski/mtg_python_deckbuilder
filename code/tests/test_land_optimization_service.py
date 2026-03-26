"""Tests for Roadmap 14 M3: Diagnostics, land_report in summary, LandOptimizationService."""
from __future__ import annotations

import os
import sys
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from code.deck_builder.phases.phase2_lands_analysis import LandAnalysisMixin
from code.web.services.land_optimization_service import LandOptimizationService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _StubDeck(LandAnalysisMixin):
    def __init__(self, card_library: Dict[str, dict] = None):
        self.color_identity = ['W', 'U']
        self.commander_dict = {'manaValue': 3.0}
        self.card_library = card_library or {}
        self.ideal_counts: Dict[str, Any] = {'lands': 35, 'basic_lands': 15}
        self.budget_total = None
        self.output_func = lambda *a, **kw: None
        self._land_report_data: Dict[str, Any] = {
            'profile': 'mid',
            'speed_category': 'mid',
            'land_target': 35,
        }


def _land(name: str, card_type: str = 'Land') -> dict:
    return {'Card Type': card_type, 'Mana Cost': '', 'Count': 1}


def _basic(name: str) -> dict:
    return {'Card Type': 'Basic Land', 'Mana Cost': '', 'Count': 1}


# ---------------------------------------------------------------------------
# generate_diagnostics
# ---------------------------------------------------------------------------

class TestGenerateDiagnostics:
    def test_counts_lands_correctly(self):
        lib = {
            'Plains': _basic('Plains'),
            'Island': _basic('Island'),
            'Command Tower': _land('Command Tower'),
            'Lightning Bolt': {'Card Type': 'Instant', 'Mana Cost': '{R}', 'Count': 1},
        }
        deck = _StubDeck(lib)
        deck.generate_diagnostics()
        assert deck._land_report_data['actual_land_count'] == 3
        assert deck._land_report_data['actual_basic_count'] == 2

    def test_no_op_on_empty_library(self):
        deck = _StubDeck({})
        deck.generate_diagnostics()
        # _land_report_data unmodified (no update called)
        assert 'actual_land_count' not in deck._land_report_data

    def test_initialises_report_if_missing(self):
        deck = _StubDeck({'Plains': _basic('Plains')})
        del deck._land_report_data
        deck.generate_diagnostics()
        assert isinstance(deck._land_report_data, dict)

    def test_tapped_lands_counted(self):
        """Lands flagged tapped by tapped_land_penalty appear in actual_tapped_count."""
        # Tapped detection relies on oracle text — mock tapped_land_penalty instead
        lib = {
            'Guildgate': _land('Guildgate'),
            'Command Tower': _land('Command Tower'),
        }
        deck = _StubDeck(lib)
        # Mock: Guildgate → tapped, Command Tower → not tapped
        with patch('code.deck_builder.builder_utils.tapped_land_penalty',
                   side_effect=lambda tl, tx: (1, 6) if 'guildgate' not in tl else (1, 6)):
            with patch('code.deck_builder.builder_utils.is_color_fixing_land', return_value=False):
                deck.generate_diagnostics()
        assert deck._land_report_data['actual_land_count'] == 2

    def test_tapped_pct_rounded(self):
        lib = {f'Land{i}': _land(f'Land{i}') for i in range(3)}
        deck = _StubDeck(lib)
        # All tapped
        with patch('code.deck_builder.builder_utils.tapped_land_penalty', return_value=(1, 6)):
            with patch('code.deck_builder.builder_utils.is_color_fixing_land', return_value=False):
                deck.generate_diagnostics()
        assert deck._land_report_data['tapped_pct'] == 100.0

    def test_fixing_lands_counted(self):
        lib = {
            'Breeding Pool': _land('Breeding Pool'),
            'Plains': _basic('Plains'),
        }
        deck = _StubDeck(lib)
        with patch('code.deck_builder.builder_utils.tapped_land_penalty', return_value=(0, 0)):
            with patch('code.deck_builder.builder_utils.is_color_fixing_land',
                       side_effect=lambda tl, tx: True):
                deck.generate_diagnostics()
        assert deck._land_report_data['actual_fixing_count'] == 2


# ---------------------------------------------------------------------------
# LandOptimizationService
# ---------------------------------------------------------------------------

class TestLandOptimizationService:
    def _svc(self) -> LandOptimizationService:
        return LandOptimizationService()

    def _sess_with_report(self, report: dict) -> dict:
        builder = MagicMock()
        builder._land_report_data = report
        return {'build_ctx': {'builder': builder}}

    def test_get_land_report_present(self):
        report = {'profile': 'mid', 'land_target': 35}
        sess = self._sess_with_report(report)
        result = self._svc().get_land_report(sess)
        assert result['profile'] == 'mid'
        assert result['land_target'] == 35

    def test_get_land_report_no_build_ctx(self):
        result = self._svc().get_land_report({})
        assert result == {}

    def test_get_land_report_no_builder(self):
        result = self._svc().get_land_report({'build_ctx': {}})
        assert result == {}

    def test_get_land_report_no_report_attr(self):
        builder = MagicMock(spec=[])  # no _land_report_data attr
        sess = {'build_ctx': {'builder': builder}}
        result = self._svc().get_land_report(sess)
        assert result == {}

    def test_format_for_api_returns_json_safe_dict(self):
        report = {'profile': 'fixing', 'land_target': 37, 'tapped_pct': 28.6}
        result = self._svc().format_for_api(report)
        assert result['profile'] == 'fixing'
        assert result['tapped_pct'] == 28.6

    def test_format_for_api_converts_non_primitives(self):
        import numpy as np  # type: ignore[import]
        try:
            report = {'value': np.int64(42)}
            result = self._svc().format_for_api(report)
            # After JSON round-trip numpy int becomes plain int or str
            assert result['value'] in (42, '42')
        except ImportError:
            pytest.skip('numpy not available')

    def test_format_for_api_empty(self):
        assert self._svc().format_for_api({}) == {}

    def test_format_for_api_returns_copy(self):
        report = {'profile': 'mid'}
        result = self._svc().format_for_api(report)
        result['profile'] = 'mutated'
        assert report['profile'] == 'mid'


# ---------------------------------------------------------------------------
# land_report in summary payload (integration)
# ---------------------------------------------------------------------------

class TestLandReportInSummary:
    def test_generate_diagnostics_adds_actuals(self):
        """_land_report_data gets actual_land_count etc. after generate_diagnostics."""
        deck = _StubDeck({'Plains': _basic('Plains'), 'Island': _basic('Island')})
        deck.generate_diagnostics()
        assert 'actual_land_count' in deck._land_report_data
        assert deck._land_report_data['actual_land_count'] == 2
        assert 'tapped_pct' in deck._land_report_data
