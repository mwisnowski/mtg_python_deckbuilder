from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from tagging.combo_schema import (
    load_and_validate_combos,
    load_and_validate_synergies,
    CombosListModel,
    SynergiesListModel,
)


def _canonicalize(name: str) -> str:
    s = str(name or "").strip()
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u201C", '"').replace("\u201D", '"')
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = " ".join(s.split())
    return s


@dataclass(frozen=True)
class DetectedCombo:
    a: str
    b: str
    cheap_early: bool
    setup_dependent: bool
    tags: Optional[List[str]] = None


@dataclass(frozen=True)
class DetectedSynergy:
    a: str
    b: str
    tags: Optional[List[str]] = None


def _detect_combos_from_model(names_norm: set[str], combos: CombosListModel) -> List[DetectedCombo]:
    out: List[DetectedCombo] = []
    for p in combos.pairs:
        a = _canonicalize(p.a).casefold()
        b = _canonicalize(p.b).casefold()
        if a in names_norm and b in names_norm:
            out.append(
                DetectedCombo(
                    a=p.a,
                    b=p.b,
                    cheap_early=bool(p.cheap_early),
                    setup_dependent=bool(p.setup_dependent),
                    tags=list(p.tags or []),
                )
            )
    return out


def detect_combos(names: Iterable[str], combos_path: str | Path = "config/card_lists/combos.json") -> List[DetectedCombo]:
    names_norm = set()
    for n in names:
        c = _canonicalize(n).casefold()
        if not c:
            continue
        names_norm.add(c)

    if not names_norm:
        return []

    combos = load_and_validate_combos(combos_path)
    return _detect_combos_from_model(names_norm, combos)


def _detect_synergies_from_model(names_norm: set[str], syn: SynergiesListModel) -> List[DetectedSynergy]:
    out: List[DetectedSynergy] = []
    for p in syn.pairs:
        a = _canonicalize(p.a).casefold()
        b = _canonicalize(p.b).casefold()
        if a in names_norm and b in names_norm:
            out.append(DetectedSynergy(a=p.a, b=p.b, tags=list(p.tags or [])))
    return out


def detect_synergies(names: Iterable[str], synergies_path: str | Path = "config/card_lists/synergies.json") -> List[DetectedSynergy]:
    names_norm = {_canonicalize(n).casefold() for n in names if str(n).strip()}
    if not names_norm:
        return []
    syn = load_and_validate_synergies(synergies_path)
    return _detect_synergies_from_model(names_norm, syn)

