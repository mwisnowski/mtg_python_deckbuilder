"""Aggregate commander partner/background metadata for suggestion scoring.

This utility ingests the commander catalog and existing deck exports to
construct a compact, deterministic dataset that downstream suggestion logic can
consume when ranking partner/background pairings. The output is written to
``config/analytics/partner_synergy.json`` by default and includes:

* Commander index with color identity, theme tags, and partner/background flags.
* Theme reverse index plus deck tag co-occurrence statistics.
* Observed partner/background pairings derived from deck export sidecars.

The script is intentionally light-weight so it can run as part of CI or ad-hoc
refresh workflows. All collections are sorted before serialization to guarantee
stable diffs between runs on the same inputs.
"""
from __future__ import annotations

import argparse
import json
import ast
from collections import defaultdict
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Dict, Iterable, List, MutableMapping, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from code.deck_builder.partner_background_utils import analyze_partner_background  # noqa: E402

try:  # Soft import to allow tests to override CSV path without settings.
    from code.deck_builder import builder_constants as _bc
except Exception:  # pragma: no cover - fallback when builder constants unavailable
    _bc = None  # type: ignore

DEFAULT_DECK_DIR = ROOT / "deck_files"
DEFAULT_OUTPUT_PATH = ROOT / "config" / "analytics" / "partner_synergy.json"
DEFAULT_COMMANDER_CSV = (
    Path(getattr(_bc, "COMMANDER_CSV_PATH", "")) if getattr(_bc, "COMMANDER_CSV_PATH", "") else ROOT / "csv_files" / "commander_cards.csv"
)

_WUBRG_ORDER: Tuple[str, ...] = ("W", "U", "B", "R", "G", "C")
_COLOR_PRIORITY = {color: index for index, color in enumerate(_WUBRG_ORDER)}

_ALLOWED_MODES = {
    "none",
    "partner",
    "partner_with",
    "background",
    "doctor_companion",
    "unknown",
}


def _normalize_name(value: str | None) -> str:
    return str(value or "").strip().casefold()


def _normalize_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    text = str(value or "").strip().casefold()
    if not text:
        return False
    if text in {"1", "true", "t", "yes", "on"}:
        return True
    if text in {"0", "false", "f", "no", "off"}:
        return False
    return False


def _coerce_sequence(value: object) -> Tuple[str, ...]:
    if value is None:
        return tuple()
    if isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        text = str(value).strip()
        if not text:
            return tuple()
        parsed = None
        try:
            parsed = json.loads(text)
        except Exception:
            try:
                parsed = ast.literal_eval(text)
            except Exception:
                parsed = None
        if isinstance(parsed, (list, tuple, set)):
            items = list(parsed)
        else:
            if ";" in text:
                items = [part.strip() for part in text.split(";")]
            elif "," in text:
                items = [part.strip() for part in text.split(",")]
            else:
                items = [text]
    cleaned: List[str] = []
    seen: set[str] = set()
    for item in items:
        token = str(item).strip()
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(token)
    return tuple(cleaned)


def _normalize_color_identity(values: Iterable[str]) -> Tuple[str, ...]:
    ordered: List[str] = []
    seen: set[str] = set()
    for value in values:
        token = str(value or "").strip().upper()
        if not token:
            continue
        if len(token) > 1 and all(ch in _COLOR_PRIORITY for ch in token):
            for ch in token:
                if ch not in seen:
                    seen.add(ch)
                    ordered.append(ch)
            continue
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    ordered.sort(key=lambda color: (_COLOR_PRIORITY.get(color, len(_COLOR_PRIORITY)), color))
    return tuple(ordered)


def _normalize_tag(value: str | None) -> Tuple[str, str]:
    display = str(value or "").strip()
    return display, display.casefold()


@dataclass(slots=True)
class PartnerMetadata:
    has_partner: bool
    partner_with: Tuple[str, ...]
    supports_backgrounds: bool
    choose_background: bool
    is_background: bool
    is_doctor: bool
    is_doctors_companion: bool
    has_plain_partner: bool
    has_restricted_partner: bool
    restricted_partner_labels: Tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "has_partner": self.has_partner,
            "partner_with": list(self.partner_with),
            "supports_backgrounds": self.supports_backgrounds,
            "choose_background": self.choose_background,
            "is_background": self.is_background,
            "is_doctor": self.is_doctor,
            "is_doctors_companion": self.is_doctors_companion,
            "has_plain_partner": self.has_plain_partner,
            "has_restricted_partner": self.has_restricted_partner,
            "restricted_partner_labels": list(self.restricted_partner_labels),
        }


