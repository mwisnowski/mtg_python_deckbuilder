import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess

import pytest

from code.scripts import generate_theme_catalog as new_catalog

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'code' / 'scripts' / 'build_theme_catalog.py'


def run(cmd, env=None):
    env_vars = os.environ.copy()
    if env:
        env_vars.update(env)
    result = subprocess.run(cmd, cwd=ROOT, env=env_vars, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"Command failed: {' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result.stdout, result.stderr


def test_deterministic_seed(tmp_path):
    out1 = tmp_path / 'theme_list1.json'
    out2 = tmp_path / 'theme_list2.json'
    cmd_base = ['python', str(SCRIPT), '--output']
    # Use a limit to keep runtime fast and deterministic small subset (allowed by guard since different output path)
    cmd1 = cmd_base + [str(out1), '--limit', '50']
    cmd2 = cmd_base + [str(out2), '--limit', '50']
    run(cmd1, env={'EDITORIAL_SEED': '123'})
    run(cmd2, env={'EDITORIAL_SEED': '123'})
    data1 = json.loads(out1.read_text(encoding='utf-8'))
    data2 = json.loads(out2.read_text(encoding='utf-8'))
    # Theme order in JSON output should match for same seed + limit
    names1 = [t['theme'] for t in data1['themes']]
    names2 = [t['theme'] for t in data2['themes']]
    assert names1 == names2


def test_popularity_boundaries_override(tmp_path):
    out_path = tmp_path / 'theme_list.json'
    run(['python', str(SCRIPT), '--output', str(out_path), '--limit', '80'], env={'EDITORIAL_POP_BOUNDARIES': '1,2,3,4'})
    data = json.loads(out_path.read_text(encoding='utf-8'))
    # With extremely low boundaries most themes in small slice will be Very Common
    buckets = {t['popularity_bucket'] for t in data['themes']}
    assert buckets <= {'Very Common', 'Common', 'Uncommon', 'Niche', 'Rare'}


def test_no_yaml_backfill_on_alt_output(tmp_path):
    # Run with alternate output and --backfill-yaml; should not modify source YAMLs
    catalog_dir = ROOT / 'config' / 'themes' / 'catalog'
    sample = next(p for p in catalog_dir.glob('*.yml'))
    before = sample.read_text(encoding='utf-8')
    out_path = tmp_path / 'tl.json'
    run(['python', str(SCRIPT), '--output', str(out_path), '--limit', '10', '--backfill-yaml'])
    after = sample.read_text(encoding='utf-8')
    assert before == after, 'YAML was modified when using alternate output path'


def test_catalog_schema_contains_descriptions(tmp_path):
    out_path = tmp_path / 'theme_list.json'
    run(['python', str(SCRIPT), '--output', str(out_path), '--limit', '40'])
    data = json.loads(out_path.read_text(encoding='utf-8'))
    assert all('description' in t for t in data['themes'])
    assert all(t['description'] for t in data['themes'])


@pytest.fixture()
def fixed_now() -> datetime:
    return datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    fieldnames = sorted({field for row in rows for field in row.keys()})
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _read_catalog_rows(path: Path) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8') as handle:
        header_comment = handle.readline()
        assert header_comment.startswith(new_catalog.HEADER_COMMENT_PREFIX)
        reader = csv.DictReader(handle)
        return list(reader)


def test_generate_theme_catalog_basic(tmp_path: Path, fixed_now: datetime) -> None:
    csv_dir = tmp_path / 'csv_files'
    cards = csv_dir / 'cards.csv'
    commander = csv_dir / 'commander_cards.csv'

    _write_csv(
        cards,
        [
            {
                'name': 'Card A',
                'themeTags': '["Lifegain", "Token Swarm"]',
            },
            {
                'name': 'Card B',
                'themeTags': '[" lifegain ", "Control"]',
            },
            {
                'name': 'Card C',
                'themeTags': '[]',
            },
        ],
    )
    _write_csv(
        commander,
        [
            {
                'name': 'Commander 1',
                'themeTags': '["Lifegain", " Voltron "]',
            }
        ],
    )

    output_path = tmp_path / 'theme_catalog.csv'
    result = new_catalog.build_theme_catalog(
        csv_directory=csv_dir,
        output_path=output_path,
        generated_at=fixed_now,
    )

    assert result.output_path == output_path
    assert result.generated_at == '2025-01-01T12:00:00Z'

    rows = _read_catalog_rows(output_path)
    assert [row['theme'] for row in rows] == ['Control', 'Lifegain', 'Token Swarm', 'Voltron']
    lifegain = next(row for row in rows if row['theme'] == 'Lifegain')
    assert lifegain['card_count'] == '2'
    assert lifegain['commander_count'] == '1'
    assert lifegain['source_count'] == '3'

    assert all(row['last_generated_at'] == result.generated_at for row in rows)
    assert all(row['version'] == result.version for row in rows)

    expected_hash = new_catalog._compute_version_hash([row['theme'] for row in rows])  # type: ignore[attr-defined]
    assert result.version == expected_hash


def test_generate_theme_catalog_deduplicates_variants(tmp_path: Path, fixed_now: datetime) -> None:
    csv_dir = tmp_path / 'csv_files'
    cards = csv_dir / 'cards.csv'
    commander = csv_dir / 'commander_cards.csv'

    _write_csv(
        cards,
        [
            {
                'name': 'Card A',
                'themeTags': '[" Token   Swarm ", "Combo"]',
            },
            {
                'name': 'Card B',
                'themeTags': '["token swarm"]',
            },
        ],
    )
    _write_csv(
        commander,
        [
            {
                'name': 'Commander 1',
                'themeTags': '["TOKEN SWARM"]',
            }
        ],
    )

    output_path = tmp_path / 'theme_catalog.csv'
    result = new_catalog.build_theme_catalog(
        csv_directory=csv_dir,
        output_path=output_path,
        generated_at=fixed_now,
    )

    rows = _read_catalog_rows(output_path)
    assert [row['theme'] for row in rows] == ['Combo', 'Token Swarm']
    token_row = next(row for row in rows if row['theme'] == 'Token Swarm')
    assert token_row['card_count'] == '2'
    assert token_row['commander_count'] == '1'
    assert token_row['source_count'] == '3'
    assert result.output_path.exists()
