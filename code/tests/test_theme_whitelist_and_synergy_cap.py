import json
import subprocess
import sys
from pathlib import Path

# This test validates that the whitelist governance + synergy cap logic
# (implemented in extract_themes.py and theme_whitelist.yml) behaves as expected.
# It focuses on a handful of anchor themes to keep runtime fast and deterministic.

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "code" / "scripts" / "extract_themes.py"
OUTPUT_JSON = ROOT / "config" / "themes" / "theme_list.json"


def run_extractor():
    # Re-run extraction so the test always evaluates fresh output.
    # Using the current python executable ensures we run inside the active venv.
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, f"extract_themes.py failed: {result.stderr or result.stdout}"
    assert OUTPUT_JSON.exists(), "Expected theme_list.json to be generated"


def load_themes():
    data = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
    themes = data.get("themes", [])
    mapping = {t["theme"]: t for t in themes if isinstance(t, dict) and "theme" in t}
    return mapping


def assert_contains(theme_map, theme_name):
    assert theme_name in theme_map, f"Expected theme '{theme_name}' in generated theme list"


def test_synergy_cap_and_enforced_inclusions():
    run_extractor()
    theme_map = load_themes()

    # Target anchors to validate
    anchors = [
        "+1/+1 Counters",
        "-1/-1 Counters",
        "Counters Matter",
        "Reanimate",
        "Outlaw Kindred",
    ]
    for a in anchors:
        assert_contains(theme_map, a)

    # Synergy cap check (<=5)
    for a in anchors:
        syn = theme_map[a]["synergies"]
        assert len(syn) <= 5, f"Synergy cap violated for {a}: {syn} (len={len(syn)})"

    # Enforced synergies for counters cluster
    plus_syn = set(theme_map["+1/+1 Counters"]["synergies"])
    assert {"Proliferate", "Counters Matter"}.issubset(plus_syn), "+1/+1 Counters missing enforced synergies"

    minus_syn = set(theme_map["-1/-1 Counters"]["synergies"])
    assert {"Proliferate", "Counters Matter"}.issubset(minus_syn), "-1/-1 Counters missing enforced synergies"

    counters_matter_syn = set(theme_map["Counters Matter"]["synergies"])
    assert "Proliferate" in counters_matter_syn, "Counters Matter should include Proliferate"

    # Reanimate anchor (enforced synergy to Graveyard Matters retained while capped)
    reanimate_syn = theme_map["Reanimate"]["synergies"]
    assert "Graveyard Matters" in reanimate_syn, "Reanimate should include Graveyard Matters"
    assert "Enter the Battlefield" in reanimate_syn, "Reanimate should include Enter the Battlefield (curated)"

    # Outlaw Kindred - curated list should remain exactly its 5 intrinsic sub-tribes
    outlaw_expected = {"Warlock Kindred", "Pirate Kindred", "Rogue Kindred", "Assassin Kindred", "Mercenary Kindred"}
    outlaw_syn = set(theme_map["Outlaw Kindred"]["synergies"])
    assert outlaw_syn == outlaw_expected, f"Outlaw Kindred synergies mismatch. Expected {outlaw_expected}, got {outlaw_syn}"

    # No enforced synergy should be silently truncated if it was required (already ensured by ordering + length checks)
    # Additional safety: ensure every enforced synergy appears in its anchor (sampling a subset)
    for anchor, required in {
        "+1/+1 Counters": ["Proliferate", "Counters Matter"],
        "-1/-1 Counters": ["Proliferate", "Counters Matter"],
        "Reanimate": ["Graveyard Matters"],
    }.items():
        present = set(theme_map[anchor]["synergies"])
        missing = [r for r in required if r not in present]
        assert not missing, f"Anchor {anchor} missing enforced synergies: {missing}"