@dataclass(slots=True)
class CommanderRecord:
    key: str
    name: str
    display_name: str
    color_identity: Tuple[str, ...]
    themes: Tuple[str, ...]
    role_tags: Tuple[str, ...]
    partner_metadata: PartnerMetadata
    usage_primary: int = 0
    usage_secondary: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "color_identity": list(self.color_identity),
            "themes": list(self.themes),
            "role_tags": list(self.role_tags),
            "partner": self.partner_metadata.to_dict(),
            "usage": {
                "primary": self.usage_primary,
                "secondary": self.usage_secondary,
                "total": self.usage_primary + self.usage_secondary,
            },
        }


@dataclass(slots=True)
class DeckRecord:
    deck_id: str
    commanders: List[str] = field(default_factory=list)
    partner_mode: str = "none"
    tags: MutableMapping[str, str] = field(default_factory=dict)
    sources: set[str] = field(default_factory=set)

    def add_tags(self, tags: Iterable[str]) -> None:
        for tag in tags:
            display, canonical = _normalize_tag(tag)
            if not canonical:
                continue
            self.tags.setdefault(canonical, display)

    def set_mode(self, mode: str) -> None:
        cleaned = _normalize_partner_mode(mode)
        if cleaned and cleaned != "none":
            self.partner_mode = cleaned


@dataclass(slots=True)
class PairingStat:
    mode: str
    primary_key: str
    primary_name: str
    secondary_key: str
    secondary_name: str
    count: int = 0
    tags: set[str] = field(default_factory=set)
    examples: List[str] = field(default_factory=list)

    def add(self, deck_id: str, tags: Iterable[str], max_examples: int) -> None:
        self.count += 1
        for tag in tags:
            self.tags.add(tag)
        if len(self.examples) < max_examples:
            self.examples.append(deck_id)

    def to_dict(self, commander_index: Dict[str, CommanderRecord]) -> dict[str, object]:
        primary_colors = list(commander_index.get(self.primary_key, CommanderRecord(
            key=self.primary_key,
            name=self.primary_name,
            display_name=self.primary_name,
            color_identity=tuple(),
            themes=tuple(),
            role_tags=tuple(),
            partner_metadata=PartnerMetadata(
                has_partner=False,
                partner_with=tuple(),
                supports_backgrounds=False,
                choose_background=False,
                is_background=False,
                is_doctor=False,
                is_doctors_companion=False,
                has_plain_partner=False,
                has_restricted_partner=False,
                restricted_partner_labels=tuple(),
            ),
        )).color_identity)
        secondary_colors = list(commander_index.get(self.secondary_key, CommanderRecord(
            key=self.secondary_key,
            name=self.secondary_name,
            display_name=self.secondary_name,
            color_identity=tuple(),
            themes=tuple(),
            role_tags=tuple(),
            partner_metadata=PartnerMetadata(
                has_partner=False,
                partner_with=tuple(),
                supports_backgrounds=False,
                choose_background=False,
                is_background=False,
                is_doctor=False,
                is_doctors_companion=False,
                has_plain_partner=False,
                has_restricted_partner=False,
                restricted_partner_labels=tuple(),
            ),
        )).color_identity)
        combined = sorted(set(primary_colors) | set(secondary_colors), key=lambda c: (_COLOR_PRIORITY.get(c, len(_COLOR_PRIORITY)), c))
        return {
            "mode": self.mode,
            "primary": self.primary_name,
            "primary_canonical": self.primary_key,
            "primary_colors": primary_colors,
            "secondary": self.secondary_name,
            "secondary_canonical": self.secondary_key,
            "secondary_colors": secondary_colors,
            "combined_colors": combined,
            "count": self.count,
            "tags": sorted(self.tags, key=lambda t: t.casefold()),
            "examples": sorted(self.examples),
        }


