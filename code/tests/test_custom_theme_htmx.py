from __future__ import annotations

from typing import Iterable, Sequence

import pytest
from fastapi.testclient import TestClient

from deck_builder.theme_resolution import ThemeResolutionInfo
from web.app import app
from web.services import custom_theme_manager as ctm


def _make_info(
    requested: Sequence[str],
    *,
    resolved: Sequence[str] | None = None,
    matches: Sequence[dict[str, object]] | None = None,
    unresolved: Sequence[dict[str, object]] | None = None,
    mode: str = "permissive",
    catalog_version: str = "test-cat",
) -> ThemeResolutionInfo:
    return ThemeResolutionInfo(
        requested=list(requested),
        mode=mode,
        catalog_version=catalog_version,
        resolved=list(resolved or []),
        matches=list(matches or []),
        unresolved=list(unresolved or []),
        fuzzy_corrections={},
    )


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    def fake_resolve(
        requested: Sequence[str],
        mode: str,
        *,
        commander_tags: Iterable[str] = (),
    ) -> ThemeResolutionInfo:
        inputs = list(requested)
        if not inputs:
            return _make_info([], resolved=[], matches=[], unresolved=[])
        if inputs == ["lifgian"]:
            return _make_info(
                inputs,
                resolved=[],
                matches=[],
                unresolved=[
                    {
                        "input": "lifgian",
                        "reason": "suggestions",
                        "score": 72.0,
                        "suggestions": [{"theme": "Lifegain", "score": 91.2}],
                    }
                ],
            )
        if inputs == ["Lifegain"]:
            return _make_info(
                inputs,
                resolved=["Lifegain"],
                matches=[
                    {
                        "input": "Lifegain",
                        "matched": "Lifegain",
                        "score": 91.2,
                        "reason": "suggestion",
                        "suggestions": [],
                    }
                ],
                unresolved=[],
            )
        raise AssertionError(f"Unexpected inputs: {inputs}")

    monkeypatch.setattr(ctm, "resolve_additional_theme_inputs", fake_resolve)
    return TestClient(app)


def test_remove_theme_updates_htmx_section(client: TestClient) -> None:
    add_resp = client.post("/build/themes/add", data={"theme": "lifgian"})
    assert add_resp.status_code == 200
    add_html = add_resp.text
    assert "lifgian" in add_html
    assert "Needs attention" in add_html

    choose_resp = client.post(
        "/build/themes/choose",
        data={"original": "lifgian", "choice": "Lifegain"},
    )
    assert choose_resp.status_code == 200
    choose_html = choose_resp.text
    assert "Lifegain" in choose_html
    assert "Updated &#39;lifgian&#39; to &#39;Lifegain&#39;." in choose_html

    remove_resp = client.post("/build/themes/remove", data={"theme": "Lifegain"})
    assert remove_resp.status_code == 200
    remove_html = remove_resp.text
    assert "Theme removed." in remove_html
    assert "No supplemental themes yet." in remove_html
    assert "All themes resolved." in remove_html
    assert "Use Lifegain" not in remove_html
    assert "theme-chip" not in remove_html
