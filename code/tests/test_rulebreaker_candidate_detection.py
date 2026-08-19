"""Tests for Roadmap 35 Milestone 9: unrecognized Rulebreaker candidate detection.

Covers detect_unrecognized_rulebreakers() (tagger.py), build_candidate_issue_body()
and lookup_existing_issue() (rulebreaker_report.py), and the /status/setup
endpoint's rulebreaker_candidates field.
"""
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tagging.tagger import detect_unrecognized_rulebreakers
from tagging.rulebreaker_report import build_candidate_issue_body, lookup_existing_issue
from code.web.app import app


def _cards_df():
    return pd.DataFrame([
        {
            # One of the 8 known cards: must NOT be flagged even though it
            # carries the ability word verbatim.
            'name': 'Grizzlegom, Hurloon Hero',
            'text': 'Rulebreaker \u2014 A deck with this commander can have any land cards.',
        },
        {
            # Synthetic "future" card with the ability word and an
            # unrecognized name: MUST be flagged.
            'name': 'Fakko, Test Rulebreaker',
            'text': 'Rulebreaker \u2014 A deck with this commander can have Goblin cards of any color identity.',
        },
        {
            # Ordinary card with unrelated text: must NOT be flagged.
            'name': 'Ordinary Bear',
            'text': 'Whenever Ordinary Bear attacks, draw a card.',
        },
    ])


def test_detect_unrecognized_rulebreakers_flags_only_unknown_ability_word_cards():
    candidates = detect_unrecognized_rulebreakers(_cards_df())
    names = {c['name'] for c in candidates}
    assert names == {'Fakko, Test Rulebreaker'}
    assert candidates[0]['matched_signal'] == 'Rulebreaker'


def test_detect_unrecognized_rulebreakers_fallback_text_signal():
    df = pd.DataFrame([{
        'name': 'Someday Card',
        'text': "This card's color identity is regardless of color identity for deckbuilding purposes.",
    }])
    candidates = detect_unrecognized_rulebreakers(df)
    assert len(candidates) == 1
    assert candidates[0]['name'] == 'Someday Card'
    assert candidates[0]['matched_signal'] == 'regardless of color identity'


def test_detect_unrecognized_rulebreakers_empty_df():
    assert detect_unrecognized_rulebreakers(pd.DataFrame()) == []


def test_build_candidate_issue_body_contains_name_text_and_registry_skeleton():
    candidate = {
        'name': 'Fakko, Test Rulebreaker',
        'text_snippet': 'Rulebreaker \u2014 test text',
        'matched_signal': 'Rulebreaker',
    }
    body = build_candidate_issue_body(candidate)
    assert '### Card Name' in body
    assert 'Fakko, Test Rulebreaker' in body
    assert '### Oracle Text' in body
    assert 'Rulebreaker \u2014 test text' in body
    assert '### Proposed Registry Entry' in body
    assert "'name': 'Fakko, Test Rulebreaker'" in body


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_lookup_existing_issue_returns_url_on_match(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return _FakeResponse(200, {'items': [{'html_url': 'https://github.com/x/y/issues/42'}]})

    monkeypatch.setattr('tagging.rulebreaker_report.requests.get', fake_get)
    # bypass in-process cache from any prior test
    import tagging.rulebreaker_report as rb_report
    rb_report._lookup_cache.clear()
    assert lookup_existing_issue('Some New Card') == 'https://github.com/x/y/issues/42'


def test_lookup_existing_issue_returns_none_on_empty_result(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return _FakeResponse(200, {'items': []})

    monkeypatch.setattr('tagging.rulebreaker_report.requests.get', fake_get)
    import tagging.rulebreaker_report as rb_report
    rb_report._lookup_cache.clear()
    assert lookup_existing_issue('No Match Card') is None


def test_lookup_existing_issue_returns_none_on_network_error(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise ConnectionError('boom')

    monkeypatch.setattr('tagging.rulebreaker_report.requests.get', fake_get)
    import tagging.rulebreaker_report as rb_report
    rb_report._lookup_cache.clear()
    assert lookup_existing_issue('Network Error Card') is None


def test_lookup_existing_issue_returns_none_on_rate_limit(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return _FakeResponse(403)

    monkeypatch.setattr('tagging.rulebreaker_report.requests.get', fake_get)
    import tagging.rulebreaker_report as rb_report
    rb_report._lookup_cache.clear()
    assert lookup_existing_issue('Rate Limited Card') is None


@pytest.fixture
def _status_setup_files(tmp_path, monkeypatch):
    """Point /status/setup's file reads at a scratch directory so this test
    never touches real csv_files/.setup_status.json or logs/rulebreaker_candidates.json."""
    import os
    monkeypatch.chdir(tmp_path)
    os.makedirs('csv_files', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    with open('csv_files/.setup_status.json', 'w', encoding='utf-8') as f:
        json.dump({'running': False, 'phase': 'done'}, f)
    yield tmp_path


def test_status_setup_includes_rulebreaker_candidates_when_present(monkeypatch, _status_setup_files):
    with open('logs/rulebreaker_candidates.json', 'w', encoding='utf-8') as f:
        json.dump([{'name': 'Fakko, Test Rulebreaker', 'text_snippet': 'Rulebreaker text', 'matched_signal': 'Rulebreaker'}], f)

    monkeypatch.setattr('tagging.rulebreaker_report.lookup_existing_issue', lambda name: None)

    client = TestClient(app)
    resp = client.get('/status/setup')
    assert resp.status_code == 200
    data = resp.json()
    assert 'rulebreaker_candidates' in data
    assert data['rulebreaker_candidates'][0]['name'] == 'Fakko, Test Rulebreaker'
    assert 'issue_body' in data['rulebreaker_candidates'][0]


def test_status_setup_omits_rulebreaker_candidates_when_absent(_status_setup_files):
    client = TestClient(app)
    resp = client.get('/status/setup')
    assert resp.status_code == 200
    data = resp.json()
    assert 'rulebreaker_candidates' not in data