def _normalize_partner_mode(value: str | None) -> str:
    text = str(value or "").strip().replace("-", "_").casefold()
    if not text:
        return "none"
    replacements = {
        "partner with": "partner_with",
        "partnerwith": "partner_with",
        "choose a background": "background",
        "choose_background": "background",
        "backgrounds": "background",
        "background": "background",
        "doctor's companion": "doctor_companion",
        "doctors companion": "doctor_companion",
        "doctor companion": "doctor_companion",
    }
    normalized = replacements.get(text, text)
    if normalized not in _ALLOWED_MODES:
        if normalized in {"partnerwith"}:
            normalized = "partner_with"
        elif normalized.startswith("partner_with"):
            normalized = "partner_with"
        elif normalized.startswith("doctor"):
            normalized = "doctor_companion"
        elif normalized.startswith("background"):
            normalized = "background"
        else:
            normalized = "unknown"
    return normalized


def _resolve_commander_csv(path: str | Path | None) -> Path:
    if path:
        return Path(path).resolve()
    return Path(DEFAULT_COMMANDER_CSV).resolve()


def _resolve_deck_dir(path: str | Path | None) -> Path:
    if path:
        return Path(path).resolve()
    return Path(DEFAULT_DECK_DIR).resolve()


def _resolve_output(path: str | Path | None) -> Path:
    if path:
        return Path(path).resolve()
    return Path(DEFAULT_OUTPUT_PATH).resolve()


def _load_commander_catalog(commander_csv: Path) -> pd.DataFrame:
    if not commander_csv.exists():
        raise FileNotFoundError(f"Commander catalog not found: {commander_csv}")
    converters = getattr(_bc, "COMMANDER_CONVERTERS", None)
    if converters:
        df = pd.read_csv(commander_csv, converters=converters)
    else:  # pragma: no cover - legacy path
        df = pd.read_csv(commander_csv)
    if "themeTags" not in df.columns:
        df["themeTags"] = [[] for _ in range(len(df))]
    if "roleTags" not in df.columns:
        df["roleTags"] = [[] for _ in range(len(df))]
    return df


def _build_commander_index(df: pd.DataFrame) -> Tuple[Dict[str, CommanderRecord], Dict[str, dict]]:
    index: Dict[str, CommanderRecord] = {}
    theme_map: Dict[str, dict] = {}
    for _, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        display_name = str(row.get("faceName", "")).strip() or name
        if not display_name:
            continue
        key = _normalize_name(display_name)
        if key in index:
            continue  # Prefer first occurrence for deterministic output.

        color_identity = _normalize_color_identity(_coerce_sequence(row.get("colorIdentity")))
        if not color_identity:
            color_identity = _normalize_color_identity(_coerce_sequence(row.get("colors")))
        theme_tags = tuple(sorted({tag.strip() for tag in _coerce_sequence(row.get("themeTags")) if tag.strip()}, key=str.casefold))
        role_tags = tuple(sorted({tag.strip() for tag in _coerce_sequence(row.get("roleTags")) if tag.strip()}, key=str.casefold))

        partner_with_col = _coerce_sequence(
            row.get("partnerWith")
            or row.get("partner_with")
            or row.get("partnerNames")
            or row.get("partner_names")
        )

        detection = analyze_partner_background(
            row.get("type") or row.get("type_line"),
            row.get("text") or row.get("oracleText"),
            theme_tags or role_tags,
        )

        supports_backgrounds = bool(
            _normalize_bool(row.get("supportsBackgrounds") or row.get("supports_backgrounds"))
            or detection.choose_background
        )
        is_partner_flag = bool(_normalize_bool(row.get("isPartner") or row.get("is_partner")) or detection.has_partner)
        is_background_flag = bool(_normalize_bool(row.get("isBackground") or row.get("is_background")) or detection.is_background)
        is_doctor_flag = bool(_normalize_bool(row.get("isDoctor") or row.get("is_doctor")) or detection.is_doctor)
        is_companion_flag = bool(
            _normalize_bool(row.get("isDoctorsCompanion") or row.get("is_doctors_companion"))
            or detection.is_doctors_companion
        )

        partner_metadata = PartnerMetadata(
            has_partner=is_partner_flag,
            partner_with=tuple(sorted(set(partner_with_col) | set(detection.partner_with), key=str.casefold)),
            supports_backgrounds=supports_backgrounds,
            choose_background=detection.choose_background,
            is_background=is_background_flag,
            is_doctor=is_doctor_flag,
            is_doctors_companion=is_companion_flag,
            has_plain_partner=detection.has_plain_partner,
            has_restricted_partner=detection.has_restricted_partner,
            restricted_partner_labels=tuple(sorted(detection.restricted_partner_labels, key=str.casefold)),
        )

        record = CommanderRecord(
            key=key,
            name=name,
            display_name=display_name,
            color_identity=color_identity,
            themes=theme_tags,
            role_tags=role_tags,
            partner_metadata=partner_metadata,
        )
        index[key] = record

        for tag in theme_tags:
            display, canon = _normalize_tag(tag)
            if not canon:
                continue
            entry = theme_map.setdefault(canon, {"name": display, "commanders": set(), "co_occurrence": {}, "deck_count": 0})
            if not entry["name"]:
                entry["name"] = display
            entry["commanders"].add(display_name)
    return index, theme_map


