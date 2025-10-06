from __future__ import annotations

import os
import re
import sys
from typing import Iterable

from fastapi.testclient import TestClient

from deck_builder.builder import DeckBuilder
from deck_builder.partner_selection import apply_partner_inputs


def _fresh_client() -> TestClient:
    os.environ["ENABLE_PARTNER_MECHANICS"] = "1"
    # Ensure a fresh app import so feature flags are applied
    for module in ("code.web.app", "code.web.routes.build"):
        if module in sys.modules:
            del sys.modules[module]
    from code.web.services.commander_catalog_loader import clear_commander_catalog_cache

    clear_commander_catalog_cache()
    from code.web.app import app  # type: ignore

    client = TestClient(app)
    from code.web.services import tasks

    tasks._SESSIONS.clear()
    return client


def _first_commander_tag(commander_name: str) -> str | None:
    from code.web.services import orchestrator as orch

    tags: Iterable[str] = orch.tags_for_commander(commander_name) or []
    for tag in tags:
        value = str(tag).strip()
        if value:
            return value
    return None


_OPTION_PATTERN = re.compile(r'<option value="([^\"]*)" data-pairing-mode="([^\"]]*)"[^>]*data-role-label="([^\"]*)"', re.IGNORECASE)
_OPTION_PATTERN = re.compile(r'<option[^>]*value="([^"]+)"[^>]*data-pairing-mode="([^"]+)"[^>]*data-role-label="([^"]+)"', re.IGNORECASE)

def _partner_option_rows(html: str) -> list[tuple[str, str, str]]:
    rows = []
    for name, mode, role in _OPTION_PATTERN.findall(html or ""):
        clean_name = name.strip()
        if not clean_name:
            continue
        rows.append((clean_name, mode.strip(), role.strip()))
    return rows


def test_new_deck_inspect_includes_partner_controls() -> None:
    client = _fresh_client()
    with client:
        client.get("/build/new")
        resp = client.get("/build/new/inspect", params={"name": "Akiri, Line-Slinger"})
        assert resp.status_code == 200
        body = resp.text
        assert "Partner commander" in body
    assert "type=\"checkbox\"" not in body
    assert "Silas Renn" in body  # partner list should surface another partner option
    assert 'data-image-url="' in body


def test_partner_with_dropdown_limits_to_pair() -> None:
    client = _fresh_client()
    with client:
        client.get("/build/new")
        resp = client.get("/build/new/inspect", params={"name": "Evie Frye"})
        assert resp.status_code == 200
        body = resp.text

    assert "Automatically paired with Jacob Frye" in body
    partner_rows = re.findall(r'<option value="([^"]+)" data-pairing-mode="([^"]+)"', body)
    assert partner_rows == [("Jacob Frye", "partner_with")]
    assert "Silas Renn" not in body


def test_new_deck_submit_persists_partner_selection() -> None:
    commander = "Akiri, Line-Slinger"
    secondary = "Silas Renn, Seeker Adept"
    client = _fresh_client()
    with client:
        client.get("/build/new")
        primary_tag = _first_commander_tag(commander)
        form_data = {
            "name": "Akiri Partner Test",
            "commander": commander,
            "partner_enabled": "1",
            "secondary_commander": secondary,
            "partner_auto_opt_out": "0",
            "bracket": "3",
        }
        if primary_tag:
            form_data["primary_tag"] = primary_tag
        resp = client.post("/build/new", data=form_data)
        assert resp.status_code == 200
        assert "Stage complete" in resp.text or "Build complete" in resp.text

        from code.web.services import tasks

        sid = client.cookies.get("sid")
        assert sid, "expected sid cookie after submission"
        sess = tasks._SESSIONS.get(sid)
        assert sess is not None, "session should exist for sid"
        assert sess.get("partner_enabled") is True
        assert sess.get("secondary_commander") == secondary
        assert sess.get("partner_mode") in {"partner", "partner_with"}
        combined = sess.get("combined_commander")
        assert isinstance(combined, dict)
        assert combined.get("secondary_name") == secondary
        assert sess.get("partner_auto_opt_out") is False
        assert sess.get("partner_auto_assigned") is False
        # cleanup
        tasks._SESSIONS.pop(sid, None)


def test_doctor_companion_flow() -> None:
    commander = "The Tenth Doctor"
    companion = "Donna Noble"
    client = _fresh_client()
    with client:
        client.get("/build/new")
        inspect = client.get("/build/new/inspect", params={"name": commander})
        assert inspect.status_code == 200
        body = inspect.text
        assert "Companion" in body
        assert companion in body
        assert re.search(r"<button[^>]*data-partner-autotoggle", body) is None  # Doctor pairings should not auto-toggle

        primary_tag = _first_commander_tag(commander)
        form_data = {
            "name": "Doctor Companion Test",
            "commander": commander,
            "partner_enabled": "1",
            "secondary_commander": companion,
            "partner_auto_opt_out": "0",
            "bracket": "3",
        }
        if primary_tag:
            form_data["primary_tag"] = primary_tag
        resp = client.post("/build/new", data=form_data)
        assert resp.status_code == 200

        from code.web.services import tasks

        sid = client.cookies.get("sid")
        assert sid, "expected sid cookie after submission"
        sess = tasks._SESSIONS.get(sid)
        assert sess is not None
        assert sess.get("partner_mode") == "doctor_companion"
        assert sess.get("secondary_commander") == companion
        tasks._SESSIONS.pop(sid, None)


