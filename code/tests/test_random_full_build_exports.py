import os
import json
from deck_builder.random_entrypoint import build_random_full_deck

def test_random_full_build_writes_sidecars():
    # Run build in real project context so CSV inputs exist
    os.makedirs('deck_files', exist_ok=True)
    res = build_random_full_deck(theme="Goblin Kindred", seed=12345)
    assert res.csv_path is not None, "CSV path should be returned"
    assert os.path.isfile(res.csv_path), f"CSV not found: {res.csv_path}"
    base, _ = os.path.splitext(res.csv_path)
    summary_path = base + '.summary.json'
    assert os.path.isfile(summary_path), "Summary sidecar missing"
    with open(summary_path,'r',encoding='utf-8') as f:
        data = json.load(f)
    assert 'meta' in data and 'summary' in data, "Malformed summary sidecar"
    comp_path = base + '_compliance.json'
    # Compliance may be empty dict depending on bracket policy; ensure file exists when compliance object returned
    if res.compliance:
        assert os.path.isfile(comp_path), "Compliance file missing despite compliance object"
    # Basic CSV sanity: contains header Name
    with open(res.csv_path,'r',encoding='utf-8') as f:
        head = f.read(200)
    assert 'Name' in head, "CSV appears malformed"
    # Cleanup artifacts to avoid polluting workspace (best effort)
    for p in [res.csv_path, summary_path, comp_path]:
        try:
            if os.path.isfile(p):
                os.remove(p)
        except Exception:
            pass