def _deck_id_from_path(path: Path) -> str:
    name = path.name
    if name.endswith(".summary.json"):
        return name[:-len(".summary.json")]
    stem = path.stem
    return stem


def _collect_deck_records(deck_dir: Path) -> Dict[str, DeckRecord]:
    records: Dict[str, DeckRecord] = {}
    if not deck_dir.exists():
        return records

    summary_paths = sorted(deck_dir.glob("*.summary.json"))
    for path in summary_paths:
        deck_id = _deck_id_from_path(path)
        record = records.setdefault(deck_id, DeckRecord(deck_id=deck_id))
        record.sources.add(str(path.name))
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        meta = payload.get("meta")
        if isinstance(meta, dict):
            commander_name = meta.get("commander")
            if commander_name and not record.commanders:
                record.commanders = [str(commander_name).strip()]
            tags = meta.get("tags")
            if isinstance(tags, list):
                record.add_tags(tags)
        summary = payload.get("summary")
        if isinstance(summary, dict):
            commander_block = summary.get("commander")
            if isinstance(commander_block, dict):
                names = commander_block.get("names")
                if isinstance(names, list) and names:
                    record.commanders = [str(name).strip() for name in names if str(name).strip()]
                primary = commander_block.get("primary")
                secondary = commander_block.get("secondary")
                if primary and not record.commanders:
                    record.commanders = [str(primary).strip()]
                    if secondary:
                        record.commanders.append(str(secondary).strip())
                record.set_mode(commander_block.get("partner_mode"))
    text_paths = sorted(deck_dir.glob("*.txt"))
    for path in text_paths:
        deck_id = _deck_id_from_path(path)
        record = records.setdefault(deck_id, DeckRecord(deck_id=deck_id))
        record.sources.add(str(path.name))
        try:
            with path.open("r", encoding="utf-8") as handle:
                lines = [next(handle).rstrip("\n") for _ in range(10)]
        except StopIteration:
            lines = []
        except Exception:
            lines = []
        commanders_line = next((line for line in lines if line.startswith("# Commanders:")), None)
        if commanders_line:
            commanders_txt = commanders_line.split(":", 1)[1].strip()
            commanders = [part.strip() for part in commanders_txt.split(",") if part.strip()]
            if commanders:
                record.commanders = commanders
        else:
            single_line = next((line for line in lines if line.startswith("# Commander:")), None)
            if single_line and not record.commanders:
                commander_txt = single_line.split(":", 1)[1].strip()
                if commander_txt:
                    record.commanders = [commander_txt]
        mode_line = next((line for line in lines if line.startswith("# Partner Mode:")), None)
        if mode_line:
            mode_txt = mode_line.split(":", 1)[1].strip()
            record.set_mode(mode_txt)
        background_line = next((line for line in lines if line.startswith("# Background:")), None)
        if background_line:
            background_txt = background_line.split(":", 1)[1].strip()
            if background_txt:
                if record.commanders and len(record.commanders) == 1:
                    record.commanders.append(background_txt)
                elif background_txt not in record.commanders:
                    record.commanders.append(background_txt)
                record.set_mode("background")
    return records


