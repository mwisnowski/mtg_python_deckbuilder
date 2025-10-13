from __future__ import annotations

# Standard library imports
import json
from pathlib import Path
from typing import List, Optional

# Third-party imports
from pydantic import BaseModel, Field


class ComboPairModel(BaseModel):
    a: str
    b: str
    cheap_early: bool = False
    setup_dependent: bool = False
    tags: List[str] | None = None
    notes: Optional[str] = None


class CombosListModel(BaseModel):
    list_version: str
    generated_at: Optional[str] = None
    pairs: List[ComboPairModel] = Field(default_factory=list)


class SynergyPairModel(BaseModel):
    a: str
    b: str
    tags: List[str] | None = None
    notes: Optional[str] = None


class SynergiesListModel(BaseModel):
    list_version: str
    generated_at: Optional[str] = None
    pairs: List[SynergyPairModel] = Field(default_factory=list)


def load_and_validate_combos(path: str | Path) -> CombosListModel:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    return CombosListModel.model_validate(obj)


def load_and_validate_synergies(path: str | Path) -> SynergiesListModel:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    return SynergiesListModel.model_validate(obj)
