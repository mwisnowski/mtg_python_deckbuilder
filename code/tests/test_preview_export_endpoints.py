from typing import Set

from fastapi.testclient import TestClient

from code.web.app import app  # FastAPI instance
from code.web.services.theme_catalog_loader import load_index


def _first_theme_slug() -> str:
    idx = load_index()
    # Deterministic ordering for test stability
    return sorted(idx.slug_to_entry.keys())[0]


def test_preview_export_json_and_csv_curated_only_round_trip():
    slug = _first_theme_slug()
    client = TestClient(app)

    # JSON full sample
    r = client.get(f"/themes/preview/{slug}/export.json", params={"curated_only": 0, "limit": 12})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["theme_id"] == slug
    assert data["count"] == len(data["items"]) <= 12  # noqa: SIM300
    required_keys_sampled = {"name", "roles", "score", "rarity", "mana_cost", "color_identity_list", "pip_colors"}
    sampled_role_set = {"payoff", "enabler", "support", "wildcard"}
    assert data["items"], "expected non-empty preview sample"
    for item in data["items"]:
        roles = set(item.get("roles") or [])
        # Curated examples & synthetic placeholders don't currently carry full card DB fields
        if roles.intersection(sampled_role_set):
            assert required_keys_sampled.issubset(item.keys()), f"sampled card missing expected fields: {item}"
        else:
            assert {"name", "roles", "score"}.issubset(item.keys())

    # JSON curated_only variant: ensure only curated/synthetic roles remain
    r2 = client.get(f"/themes/preview/{slug}/export.json", params={"curated_only": 1, "limit": 12})
    assert r2.status_code == 200, r2.text
    curated = r2.json()
    curated_roles_allowed: Set[str] = {"example", "curated_synergy", "synthetic"}
    for item in curated["items"]:
        roles = set(item.get("roles") or [])
        assert roles, "item missing roles"
        assert roles.issubset(curated_roles_allowed), f"unexpected sampled role present: {roles}"

    # CSV export header stability + curated_only path
    r3 = client.get(f"/themes/preview/{slug}/export.csv", params={"curated_only": 1, "limit": 12})
    assert r3.status_code == 200, r3.text
    text = r3.text.splitlines()
    assert text, "empty CSV response"
    header = text[0].strip()
    assert header == "name,roles,score,rarity,mana_cost,color_identity_list,pip_colors,reasons,tags"
    # Basic sanity: curated_only CSV should not contain a sampled role token
    sampled_role_tokens = {"payoff", "enabler", "support", "wildcard"}
    body = "\n".join(text[1:])
    for tok in sampled_role_tokens:
        assert f";{tok}" not in body, f"sampled role {tok} leaked into curated_only CSV"