def _infer_missing_modes(records: Dict[str, DeckRecord], commander_index: Dict[str, CommanderRecord]) -> None:
    for record in records.values():
        if len(record.commanders) <= 1:
            continue
        if record.partner_mode not in {"partner", "partner_with", "background", "doctor_companion"}:
            primary_key = _normalize_name(record.commanders[0])
            secondary_key = _normalize_name(record.commanders[1])
            primary = commander_index.get(primary_key)
            secondary = commander_index.get(secondary_key)
            if primary and secondary:
                if secondary.partner_metadata.is_background:
                    record.partner_mode = "background"
                elif primary.partner_metadata.partner_with and secondary.display_name in primary.partner_metadata.partner_with:
                    record.partner_mode = "partner_with"
                elif primary.partner_metadata.is_doctor and secondary.partner_metadata.is_doctors_companion:
                    record.partner_mode = "doctor_companion"
                elif primary.partner_metadata.is_doctors_companion and secondary.partner_metadata.is_doctor:
                    record.partner_mode = "doctor_companion"
                elif primary.partner_metadata.has_partner and secondary.partner_metadata.has_partner:
                    record.partner_mode = "partner"
                else:
                    record.partner_mode = "unknown"
            else:
                record.partner_mode = "unknown"


def _update_commander_usage(records: Dict[str, DeckRecord], commander_index: Dict[str, CommanderRecord]) -> None:
    for record in records.values():
        if not record.commanders:
            continue
        for idx, name in enumerate(record.commanders):
            key = _normalize_name(name)
            entry = commander_index.get(key)
            if entry is None:
                continue
            if idx == 0:
                entry.usage_primary += 1
            else:
                entry.usage_secondary += 1


def _build_theme_statistics(
    records: Dict[str, DeckRecord],
    theme_map: Dict[str, dict],
) -> None:
    for record in records.values():
        if not record.tags:
            continue
        tags = list(record.tags.items())
        for canonical, display in tags:
            entry = theme_map.setdefault(canonical, {"name": display, "commanders": set(), "co_occurrence": {}, "deck_count": 0})
            if not entry["name"]:
                entry["name"] = display
            entry["deck_count"] += 1
        for i in range(len(tags)):
            canon_a, display_a = tags[i]
            for j in range(i + 1, len(tags)):
                canon_b, display_b = tags[j]
                if canon_a == canon_b:
                    continue
                entry_a = theme_map.setdefault(canon_a, {"name": display_a, "commanders": set(), "co_occurrence": {}, "deck_count": 0})
                entry_b = theme_map.setdefault(canon_b, {"name": display_b, "commanders": set(), "co_occurrence": {}, "deck_count": 0})
                co_a = entry_a.setdefault("co_occurrence", {})
                co_b = entry_b.setdefault("co_occurrence", {})
                co_a[canon_b] = co_a.get(canon_b, 0) + 1
                co_b[canon_a] = co_b.get(canon_a, 0) + 1


def _collect_pairing_stats(
    records: Dict[str, DeckRecord],
    commander_index: Dict[str, CommanderRecord],
    max_examples: int,
) -> Tuple[List[dict], Dict[str, int]]:
    stats: Dict[Tuple[str, str, str], PairingStat] = {}
    mode_counts: Dict[str, int] = defaultdict(int)
    for record in records.values():
        if len(record.commanders) <= 1:
            continue
        primary_name = record.commanders[0]
        secondary_name = record.commanders[1]
        primary_key = _normalize_name(primary_name)
        secondary_key = _normalize_name(secondary_name)
        mode = record.partner_mode or "unknown"
        mode_counts[mode] += 1
        stat = stats.get((mode, primary_key, secondary_key))
        if stat is None:
            stat = PairingStat(
                mode=mode,
                primary_key=primary_key,
                primary_name=commander_index.get(primary_key, CommanderRecord(
                    key=primary_key,
                    name=primary_name,
                    display_name=primary_name,
                    color_identity=tuple(),
                    themes=tuple(),
                    role_tags=tuple(),
                    partner_metadata=PartnerMetadata(
                        has_partner=False,
                        partner_with=tuple(),
                        supports_backgrounds=False,
                        choose_background=False,
                        is_background=False,
                        is_doctor=False,
                        is_doctors_companion=False,
                        has_plain_partner=False,
                        has_restricted_partner=False,
                        restricted_partner_labels=tuple(),
                    ),
                )).display_name,
                secondary_key=secondary_key,
                secondary_name=commander_index.get(secondary_key, CommanderRecord(
                    key=secondary_key,
                    name=secondary_name,
                    display_name=secondary_name,
                    color_identity=tuple(),
                    themes=tuple(),
                    role_tags=tuple(),
                    partner_metadata=PartnerMetadata(
                        has_partner=False,
                        partner_with=tuple(),
                        supports_backgrounds=False,
                        choose_background=False,
                        is_background=False,
                        is_doctor=False,
                        is_doctors_companion=False,
                        has_plain_partner=False,
                        has_restricted_partner=False,
                        restricted_partner_labels=tuple(),
                    ),
                )).display_name,
            )
            stats[(mode, primary_key, secondary_key)] = stat
        stat.add(record.deck_id, record.tags.values(), max_examples)
    records_list = [stat.to_dict(commander_index) for stat in stats.values()]
    records_list.sort(key=lambda entry: (-entry["count"], entry["mode"], entry["primary"], entry.get("secondary", "")))
    return records_list, dict(sorted(mode_counts.items(), key=lambda item: item[0]))


