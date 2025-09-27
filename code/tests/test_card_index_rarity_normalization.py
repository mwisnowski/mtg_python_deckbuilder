import csv
from code.web.services import card_index

def test_rarity_normalization_and_duplicate_handling(tmp_path, monkeypatch):
    # Create a temporary CSV simulating duplicate rarities and variant casing
    csv_path = tmp_path / "cards.csv"
    rows = [
        {"name": "Alpha Beast", "themeTags": "testtheme", "colorIdentity": "G", "manaCost": "3G", "rarity": "MyThic"},
        {"name": "Alpha Beast", "themeTags": "othertheme", "colorIdentity": "G", "manaCost": "3G", "rarity": "MYTHIC RARE"},
        {"name": "Helper Sprite", "themeTags": "testtheme", "colorIdentity": "U", "manaCost": "1U", "rarity": "u"},
        {"name": "Common Grunt", "themeTags": "testtheme", "colorIdentity": "R", "manaCost": "1R", "rarity": "COMMON"},
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["name","themeTags","colorIdentity","manaCost","rarity"])
        writer.writeheader()
        writer.writerows(rows)

    # Monkeypatch CARD_FILES_GLOB to only use our temp file
    monkeypatch.setattr(card_index, "CARD_FILES_GLOB", [csv_path])

    card_index.maybe_build_index()
    pool = card_index.get_tag_pool("testtheme")
    # Expect three entries for testtheme (Alpha Beast (first occurrence), Helper Sprite, Common Grunt)
    names = sorted(c["name"] for c in pool)
    assert names == ["Alpha Beast", "Common Grunt", "Helper Sprite"]
    # Assert rarity normalization collapsed variants
    rarities = {c["name"]: c["rarity"] for c in pool}
    assert rarities["Alpha Beast"] == "mythic"
    assert rarities["Helper Sprite"] == "uncommon"
    assert rarities["Common Grunt"] == "common"
