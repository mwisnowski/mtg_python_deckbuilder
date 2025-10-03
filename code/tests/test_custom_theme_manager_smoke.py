from __future__ import annotations

from typing import Dict, Iterable, Sequence

import pytest

from deck_builder.theme_resolution import ThemeResolutionInfo
from web.services import custom_theme_manager as ctm


def _make_info(
    requested: Sequence[str],
    *,
    resolved: Sequence[str] | None = None,
    matches: Sequence[Dict[str, object]] | None = None,
    unresolved: Sequence[Dict[str, object]] | None = None,
    mode: str = "permissive",
) -> ThemeResolutionInfo:
    return ThemeResolutionInfo(
        requested=list(requested),
        mode=mode,
        catalog_version="test-cat",
        resolved=list(resolved or []),
        matches=list(matches or []),
        unresolved=list(unresolved or []),
        fuzzy_corrections={},
    )


def test_add_theme_exact_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    session: Dict[str, object] = {}

    def fake_resolve(requested: Sequence[str], mode: str, *, commander_tags: Iterable[str] = ()) -> ThemeResolutionInfo:
        assert list(requested) == ["Lifegain"]
        assert mode == "permissive"
        return _make_info(
            requested,
            resolved=["Lifegain"],
            matches=[{"input": "Lifegain", "matched": "Lifegain", "score": 100.0, "reason": "exact", "suggestions": []}],
        )

    monkeypatch.setattr(ctm, "resolve_additional_theme_inputs", fake_resolve)

    info, message, level = ctm.add_theme(
        session,
        "Lifegain",
        commander_tags=(),
        mode="permissive",
        limit=ctm.DEFAULT_THEME_LIMIT,
    )

    assert info is not None
    assert info.resolved == ["Lifegain"]
    assert session["custom_theme_inputs"] == ["Lifegain"]
    assert session["additional_themes"] == ["Lifegain"]
    assert message == "Added theme 'Lifegain'."
    assert level == "success"


def test_add_theme_choose_suggestion_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    session: Dict[str, object] = {}

    def fake_resolve(requested: Sequence[str], mode: str, *, commander_tags: Iterable[str] = ()) -> ThemeResolutionInfo:
        inputs = list(requested)
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
                        "input": "lifgian",
                        "matched": "Lifegain",
                        "score": 91.2,
                        "reason": "suggestion",
                        "suggestions": [],
                    }
                ],
            )
        pytest.fail(f"Unexpected inputs {inputs}")

    monkeypatch.setattr(ctm, "resolve_additional_theme_inputs", fake_resolve)

    info, message, level = ctm.add_theme(
        session,
        "lifgian",
        commander_tags=(),
        mode="permissive",
        limit=ctm.DEFAULT_THEME_LIMIT,
    )
    assert info is not None
    assert not info.resolved
    assert session["custom_theme_inputs"] == ["lifgian"]
    assert message == "Added theme 'lifgian'."
    assert level == "success"

    info, message, level = ctm.choose_suggestion(
        session,
        "lifgian",
        "Lifegain",
        commander_tags=(),
        mode="permissive",
    )
    assert info is not None
    assert info.resolved == ["Lifegain"]
    assert session["custom_theme_inputs"] == ["Lifegain"]
    assert session["additional_themes"] == ["Lifegain"]
    assert message == "Updated 'lifgian' to 'Lifegain'."
    assert level == "success"


def test_remove_theme_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    session: Dict[str, object] = {"custom_theme_inputs": ["Lifegain"], "additional_themes": ["Lifegain"]}

    def fake_resolve(requested: Sequence[str], mode: str, *, commander_tags: Iterable[str] = ()) -> ThemeResolutionInfo:
        assert requested == []
        return _make_info(requested, resolved=[], matches=[], unresolved=[])

    monkeypatch.setattr(ctm, "resolve_additional_theme_inputs", fake_resolve)

    info, message, level = ctm.remove_theme(
        session,
        "Lifegain",
        commander_tags=(),
        mode="permissive",
    )

    assert info is not None
    assert session["custom_theme_inputs"] == []
    assert session["additional_themes"] == []
    assert message == "Theme removed."
    assert level == "success"