def build_partner_suggestions(
    *,
    commander_csv: str | Path | None = None,
    deck_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    max_examples: int = 5,
) -> dict[str, object]:
    """Generate the partner suggestion support dataset."""

    commander_csv_path = _resolve_commander_csv(commander_csv)
    deck_directory = _resolve_deck_dir(deck_dir)
    output_file = _resolve_output(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    commander_df = _load_commander_catalog(commander_csv_path)
    commander_index, theme_map = _build_commander_index(commander_df)
    deck_records = _collect_deck_records(deck_directory)
    _infer_missing_modes(deck_records, commander_index)
    _update_commander_usage(deck_records, commander_index)
    _build_theme_statistics(deck_records, theme_map)
    pairing_records, mode_counts = _collect_pairing_stats(deck_records, commander_index, max_examples)

    commanders_payload = {
        key: record.to_dict() for key, record in sorted(commander_index.items(), key=lambda item: item[0])
    }

    themes_payload: Dict[str, dict] = {}
    for canonical, entry in sorted(theme_map.items(), key=lambda item: item[0]):
        commanders = sorted(entry.get("commanders", []), key=str.casefold)
        co_map = entry.get("co_occurrence", {}) or {}
        co_payload = {
            other: {
                "name": theme_map.get(other, {"name": other}).get("name", other),
                "count": count,
            }
            for other, count in sorted(co_map.items(), key=lambda item: item[0])
        }
        themes_payload[canonical] = {
            "name": entry.get("name", canonical),
            "commanders": commanders,
            "commander_count": len(commanders),
            "deck_count": entry.get("deck_count", 0),
            "co_occurrence": co_payload,
        }

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    decks_processed = sum(1 for record in deck_records.values() if record.commanders)
    decks_with_pairs = sum(1 for record in deck_records.values() if len(record.commanders) >= 2)

    payload: dict[str, object] = {
        "metadata": {
            "generated_at": generated_at,
            "commander_csv": str(commander_csv_path),
            "deck_directory": str(deck_directory),
            "output_path": str(output_file),
            "commander_count": len(commander_index),
            "theme_count": len(themes_payload),
            "deck_exports_total": len(deck_records),
            "deck_exports_processed": decks_processed,
            "deck_exports_with_pairs": decks_with_pairs,
        },
        "commanders": commanders_payload,
        "themes": themes_payload,
        "pairings": {
            "records": pairing_records,
            "mode_counts": mode_counts,
        },
    }

    hash_input = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    version_hash = hashlib.sha256(hash_input).hexdigest()
    payload["metadata"]["version_hash"] = version_hash
    payload["curated_overrides"] = {"version": version_hash, "entries": {}}

    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")

    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build partner suggestion support dataset")
    parser.add_argument("--commander-csv", dest="commander_csv", default=None, help="Path to commander_cards.csv")
    parser.add_argument("--deck-dir", dest="deck_dir", default=None, help="Directory containing deck export files")
    parser.add_argument("--output", dest="output_path", default=None, help="Output JSON path")
    parser.add_argument("--max-examples", dest="max_examples", type=int, default=5, help="Maximum example deck IDs to retain per pairing")
    args = parser.parse_args(list(argv) if argv is not None else None)

    payload = build_partner_suggestions(
        commander_csv=args.commander_csv,
        deck_dir=args.deck_dir,
        output_path=args.output_path,
        max_examples=args.max_examples,
    )

    summary = payload.get("metadata", {})
    decks = summary.get("deck_exports_processed", 0)
    pairs = len(payload.get("pairings", {}).get("records", []))
    print(
        f"partner_suggestions dataset written to {summary.get('output_path')} "
        f"(commanders={summary.get('commander_count')}, decks={decks}, pairings={pairs})"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
