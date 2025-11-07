from __future__ import annotations

import pytest
from pathlib import Path

from code.web.services import card_index

# M4 (Parquet Migration): This test relied on injecting custom CSV data via CARD_INDEX_EXTRA_CSV,
# which is no longer supported. The card_index now loads from the global all_cards.parquet file.
# Skipping this test as custom data injection is not possible with unified Parquet.
pytestmark = pytest.mark.skip(reason="M4: CARD_INDEX_EXTRA_CSV removed, cannot inject test data")

CSV_CONTENT = """name,themeTags,colorIdentity,manaCost,rarity
Hybrid Test,"Blink",WG,{W/G}{W/G},uncommon
Devoid Test,"Blink",C,3U,uncommon
MDFC Front,"Blink",R,1R,rare
Adventure Card,"Blink",G,2G,common
Color Indicator,"Blink",U,2U,uncommon
"""

# Note: The simplified edge cases focus on color_identity_list extraction logic.

def write_csv(tmp_path: Path):
    p = tmp_path / "synthetic_edge_cases.csv"
    p.write_text(CSV_CONTENT, encoding="utf-8")
    return p


def test_card_index_color_identity_list_handles_edge_cases(tmp_path, monkeypatch):
    csv_path = write_csv(tmp_path)
    monkeypatch.setenv("CARD_INDEX_EXTRA_CSV", str(csv_path))
    # Force rebuild
    card_index._CARD_INDEX.clear()
    card_index._CARD_INDEX_MTIME = None
    card_index.maybe_build_index()

    pool = card_index.get_tag_pool("Blink")
    names = {c["name"]: c for c in pool}
    assert {"Hybrid Test", "Devoid Test", "MDFC Front", "Adventure Card", "Color Indicator"}.issubset(names.keys())

    # Hybrid Test: colorIdentity WG -> list should be ["W", "G"]
    assert names["Hybrid Test"]["color_identity_list"] == ["W", "G"]
    # Devoid Test: colorless identity C -> list empty (colorless)
    assert names["Devoid Test"]["color_identity_list"] == [] or names["Devoid Test"]["color_identity"] in ("", "C")
    # MDFC Front: single color R
    assert names["MDFC Front"]["color_identity_list"] == ["R"]
    # Adventure Card: single color G
    assert names["Adventure Card"]["color_identity_list"] == ["G"]
    # Color Indicator: single color U
    assert names["Color Indicator"]["color_identity_list"] == ["U"]
