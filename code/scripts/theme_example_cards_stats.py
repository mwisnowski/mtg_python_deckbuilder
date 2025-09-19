import yaml
import statistics
from pathlib import Path

CATALOG_DIR = Path('config/themes/catalog')

lengths = []
underfilled = []
overfilled = []
missing = []
examples = []

for path in sorted(CATALOG_DIR.glob('*.yml')):
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    except Exception as e:
        print(f'YAML error {path.name}: {e}')
        continue
    cards = data.get('example_cards')
    if not isinstance(cards, list):
        missing.append(path.name)
        continue
    n = len(cards)
    lengths.append(n)
    if n == 0:
        missing.append(path.name)
    elif n < 10:
        underfilled.append((path.name, n))
    elif n > 10:
        overfilled.append((path.name, n))

print('Total themes scanned:', len(lengths))
print('Exact 10:', sum(1 for x in lengths if x == 10))
print('Underfilled (<10):', len(underfilled))
print('Missing (0 or missing list):', len(missing))
print('Overfilled (>10):', len(overfilled))
if lengths:
    print('Min/Max/Mean/Median example_cards length:', min(lengths), max(lengths), f"{statistics.mean(lengths):.2f}", statistics.median(lengths))

if underfilled:
    print('\nFirst 25 underfilled:')
    for name, n in underfilled[:25]:
        print(f'  {name}: {n}')

if overfilled:
    print('\nFirst 10 overfilled:')
    for name, n in overfilled[:10]:
        print(f'  {name}: {n}')

