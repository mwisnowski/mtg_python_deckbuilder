from __future__ import annotations

import pytest

from code.web.services.theme_preview import get_theme_preview  # type: ignore
from code.web.services.theme_catalog_loader import load_index, slugify, project_detail  # type: ignore


@pytest.mark.parametrize("limit", [8, 12])
def test_preview_role_ordering(limit):
    # Pick a deterministic existing theme (first catalog theme)
    idx = load_index()
    assert idx.catalog.themes, "No themes available for preview test"
    theme = idx.catalog.themes[0].theme
    preview = get_theme_preview(theme, limit=limit)
    # Ensure curated examples (role=example) all come before any curated_synergy, which come before any payoff/enabler/support/wildcard
    roles = [c["roles"][0] for c in preview["sample"] if c.get("roles")]
    # Find first indices
    first_curated_synergy = next((i for i, r in enumerate(roles) if r == "curated_synergy"), None)
    first_non_curated = next((i for i, r in enumerate(roles) if r not in {"example", "curated_synergy"}), None)
    # If both present, ordering constraints
    if first_curated_synergy is not None and first_non_curated is not None:
        assert first_curated_synergy < first_non_curated, "curated_synergy block should precede sampled roles"
    # All example indices must be < any curated_synergy index
    if first_curated_synergy is not None:
        for i, r in enumerate(roles):
            if r == "example":
                assert i < first_curated_synergy, "example card found after curated_synergy block"


def test_synergy_commanders_no_overlap_with_examples():
    idx = load_index()
    theme_entry = idx.catalog.themes[0]
    slug = slugify(theme_entry.theme)
    detail = project_detail(slug, idx.slug_to_entry[slug], idx.slug_to_yaml, uncapped=False)
    examples = set(detail.get("example_commanders") or [])
    synergy_commanders = detail.get("synergy_commanders") or []
    assert not (examples.intersection(synergy_commanders)), "synergy_commanders should not include example_commanders"
