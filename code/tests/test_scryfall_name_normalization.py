import re
from code.web.services.theme_preview import get_theme_preview

# We can't easily execute the JS normalizeCardName in Python, but we can ensure
# server-delivered sample names that include appended synergy annotations are not
# leaking into subsequent lookups by simulating the name variant and asserting
# normalization logic (mirrors regex in base.html) would strip it.

NORMALIZE_RE = re.compile(r"(.*?)(\s*-\s*Synergy\s*\(.*\))$", re.IGNORECASE)

def normalize(name: str) -> str:
    m = NORMALIZE_RE.match(name)
    if m:
        return m.group(1).strip()
    return name


def test_synergy_annotation_regex_strips_suffix():
    raw = "Sol Ring - Synergy (Blink Engines)"
    assert normalize(raw) == "Sol Ring"


def test_preview_sample_names_do_not_contain_synergy_suffix():
    # Build a preview; sample names might include curated examples but should not
    # include the synthesized ' - Synergy (' suffix in stored payload.
    pv = get_theme_preview('Blink', limit=12)
    for it in pv.get('sample', []):
        name = it.get('name','')
        # Ensure regex would not change valid names; if it would, that's a leak.
        assert normalize(name) == name, f"Name leaked synergy annotation: {name}"