from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


def _load_applier():
    root = Path(__file__).resolve().parents[2]
    mod_path = root / 'code' / 'tagging' / 'bracket_policy_applier.py'
    spec = importlib.util.spec_from_file_location('bracket_policy_applier', str(mod_path))
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[assignment]
    return mod


def test_apply_bracket_policy_tags(tmp_path: Path, monkeypatch):
    # Create minimal DataFrame
    df = pd.DataFrame([
        { 'name': "Time Warp", 'faceName': '', 'text': '', 'type': 'Sorcery', 'keywords': '', 'creatureTypes': [], 'themeTags': [] },
        { 'name': "Armageddon", 'faceName': '', 'text': '', 'type': 'Sorcery', 'keywords': '', 'creatureTypes': [], 'themeTags': [] },
        { 'name': "Demonic Tutor", 'faceName': '', 'text': '', 'type': 'Sorcery', 'keywords': '', 'creatureTypes': [], 'themeTags': [] },
        { 'name': "Forest", 'faceName': '', 'text': '', 'type': 'Basic Land — Forest', 'keywords': '', 'creatureTypes': [], 'themeTags': [] },
    ])

    # Ensure the JSON lists exist with expected names
    lists_dir = Path('config/card_lists')
    lists_dir.mkdir(parents=True, exist_ok=True)
    (lists_dir / 'extra_turns.json').write_text(json.dumps({ 'source_url': 'test', 'generated_at': 'now', 'cards': ['Time Warp'] }), encoding='utf-8')
    (lists_dir / 'mass_land_denial.json').write_text(json.dumps({ 'source_url': 'test', 'generated_at': 'now', 'cards': ['Armageddon'] }), encoding='utf-8')
    (lists_dir / 'tutors_nonland.json').write_text(json.dumps({ 'source_url': 'test', 'generated_at': 'now', 'cards': ['Demonic Tutor'] }), encoding='utf-8')
    (lists_dir / 'game_changers.json').write_text(json.dumps({ 'source_url': 'test', 'generated_at': 'now', 'cards': [] }), encoding='utf-8')

    mod = _load_applier()
    mod.apply_bracket_policy_tags(df)

    row = df.set_index('name')
    assert any('Bracket:ExtraTurn' == t for t in row.loc['Time Warp', 'themeTags'])
    assert any('Bracket:MassLandDenial' == t for t in row.loc['Armageddon', 'themeTags'])
    assert any('Bracket:TutorNonland' == t for t in row.loc['Demonic Tutor', 'themeTags'])
    assert not row.loc['Forest', 'themeTags']
