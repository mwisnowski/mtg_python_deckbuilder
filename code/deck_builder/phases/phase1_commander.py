from __future__ import annotations
from typing import List, Optional
import pandas as pd
from .phase0_core import BracketDefinition, BRACKET_DEFINITIONS  # noqa: F401

"""Phase 1: Commander & Tag Selection logic.

Extracted from builder.py to reduce monolith size. All public method names and
signatures preserved; DeckBuilder will delegate to these mixin-style functions.

Provided functions expect `self` to be a DeckBuilder instance exposing:
  - input_func, output_func
  - load_commander_data, _auto_accept, _gather_candidates, _format_commander_pretty,
    _initialize_commander_dict
  - commander_name, commander_row, commander_tags, commander_dict
  - selected_tags, primary_tag, secondary_tag, tertiary_tag
  - bracket_definition related attributes for printing summary

No side‑effect changes.
"""
# (Imports moved to top for lint compliance)

class CommanderSelectionMixin:
    # ---------------------------
    # Commander Selection
    # ---------------------------
    def choose_commander(self) -> str:  # type: ignore[override]
        df = self.load_commander_data()
        names = df["name"].tolist()
        while True:
            query = self.input_func("Enter commander name: ").strip()
            if not query:
                self.output_func("No input provided. Try again.")
                continue
            direct_hits = [n for n in names if self._auto_accept(query, n)]
            if len(direct_hits) == 1:
                candidate = direct_hits[0]
                self.output_func(f"(Auto match candidate) {candidate}")
                if self._present_commander_and_confirm(df, candidate):
                    self.output_func(f"Confirmed: {candidate}")
                    return candidate
                else:
                    self.output_func("Not confirmed. Starting over.\n")
                    continue
            candidates = self._gather_candidates(query, names)
            if not candidates:
                self.output_func("No close matches found. Try again.")
                continue
            self.output_func("\nTop matches:")
            for idx, (n, score) in enumerate(candidates, start=1):
                self.output_func(f"  {idx}. {n}  (score {score})")
            self.output_func("Enter number to inspect, 'r' to retry, or type a new name:")
            choice = self.input_func("Selection: ").strip()
            if choice.lower() == 'r':
                continue
            if choice.isdigit():
                i = int(choice)
                if 1 <= i <= len(candidates):
                    nm = candidates[i - 1][0]
                    if self._present_commander_and_confirm(df, nm):
                        self.output_func(f"Confirmed: {nm}")
                        return nm
                    else:
                        self.output_func("Not confirmed. Search again.\n")
                        continue
                else:
                    self.output_func("Invalid index.")
                    continue
            query = choice  # treat as new query

    def _present_commander_and_confirm(self, df: pd.DataFrame, name: str) -> bool:  # type: ignore[override]
        row = df[df["name"] == name].iloc[0]
        pretty = self._format_commander_pretty(row)
        self.output_func("\n" + pretty)
        while True:
            resp = self.input_func("Is this the commander you want? (y/n): ").strip().lower()
            if resp in ("y", "yes"):
                self._apply_commander_selection(row)
                return True
            if resp in ("n", "no"):
                return False
            self.output_func("Please enter y or n.")

    def _apply_commander_selection(self, row: pd.Series):  # type: ignore[override]
        self.commander_name = row["name"]
        self.commander_row = row
        self.commander_tags = list(row.get("themeTags", []) or [])
        self._initialize_commander_dict(row)

    # ---------------------------
    # Tag Prioritization
    # ---------------------------
    def select_commander_tags(self) -> List[str]:  # type: ignore[override]
        if not self.commander_name:
            self.output_func("No commander chosen yet. Selecting commander first...")
            self.choose_commander()
        tags = list(dict.fromkeys(self.commander_tags))
        if not tags:
            self.output_func("Commander has no theme tags available.")
            self.selected_tags = []
            self.primary_tag = self.secondary_tag = self.tertiary_tag = None
            self._update_commander_dict_with_selected_tags()
            return self.selected_tags
        self.output_func("\nAvailable Theme Tags:")
        for i, t in enumerate(tags, 1):
            self.output_func(f"  {i}. {t}")
        self.selected_tags = []
        self.primary_tag = self._prompt_tag_choice(tags, "Select PRIMARY tag (required):", allow_stop=False)
        self.selected_tags.append(self.primary_tag)
        remaining = [t for t in tags if t not in self.selected_tags]
        if remaining:
            self.secondary_tag = self._prompt_tag_choice(remaining, "Select SECONDARY tag (or 0 to stop here):", allow_stop=True)
            if self.secondary_tag:
                self.selected_tags.append(self.secondary_tag)
                remaining = [t for t in remaining if t != self.secondary_tag]
        if remaining and self.secondary_tag:
            self.tertiary_tag = self._prompt_tag_choice(remaining, "Select TERTIARY tag (or 0 to stop here):", allow_stop=True)
            if self.tertiary_tag:
                self.selected_tags.append(self.tertiary_tag)
        self.output_func("\nChosen Tags (in priority order):")
        if not self.selected_tags:
            self.output_func("  (None)")
        else:
            for idx, tag in enumerate(self.selected_tags, 1):
                label = ["Primary", "Secondary", "Tertiary"][idx - 1] if idx <= 3 else f"Tag {idx}"
                self.output_func(f"  {idx}. {tag} ({label})")
        self._update_commander_dict_with_selected_tags()
        return self.selected_tags

    def _prompt_tag_choice(self, available: List[str], prompt_text: str, allow_stop: bool) -> Optional[str]:  # type: ignore[override]
        while True:
            self.output_func("\nCurrent options:")
            for i, t in enumerate(available, 1):
                self.output_func(f"  {i}. {t}")
            if allow_stop:
                self.output_func("  0. Stop (no further tags)")
            raw = self.input_func(f"{prompt_text} ").strip()
            if allow_stop and raw == "0":
                return None
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(available):
                    return available[idx - 1]
            matches = [t for t in available if t.lower() == raw.lower()]
            if matches:
                return matches[0]
            self.output_func("Invalid selection. Try again.")

    def _update_commander_dict_with_selected_tags(self):  # type: ignore[override]
        if not self.commander_dict and self.commander_row is not None:
            self._initialize_commander_dict(self.commander_row)
        if not self.commander_dict:
            return
        self.commander_dict["Primary Tag"] = self.primary_tag
        self.commander_dict["Secondary Tag"] = self.secondary_tag
        self.commander_dict["Tertiary Tag"] = self.tertiary_tag
        self.commander_dict["Selected Tags"] = self.selected_tags.copy()

    # ---------------------------
    # Power Bracket Selection
    # ---------------------------
    def select_power_bracket(self) -> BracketDefinition:  # type: ignore[override]
        if self.bracket_definition:
            return self.bracket_definition
        self.output_func("\nChoose Deck Power Bracket:")
        for bd in BRACKET_DEFINITIONS:
            self.output_func(f"  {bd.level}. {bd.name} - {bd.short_desc}")
        while True:
            raw = self.input_func("Enter bracket number (1-5) or 'info' for details: ").strip().lower()
            if raw == "info":
                self._print_bracket_details()
                continue
            if raw.isdigit():
                num = int(raw)
                match = next((bd for bd in BRACKET_DEFINITIONS if bd.level == num), None)
                if match:
                    self.bracket_definition = match
                    self.bracket_level = match.level
                    self.bracket_name = match.name
                    self.bracket_limits = match.limits.copy()
                    self.output_func(f"\nSelected Bracket {match.level}: {match.name}")
                    self._print_selected_bracket_summary()
                    return match
            self.output_func("Invalid input. Type 1-5 or 'info'.")

    def _print_bracket_details(self):  # type: ignore[override]
        self.output_func("\nBracket Details:")
        for bd in BRACKET_DEFINITIONS:
            self.output_func(f"\n[{bd.level}] {bd.name}")
            self.output_func(bd.long_desc)
            self.output_func(self._format_limits(bd.limits))

    def _print_selected_bracket_summary(self):  # type: ignore[override]
        self.output_func("\nBracket Constraints:")
        if self.bracket_limits:
            self.output_func(self._format_limits(self.bracket_limits))

__all__ = [
    'CommanderSelectionMixin'
]