def test_amy_partner_options_include_rory_and_only_doctors() -> None:
    client = _fresh_client()
    with client:
        client.get("/build/new")
        resp = client.get("/build/new/inspect", params={"name": "Amy Pond"})
        assert resp.status_code == 200
        rows = _partner_option_rows(resp.text)

    partner_with_rows = [row for row in rows if row[1] == "partner_with"]
    assert any(name == "Rory Williams" for name, _, _ in partner_with_rows)
    assert len(partner_with_rows) == 1

    for name, mode, role in rows:
        if name == "Rory Williams":
            continue
        assert mode == "doctor_companion"
        assert "Doctor" in role
        assert "Companion" not in role


def test_donna_partner_options_only_list_doctors() -> None:
    client = _fresh_client()
    with client:
        client.get("/build/new")
        resp = client.get("/build/new/inspect", params={"name": "Donna Noble"})
        assert resp.status_code == 200
        rows = _partner_option_rows(resp.text)

    assert rows, "expected Doctor options for Donna"
    for name, mode, role in rows:
        assert mode == "doctor_companion"
        assert "Doctor" in role
        assert "Companion" not in role


def test_rory_partner_options_only_include_amy() -> None:
    client = _fresh_client()
    with client:
        client.get("/build/new")
        resp = client.get("/build/new/inspect", params={"name": "Rory Williams"})
        assert resp.status_code == 200
        rows = _partner_option_rows(resp.text)

    assert rows == [("Amy Pond", "partner_with", "Partner With")]


def test_step2_tags_merge_partner_union() -> None:
    commander = "Akiri, Line-Slinger"
    secondary = "Silas Renn, Seeker Adept"
    builder = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
    combined = apply_partner_inputs(
        builder,
        primary_name=commander,
        secondary_name=secondary,
        feature_enabled=True,
    )
    expected_tags = set(combined.theme_tags if combined else ())
    assert expected_tags, "expected combined commander to produce theme tags"

    client = _fresh_client()
    with client:
        client.get("/build/new")
        primary_tag = _first_commander_tag(commander)
        form_data = {
            "name": "Tag Merge",
            "commander": commander,
            "partner_enabled": "1",
            "secondary_commander": secondary,
            "partner_auto_opt_out": "0",
            "bracket": "3",
        }
        if primary_tag:
            form_data["primary_tag"] = primary_tag
        client.post("/build/new", data=form_data)

        resp = client.get("/build/step2")
        assert resp.status_code == 200
        body = resp.text
        for tag in expected_tags:
            assert tag in body


def test_step5_summary_displays_combined_partner_details() -> None:
    commander = "Halana, Kessig Ranger"
    secondary = "Alena, Kessig Trapper"
    client = _fresh_client()
    with client:
        client.get("/build/new")
        primary_tag = _first_commander_tag(commander)
        form_data = {
            "name": "Halana Alena Partner",
            "commander": commander,
            "partner_enabled": "1",
            "secondary_commander": secondary,
            "partner_auto_opt_out": "0",
            "bracket": "3",
        }
        if primary_tag:
            form_data["primary_tag"] = primary_tag
        resp = client.post("/build/new", data=form_data)
        assert resp.status_code == 200
        body = resp.text

    assert "Halana, Kessig Ranger + Alena, Kessig Trapper" in body
    assert "mana-R" in body and "mana-G" in body
    assert "Burn" in body
    assert "commander-card partner-card" in body
    assert 'data-card-name="Alena, Kessig Trapper"' in body
    assert 'width="320"' in body


def test_partner_preview_endpoint_returns_theme_tags() -> None:
    commander = "Akiri, Line-Slinger"
    secondary = "Silas Renn, Seeker Adept"
    client = _fresh_client()
    with client:
        client.get("/build/new")
        resp = client.post(
            "/build/partner/preview",
            data={
                "commander": commander,
                "partner_enabled": "1",
                "secondary_commander": secondary,
                "partner_auto_opt_out": "0",
                "scope": "step2",
            },
        )
        assert resp.status_code == 200
        payload = resp.json()

    assert payload.get("ok") is True
    preview = payload.get("preview") or {}
    assert preview.get("secondary_name") == secondary
    assert preview.get("partner_mode") in {"partner", "partner_with"}
    tags = payload.get("theme_tags") or []
    assert isinstance(tags, list)
    assert tags, "expected theme tags from partner preview"
    assert payload.get("scope") == "step2"
    assert preview.get("secondary_image_url")
    assert preview.get("secondary_role_label")
