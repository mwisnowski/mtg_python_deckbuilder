import os
import tempfile
from pathlib import Path
import importlib
from starlette.testclient import TestClient


def _write_csv(p: Path, rows):
    p.write_text('\n'.join(rows), encoding='utf-8')


def test_compare_diffs_with_temp_exports(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        # Create two CSV exports with small differences
        a = tmp / 'A.csv'
        b = tmp / 'B.csv'
        header = 'Name,Count,Type,ManaValue\n'
        _write_csv(a, [
            header.rstrip('\n'),
            'Card One,1,Creature,2',
            'Card Two,2,Instant,1',
            'Card Three,1,Sorcery,3',
        ])
        _write_csv(b, [
            header.rstrip('\n'),
            'Card Two,1,Instant,1',  # decreased in B
            'Card Four,1,Creature,2',  # only in B
            'Card Three,1,Sorcery,3',
        ])
        # Touch mtime so B is newer
        os.utime(a, None)
        os.utime(b, None)

        # Point DECK_EXPORTS at this temp dir
        monkeypatch.setenv('DECK_EXPORTS', str(tmp))
        app_module = importlib.import_module('code.web.app')
        client = TestClient(app_module.app)

        # Compare A vs B
        r = client.get(f'/decks/compare?A={a.name}&B={b.name}')
        assert r.status_code == 200
        body = r.text
        # Only in A: Card One
        assert 'Only in A' in body
        assert 'Card One' in body
        # Only in B: Card Four
        assert 'Only in B' in body
        assert 'Card Four' in body
        # Changed list includes Card Two with delta -1
        assert 'Card Two' in body
        assert 'Decreased' in body or '( -1' in body or '(-1)' in body
