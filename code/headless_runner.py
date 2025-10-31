from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from deck_builder.builder import DeckBuilder
from deck_builder import builder_constants as bc
from deck_builder.partner_selection import apply_partner_inputs
from deck_builder.theme_resolution import (
    ThemeResolutionInfo,
    clean_theme_inputs,
    normalize_theme_match_mode,
    parse_theme_list,
    resolve_additional_theme_inputs,
)
from file_setup.setup import initial_setup
from tagging import tagger
from exceptions import CommanderValidationError

def _is_stale(file1: str, file2: str) -> bool:
    """Return True if file2 is missing or older than file1."""
    if not os.path.isfile(file2):
        return True
    if not os.path.isfile(file1):
        return True
    return os.path.getmtime(file2) < os.path.getmtime(file1)

def _ensure_data_ready():
    # M4: Check for Parquet file instead of CSV
    from path_util import get_processed_cards_path
    
    parquet_path = get_processed_cards_path()
    tagging_json = os.path.join("csv_files", ".tagging_complete.json")
    
    # If all_cards.parquet is missing, run full setup+tagging
    if not os.path.isfile(parquet_path):
        print("all_cards.parquet not found, running full setup and tagging...")
        initial_setup()
        tagger.run_tagging(parallel=True)  # Use parallel tagging for performance
        _write_tagging_flag(tagging_json)
    # If tagging_complete is missing or stale, run tagging
    elif not os.path.isfile(tagging_json) or _is_stale(parquet_path, tagging_json):
        print(".tagging_complete.json missing or stale, running tagging...")
        tagger.run_tagging(parallel=True)  # Use parallel tagging for performance
        _write_tagging_flag(tagging_json)

def _write_tagging_flag(tagging_json):
    import json
    from datetime import datetime
    os.makedirs(os.path.dirname(tagging_json), exist_ok=True)
    with open(tagging_json, 'w', encoding='utf-8') as f:
        json.dump({'tagged_at': datetime.now().isoformat(timespec='seconds')}, f)


def _headless_owned_cards_dir() -> str:
    env_dir = os.getenv("OWNED_CARDS_DIR") or os.getenv("CARD_LIBRARY_DIR")
    if env_dir:
        return env_dir
    if os.path.isdir("owned_cards"):
        return "owned_cards"
    if os.path.isdir("card_library"):
        return "card_library"
    return "owned_cards"


def _headless_list_owned_files() -> List[str]:
    folder = _headless_owned_cards_dir()
    entries: List[str] = []
    try:
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                path = os.path.join(folder, name)
                if os.path.isfile(path) and name.lower().endswith((".txt", ".csv")):
                    entries.append(path)
    except Exception:
        return []
    return sorted(entries)


def _normalize_commander_name(value: Any) -> str:
    return str(value or "").strip().casefold()


def _tokenize_commander_name(value: Any) -> List[str]:
    normalized = _normalize_commander_name(value)
    if not normalized:
        return []
    return [token for token in re.split(r"[^a-z0-9]+", normalized) if token]



@lru_cache(maxsize=1)
def _load_commander_name_lookup() -> Tuple[set[str], Tuple[str, ...]]:
    builder = DeckBuilder(
        headless=True,
        log_outputs=False,
        output_func=lambda *_: None,
        input_func=lambda *_: "",
    )
    df = builder.load_commander_data()
    raw_names: List[str] = []
    for column in ("name", "faceName"):
        if column not in df.columns:
            continue
        series = df[column].dropna().astype(str)
        raw_names.extend(series.tolist())
    normalized = {
        norm
        for norm in (_normalize_commander_name(name) for name in raw_names)
        if norm
    }
    ordered_raw = tuple(dict.fromkeys(raw_names))
    return normalized, ordered_raw


def _validate_commander_available(command_name: str) -> None:
    normalized = _normalize_commander_name(command_name)
    if not normalized:
        return

    available, raw_names = _load_commander_name_lookup()
    if normalized in available:
        return

    query_tokens = _tokenize_commander_name(command_name)
    for candidate in raw_names:
        candidate_norm = _normalize_commander_name(candidate)
        if not candidate_norm:
            continue
        if candidate_norm.startswith(normalized):
            return
        candidate_tokens = _tokenize_commander_name(candidate)
        if query_tokens and all(token in candidate_tokens for token in query_tokens):
            return

    try:
        from commander_exclusions import lookup_commander_detail as _lookup_commander_detail
    except ImportError:  # pragma: no cover
        _lookup_commander_detail = None

    info = _lookup_commander_detail(command_name) if _lookup_commander_detail else None
    if info is not None:
        primary_face = str(info.get("primary_face") or info.get("name") or "").strip()
        eligible_faces = info.get("eligible_faces")
        face_hint = ", ".join(str(face) for face in eligible_faces) if isinstance(eligible_faces, list) else ""
        message = (
            f"Commander '{command_name}' is no longer available because only a secondary face met commander eligibility."
        )
        if primary_face and _normalize_commander_name(primary_face) != normalized:
            message += f" Try selecting the front face '{primary_face}' or choose a different commander."
        elif face_hint:
            message += f" The remaining eligible faces were: {face_hint}."
        else:
            message += " Choose a different commander whose front face is commander-legal."
        raise CommanderValidationError(message, details={"commander": command_name, "reason": info})

    raise CommanderValidationError(f"Commander not found: {command_name}", details={"commander": command_name})


@dataclass
class RandomRunConfig:
    """Runtime options for the headless random build flow."""

    legacy_theme: Optional[str] = None
    primary_theme: Optional[str] = None
    secondary_theme: Optional[str] = None
    tertiary_theme: Optional[str] = None
    auto_fill_missing: bool = False
    auto_fill_secondary: Optional[bool] = None
    auto_fill_tertiary: Optional[bool] = None
    strict_theme_match: bool = False
    attempts: int = 5
    timeout_ms: int = 5000
    seed: Optional[int | str] = None
    constraints: Dict[str, Any] = field(default_factory=dict)
    output_json: Optional[str] = None

def run(
    command_name: str = "",
    add_creatures: bool = True,
    add_non_creature_spells: bool = True,
    add_ramp: bool = True,
    add_removal: bool = True,
    add_wipes: bool = True,
    add_card_advantage: bool = True,
    add_protection: bool = True,
    primary_choice: int = 1,
    secondary_choice: Optional[int] = None,
    tertiary_choice: Optional[int] = None,
    add_lands: bool = True,
    fetch_count: Optional[int] = 3,
    dual_count: Optional[int] = None,
    triple_count: Optional[int] = None,
    utility_count: Optional[int] = None,
    ideal_counts: Optional[Dict[str, int]] = None,
    bracket_level: Optional[int] = None,
    # Include/Exclude configuration (M1: Config + Validation + Persistence)
    include_cards: Optional[List[str]] = None,
    exclude_cards: Optional[List[str]] = None,
    enforcement_mode: str = "warn",
    allow_illegal: bool = False,
    fuzzy_matching: bool = True,
    seed: Optional[int | str] = None,
    additional_themes: Optional[List[str]] = None,
    theme_match_mode: str = "permissive",
    user_theme_resolution: Optional[ThemeResolutionInfo] = None,
    user_theme_weight: Optional[float] = None,
    secondary_commander: Optional[str] = None,
    background: Optional[str] = None,
    enable_partner_mechanics: bool = False,
) -> DeckBuilder:
    """Run a scripted non-interactive deck build and return the DeckBuilder instance.

    When ``enable_partner_mechanics`` is True, optional ``secondary_commander``
    or ``background`` inputs are resolved into a combined commander pairing
    before any deck-building steps execute.
    """
    trimmed_commander = (command_name or "").strip()
    if trimmed_commander:
        _validate_commander_available(trimmed_commander)

    owned_prompt_inputs: List[str] = []
    owned_files_available = _headless_list_owned_files()
    if owned_files_available:
        use_owned_flag = _parse_bool(os.getenv("HEADLESS_USE_OWNED_ONLY"))
        if use_owned_flag:
            owned_prompt_inputs.append("y")
            selection = (os.getenv("HEADLESS_OWNED_SELECTION") or "").strip()
            owned_prompt_inputs.append(selection)
        else:
            owned_prompt_inputs.append("n")

    scripted_inputs: List[str] = []
    # Commander query & selection
    scripted_inputs.append(command_name)        # initial query
    scripted_inputs.append("1")                # choose first search match to inspect
    scripted_inputs.append("y")                # confirm commander
    # Primary tag selection
    scripted_inputs.append(str(primary_choice))
    # Secondary tag selection or stop (0)
    if secondary_choice is not None:
        scripted_inputs.append(str(secondary_choice))
        # Tertiary tag selection or stop (0)
        if tertiary_choice is not None:
            scripted_inputs.append(str(tertiary_choice))
        else:
            scripted_inputs.append("0")
    else:
        scripted_inputs.append("0")  # stop at primary
    scripted_inputs.extend(owned_prompt_inputs)
    # Bracket (meta power / style) selection; default to 3 if not provided
    scripted_inputs.append(str(bracket_level if isinstance(bracket_level, int) and 1 <= bracket_level <= 5 else 3))
    # Ideal count prompts (press Enter for defaults). Include fetch_lands if present.
    ideal_keys = {
        "ramp",
        "lands",
        "basic_lands",
        "fetch_lands",
        "creatures",
        "removal",
        "wipes",
        "card_advantage",
        "protection",
    }
    for key in bc.DECK_COMPOSITION_PROMPTS.keys():
        if key in ideal_keys:
            scripted_inputs.append("")

    def scripted_input(prompt: str) -> str:
        if scripted_inputs:
            return scripted_inputs.pop(0)
        # Fallback to auto-accept defaults for any unexpected prompts
        return ""

    builder = DeckBuilder(input_func=scripted_input)
    # Optional deterministic seed for Random Modes (does not affect core when unset)
    try:
        if seed is not None:
            builder.set_seed(seed)
    except Exception:
        pass
    # Mark this run as headless so builder can adjust exports and logging
    try:
        builder.headless = True
    except Exception:
        pass

    partner_feature_enabled = bool(enable_partner_mechanics)
    secondary_clean = (secondary_commander or "").strip()
    background_clean = (background or "").strip()
    try:
        builder.partner_feature_enabled = partner_feature_enabled
        builder.requested_secondary_commander = secondary_clean or None
        builder.requested_background = background_clean or None
    except Exception:
        pass

    if partner_feature_enabled and trimmed_commander:
        combined_result = apply_partner_inputs(
            builder,
            primary_name=trimmed_commander,
            secondary_name=secondary_clean or None,
            background_name=background_clean or None,
            feature_enabled=True,
        )
        if combined_result is not None:
            _apply_combined_commander_to_builder(builder, combined_result)
    
    # Configure include/exclude settings (M1: Config + Validation + Persistence)
    try:
        builder.include_cards = list(include_cards or [])
        builder.exclude_cards = list(exclude_cards or [])
        builder.enforcement_mode = enforcement_mode
        builder.allow_illegal = allow_illegal
        builder.fuzzy_matching = fuzzy_matching
    except Exception:
        pass

    normalized_theme_mode = normalize_theme_match_mode(theme_match_mode)
    theme_resolution = user_theme_resolution
    if theme_resolution is None:
        theme_resolution = resolve_additional_theme_inputs(
            additional_themes or [],
            normalized_theme_mode,
        )
    else:
        if theme_resolution.mode != normalized_theme_mode:
            theme_resolution = resolve_additional_theme_inputs(
                theme_resolution.requested,
                normalized_theme_mode,
            )

    try:
        builder.theme_match_mode = theme_resolution.mode
        builder.theme_catalog_version = theme_resolution.catalog_version
        builder.user_theme_requested = list(theme_resolution.requested)
        builder.user_theme_resolved = list(theme_resolution.resolved)
        builder.user_theme_matches = list(theme_resolution.matches)
        builder.user_theme_unresolved = list(theme_resolution.unresolved)
        builder.user_theme_fuzzy_corrections = dict(theme_resolution.fuzzy_corrections)
        builder.user_theme_resolution = theme_resolution
        if user_theme_weight is not None:
            builder.user_theme_weight = float(user_theme_weight)
    except Exception:
        pass
        
    # If ideal_counts are provided (from JSON), use them as the current defaults
    # so the step 2 prompts will show these values and our blank entries will accept them.
    if isinstance(ideal_counts, dict) and ideal_counts:
        try:
            ic: Dict[str, int] = {}
            for k, v in ideal_counts.items():
                try:
                    iv = int(v) if v is not None else None
                except Exception:
                    continue
                if iv is None:
                    continue
                # Only accept known keys
                if k in {"ramp","lands","basic_lands","creatures","removal","wipes","card_advantage","protection"}:
                    ic[k] = iv
            if ic:
                builder.ideal_counts.update(ic)
        except Exception:
            pass
    builder.run_initial_setup()
    builder.run_deck_build_step1()
    builder.run_deck_build_step2()
    
    # Land sequence (optional)
    if add_lands:
        def call(method: str, **kwargs: Any) -> None:
            fn = getattr(builder, method, None)
            if callable(fn):
                try:
                    fn(**kwargs)
                except Exception:
                    pass
        for method, kwargs in [
            ("run_land_step1", {}),
            ("run_land_step2", {}),
            ("run_land_step3", {}),
            ("run_land_step4", {"requested_count": fetch_count}),
            ("run_land_step5", {"requested_count": dual_count}),
            ("run_land_step6", {"requested_count": triple_count}),
            ("run_land_step7", {"requested_count": utility_count}),
            ("run_land_step8", {}),
        ]:
            call(method, **kwargs)

    if add_creatures:
        builder.add_creatures()
    # Non-creature spell categories (ramp / removal / wipes / draw / protection)
    did_bulk = False
    if add_non_creature_spells and hasattr(builder, "add_non_creature_spells"):
        try:
            builder.add_non_creature_spells()
            did_bulk = True
        except Exception:
            did_bulk = False
    if not did_bulk:
        for method, flag in [
            ("add_ramp", add_ramp),
            ("add_removal", add_removal),
            ("add_board_wipes", add_wipes),
            ("add_card_advantage", add_card_advantage),
            ("add_protection", add_protection),
        ]:
            if flag:
                fn = getattr(builder, method, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
        

    builder.post_spell_land_adjust()
    _export_outputs(builder)
    return builder

def _should_export_json_headless() -> bool:
    return os.getenv('HEADLESS_EXPORT_JSON', '').strip().lower() in {'1','true','yes','on'}

def _print_include_exclude_summary(builder: DeckBuilder) -> None:
    """Print include/exclude summary to console (M4: Extended summary printing)."""
    if not hasattr(builder, 'include_exclude_diagnostics') or not builder.include_exclude_diagnostics:
        return
    
    diagnostics = builder.include_exclude_diagnostics
    
    # Skip if no include/exclude activity
    if not any([
        diagnostics.get('include_cards'),
        diagnostics.get('exclude_cards'), 
        diagnostics.get('include_added'),
        diagnostics.get('excluded_removed')
    ]):
        return
    
    print("\n" + "=" * 50)
    print("INCLUDE/EXCLUDE SUMMARY")
    print("=" * 50)
    
    # Include cards impact
    include_cards = diagnostics.get('include_cards', [])
    if include_cards:
        print(f"\n✓ Must Include Cards ({len(include_cards)}):")
        
        include_added = diagnostics.get('include_added', [])
        if include_added:
            print(f"  ✓ Successfully Added ({len(include_added)}):")
            for card in include_added:
                print(f"    • {card}")
        
        missing_includes = diagnostics.get('missing_includes', [])
        if missing_includes:
            print(f"  ⚠ Could Not Include ({len(missing_includes)}):")
            for card in missing_includes:
                print(f"    • {card}")
    
    # Exclude cards impact
    exclude_cards = diagnostics.get('exclude_cards', [])
    if exclude_cards:
        print(f"\n✗ Must Exclude Cards ({len(exclude_cards)}):")
        
        excluded_removed = diagnostics.get('excluded_removed', [])
        if excluded_removed:
            print(f"  ✓ Successfully Excluded ({len(excluded_removed)}):")
            for card in excluded_removed:
                print(f"    • {card}")
        
        print("  Patterns:")
        for pattern in exclude_cards:
            print(f"    • {pattern}")
    
    # Validation issues
    issues = []
    fuzzy_corrections = diagnostics.get('fuzzy_corrections', {})
    if fuzzy_corrections:
        issues.append(f"Fuzzy Matched ({len(fuzzy_corrections)})")
        
    duplicates = diagnostics.get('duplicates_collapsed', {})
    if duplicates:
        issues.append(f"Duplicates Collapsed ({len(duplicates)})")
        
    illegal_dropped = diagnostics.get('illegal_dropped', [])
    if illegal_dropped:
        issues.append(f"Illegal Cards Dropped ({len(illegal_dropped)})")
    
    if issues:
        print("\n⚠ Validation Issues:")
        
        if fuzzy_corrections:
            print("  ⚡ Fuzzy Matched:")
            for original, corrected in fuzzy_corrections.items():
                print(f"    • {original} → {corrected}")
        
        if duplicates:
            print("  Duplicates Collapsed:")
            for card, count in duplicates.items():
                print(f"    • {card} ({count}x)")
        
        if illegal_dropped:
            print("  Illegal Cards Dropped:")
            for card in illegal_dropped:
                print(f"    • {card}")
    
    print("=" * 50)


def _apply_combined_commander_to_builder(builder: DeckBuilder, combined_commander: Any) -> None:
    """Attach combined commander metadata to the builder for downstream use."""

    try:
        builder.combined_commander = combined_commander
    except Exception:
        pass

    try:
        builder.partner_mode = combined_commander.partner_mode
    except Exception:
        pass

    try:
        builder.secondary_commander = combined_commander.secondary_name
    except Exception:
        pass

    try:
        builder.combined_color_identity = combined_commander.color_identity
        builder.combined_theme_tags = combined_commander.theme_tags
        builder.partner_warnings = combined_commander.warnings
    except Exception:
        pass

    commander_dict = getattr(builder, "commander_dict", None)
    if isinstance(commander_dict, dict):
        try:
            commander_dict["Partner Mode"] = combined_commander.partner_mode.value
            commander_dict["Secondary Commander"] = combined_commander.secondary_name
        except Exception:
            pass

def _export_outputs(builder: DeckBuilder) -> None:
    # M4: Print include/exclude summary to console
    _print_include_exclude_summary(builder)
    
    csv_path: Optional[str] = None
    try:
        csv_path = builder.export_decklist_csv() if hasattr(builder, "export_decklist_csv") else None
        # Persist for downstream reuse (e.g., random_entrypoint / reroll flows) so they don't re-export
        if csv_path:
            try:
                builder.last_csv_path = csv_path
            except Exception:
                pass
    except Exception:
        csv_path = None
    try:
        if hasattr(builder, "export_decklist_text"):
            if csv_path:
                base = os.path.splitext(os.path.basename(csv_path))[0]
                txt_generated: Optional[str] = None
                try:
                    txt_generated = builder.export_decklist_text(filename=base + ".txt")
                finally:
                    if txt_generated:
                        try:
                            builder.last_txt_path = txt_generated
                        except Exception:
                            pass
            else:
                txt_generated = None
                try:
                    txt_generated = builder.export_decklist_text()
                finally:
                    if txt_generated:
                        try:
                            builder.last_txt_path = txt_generated
                        except Exception:
                            pass
    except Exception:
        pass
    if _should_export_json_headless() and hasattr(builder, "export_run_config_json") and csv_path:
        try:
            base = os.path.splitext(os.path.basename(csv_path))[0]
            dest = os.getenv("DECK_CONFIG")
            if dest and dest.lower().endswith(".json"):
                out_dir, out_name = os.path.dirname(dest) or ".", os.path.basename(dest)
                os.makedirs(out_dir, exist_ok=True)
                builder.export_run_config_json(directory=out_dir, filename=out_name)
            else:
                out_dir = (dest if dest and os.path.isdir(dest) else "config")
                os.makedirs(out_dir, exist_ok=True)
                builder.export_run_config_json(directory=out_dir, filename=base + ".json")
        except Exception:
            pass

def _parse_bool(val: Optional[str | bool | int]) -> Optional[bool]:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return bool(val)
    s = str(val).strip().lower()
    if s in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "f", "no", "n", "off"}:
        return False
    return None


def _parse_bool_cli(val: str) -> bool:
    result = _parse_bool(val)
    if result is None:
        raise argparse.ArgumentTypeError(f"Expected a boolean value, received '{val}'")
    return result


def _parse_card_list(val: Optional[str]) -> List[str]:
    """Parse comma or semicolon-separated card list from CLI argument."""
    if not val:
        return []
    
    # Support semicolon separation for card names with commas
    if ';' in val:
        return [card.strip() for card in val.split(';') if card.strip()]
    
    # Use the intelligent parsing for comma-separated (handles card names with commas)
    try:
        from deck_builder.include_exclude_utils import parse_card_list_input
        return parse_card_list_input(val)
    except ImportError:
        # Fallback to simple comma split if import fails
        return [card.strip() for card in val.split(',') if card.strip()]


def _parse_opt_int(val: Optional[str | int]) -> Optional[int]:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    s = str(val).strip().lower()
    if s in {"", "none", "null", "nan"}:
        return None
    return int(s)


def _load_json_config(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("JSON config must be an object")
            return data
    except FileNotFoundError:
        raise


def _load_constraints_spec(spec: Any) -> Dict[str, Any]:
    """Load random constraints from a dict, JSON string, or file path."""

    if not spec:
        return {}
    if isinstance(spec, dict):
        return dict(spec)

    try:
        text = str(spec).strip()
    except Exception:
        return {}

    if not text:
        return {}

    # Treat existing file paths as JSON documents
    if os.path.isfile(text):
        try:
            with open(text, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                return loaded
        except Exception as exc:
            print(f"Warning: failed to load constraints from '{text}': {exc}")
        return {}

    # Fallback: parse inline JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception as exc:
        print(f"Warning: failed to parse inline constraints '{text}': {exc}")
    return {}


def _try_convert_seed(value: Any) -> Optional[int | str]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        text = str(value).strip()
    except Exception:
        return None
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return text


def _resolve_pathish_target(target: str, seed: Any) -> str:
    """Return a concrete file path for an output target, creating directories as needed."""

    if not target:
        raise ValueError("Empty output path provided")

    normalized = target.strip()
    if not normalized:
        raise ValueError("Blank output path provided")

    looks_dir = normalized.endswith(("/", "\\"))
    if os.path.isdir(normalized) or looks_dir:
        base_dir = normalized.rstrip("/\\") or "."
        os.makedirs(base_dir, exist_ok=True)
        seed_suffix = str(seed) if seed is not None else "latest"
        filename = f"random_build_{seed_suffix}.json"
        return os.path.join(base_dir, filename)

    base_dir = os.path.dirname(normalized)
    if base_dir:
        os.makedirs(base_dir, exist_ok=True)
    return normalized


def _resolve_random_bool(
    cli_value: Optional[bool],
    env_name: str,
    random_section: Dict[str, Any],
    json_key: str,
    default: Optional[bool],
) -> Optional[bool]:
    if cli_value is not None:
        return bool(cli_value)
    env_val = os.getenv(env_name)
    result = _parse_bool(env_val) if env_val is not None else None
    if result is not None:
        return result
    if json_key in random_section:
        result = _parse_bool(random_section.get(json_key))
        if result is not None:
            return result
    return default


def _resolve_random_str(
    cli_value: Optional[str],
    env_name: str,
    random_section: Dict[str, Any],
    json_key: str,
    default: Optional[str] = None,
) -> Optional[str]:
    candidates: Tuple[Any, ...] = (
        cli_value,
        os.getenv(env_name),
        random_section.get(json_key),
        default,
    )
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            text = str(candidate).strip()
        except Exception:
            continue
        if text:
            return text
    return None


def _resolve_random_int(
    cli_value: Optional[int],
    env_name: str,
    random_section: Dict[str, Any],
    json_key: str,
    default: int,
) -> int:
    if cli_value is not None:
        try:
            return int(cli_value)
        except Exception:
            pass

    env_val = os.getenv(env_name)
    if env_val is not None and str(env_val).strip() != "":
        try:
            return int(float(str(env_val).strip()))
        except Exception:
            pass

    if json_key in random_section:
        value = random_section.get(json_key)
        try:
            if isinstance(value, str):
                value = value.strip()
                if value:
                    return int(float(value))
            elif value is not None:
                return int(value)
        except Exception:
            pass
    return default


def _resolve_random_seed(cli_value: Optional[str], random_section: Dict[str, Any]) -> Optional[int | str]:
    seed = _try_convert_seed(cli_value)
    if seed is not None:
        return seed
    seed = _try_convert_seed(os.getenv("RANDOM_SEED"))
    if seed is not None:
        return seed
    return _try_convert_seed(random_section.get("seed"))


def _extract_random_section(json_cfg: Dict[str, Any]) -> Dict[str, Any]:
    section = json_cfg.get("random")
    if isinstance(section, dict):
        return dict(section)
    alt = json_cfg.get("random_config")
    if isinstance(alt, dict):
        return dict(alt)
    return {}


def _should_run_random_mode(args: argparse.Namespace, json_cfg: Dict[str, Any], random_section: Dict[str, Any]) -> bool:
    if getattr(args, "random_mode", False):
        return True
    if _parse_bool(os.getenv("HEADLESS_RANDOM_MODE")):
        return True
    if (os.getenv("DECK_MODE") or "").strip().lower() == "random":
        return True
    if _parse_bool(json_cfg.get("random_mode")):
        return True
    if _parse_bool(random_section.get("enabled")):
        return True

    # Detect CLI or env hints that imply random mode even without explicit flag
    cli_indicators = (
        getattr(args, "random_theme", None),
        getattr(args, "random_primary_theme", None),
        getattr(args, "random_secondary_theme", None),
        getattr(args, "random_tertiary_theme", None),
        getattr(args, "random_seed", None),
        getattr(args, "random_auto_fill", None),
        getattr(args, "random_auto_fill_secondary", None),
        getattr(args, "random_auto_fill_tertiary", None),
        getattr(args, "random_strict_theme_match", None),
        getattr(args, "random_attempts", None),
        getattr(args, "random_timeout_ms", None),
        getattr(args, "random_constraints", None),
        getattr(args, "random_output_json", None),
    )
    if any(value is not None for value in cli_indicators):
        return True

    for env_name in (
        "RANDOM_THEME",
        "RANDOM_PRIMARY_THEME",
        "RANDOM_SECONDARY_THEME",
        "RANDOM_TERTIARY_THEME",
        "RANDOM_CONSTRAINTS",
        "RANDOM_CONSTRAINTS_PATH",
        "RANDOM_OUTPUT_JSON",
    ):
        if os.getenv(env_name):
            return True

    noteworthy_keys = (
        "theme",
        "primary_theme",
        "secondary_theme",
        "tertiary_theme",
        "seed",
        "auto_fill",
        "auto_fill_secondary",
        "auto_fill_tertiary",
        "strict_theme_match",
        "attempts",
        "timeout_ms",
        "constraints",
        "constraints_path",
        "output_json",
    )
    if any(random_section.get(key) for key in noteworthy_keys):
        return True

    return False


def _resolve_random_config(args: argparse.Namespace, json_cfg: Dict[str, Any]) -> Tuple[RandomRunConfig, Dict[str, Any]]:
    random_section = _extract_random_section(json_cfg)
    cfg = RandomRunConfig()

    cfg.legacy_theme = _resolve_random_str(
        getattr(args, "random_theme", None),
        "RANDOM_THEME",
        random_section,
        "theme",
        None,
    )
    cfg.primary_theme = _resolve_random_str(
        getattr(args, "random_primary_theme", None),
        "RANDOM_PRIMARY_THEME",
        random_section,
        "primary_theme",
        cfg.legacy_theme,
    )
    cfg.secondary_theme = _resolve_random_str(
        getattr(args, "random_secondary_theme", None),
        "RANDOM_SECONDARY_THEME",
        random_section,
        "secondary_theme",
        None,
    )
    cfg.tertiary_theme = _resolve_random_str(
        getattr(args, "random_tertiary_theme", None),
        "RANDOM_TERTIARY_THEME",
        random_section,
        "tertiary_theme",
        None,
    )

    auto_fill_flag = _resolve_random_bool(
        getattr(args, "random_auto_fill", None),
        "RANDOM_AUTO_FILL",
        random_section,
        "auto_fill",
        False,
    )
    cfg.auto_fill_missing = bool(auto_fill_flag)
    cfg.auto_fill_secondary = _resolve_random_bool(
        getattr(args, "random_auto_fill_secondary", None),
        "RANDOM_AUTO_FILL_SECONDARY",
        random_section,
        "auto_fill_secondary",
        None,
    )
    cfg.auto_fill_tertiary = _resolve_random_bool(
        getattr(args, "random_auto_fill_tertiary", None),
        "RANDOM_AUTO_FILL_TERTIARY",
        random_section,
        "auto_fill_tertiary",
        None,
    )

    cfg.strict_theme_match = bool(
        _resolve_random_bool(
            getattr(args, "random_strict_theme_match", None),
            "RANDOM_STRICT_THEME_MATCH",
            random_section,
            "strict_theme_match",
            False,
        )
    )

    cfg.attempts = max(
        1,
        _resolve_random_int(
            getattr(args, "random_attempts", None),
            "RANDOM_MAX_ATTEMPTS",
            random_section,
            "attempts",
            5,
        ),
    )
    cfg.timeout_ms = max(
        100,
        _resolve_random_int(
            getattr(args, "random_timeout_ms", None),
            "RANDOM_TIMEOUT_MS",
            random_section,
            "timeout_ms",
            5000,
        ),
    )

    cfg.seed = _resolve_random_seed(getattr(args, "random_seed", None), random_section)

    # Resolve constraints in precedence order: CLI > env JSON > env path > config dict > config path
    constraints_candidates: Tuple[Any, ...] = (
        getattr(args, "random_constraints", None),
        os.getenv("RANDOM_CONSTRAINTS"),
        os.getenv("RANDOM_CONSTRAINTS_PATH"),
        random_section.get("constraints"),
        random_section.get("constraints_path"),
    )
    for candidate in constraints_candidates:
        loaded = _load_constraints_spec(candidate)
        if loaded:
            cfg.constraints = loaded
            break

    cfg.output_json = _resolve_random_str(
        getattr(args, "random_output_json", None),
        "RANDOM_OUTPUT_JSON",
        random_section,
        "output_json",
        None,
    )

    if cfg.primary_theme is None:
        cfg.primary_theme = cfg.legacy_theme
    if cfg.primary_theme and not cfg.legacy_theme:
        cfg.legacy_theme = cfg.primary_theme

    if cfg.auto_fill_missing:
        if cfg.auto_fill_secondary is None:
            cfg.auto_fill_secondary = True
        if cfg.auto_fill_tertiary is None:
            cfg.auto_fill_tertiary = True

    return cfg, random_section


def _print_random_summary(result: Any, config: RandomRunConfig) -> None:
    print("\n" + "=" * 60)
    print("RANDOM MODE BUILD")
    print("=" * 60)
    commander = getattr(result, "commander", None) or "(unknown)"
    print(f"Commander       : {commander}")
    seed_value = getattr(result, "seed", config.seed)
    print(f"Seed            : {seed_value}")

    display_themes = list(getattr(result, "display_themes", []) or [])
    if not display_themes:
        primary = getattr(result, "primary_theme", config.primary_theme)
        if primary:
            display_themes.append(primary)
        for extra in (
            getattr(result, "secondary_theme", config.secondary_theme),
            getattr(result, "tertiary_theme", config.tertiary_theme),
        ):
            if extra:
                display_themes.append(extra)
    if display_themes:
        print(f"Themes          : {', '.join(display_themes)}")
    else:
        print("Themes          : (none)")

    fallback_kinds: List[str] = []
    if getattr(result, "combo_fallback", False):
        fallback_kinds.append("combo")
    if getattr(result, "synergy_fallback", False):
        fallback_kinds.append("synergy")
    fallback_reason = getattr(result, "fallback_reason", None)
    print(f"Fallback        : {('/'.join(fallback_kinds)) if fallback_kinds else 'none'}")
    if fallback_reason:
        print(f"Fallback reason : {fallback_reason}")

    auto_secondary = getattr(result, "auto_fill_secondary_enabled", config.auto_fill_secondary or False)
    auto_tertiary = getattr(result, "auto_fill_tertiary_enabled", config.auto_fill_tertiary or False)
    print(
        "Auto-fill       : secondary={} | tertiary={}".format(
            "on" if auto_secondary else "off",
            "on" if auto_tertiary else "off",
        )
    )
    print(f"Strict match    : {'on' if config.strict_theme_match else 'off'}")

    attempts_used = getattr(result, "attempts_tried", None)
    if attempts_used is None:
        attempts_used = config.attempts
    print(f"Attempts used   : {attempts_used} / {config.attempts}")
    timeout_hit = getattr(result, "timeout_hit", False)
    print(f"Timeout (ms)    : {config.timeout_ms} (timeout_hit={timeout_hit})")

    if config.constraints:
        try:
            print("Constraints     :")
            print(json.dumps(config.constraints, indent=2))
        except Exception:
            print(f"Constraints     : {config.constraints}")

    csv_path = getattr(result, "csv_path", None)
    if csv_path:
        print(f"Deck CSV        : {csv_path}")
    txt_path = getattr(result, "txt_path", None)
    if txt_path:
        print(f"Deck TXT        : {txt_path}")
    compliance = getattr(result, "compliance", None)
    if compliance:
        if isinstance(compliance, dict) and compliance.get("path"):
            print(f"Compliance JSON : {compliance['path']}")
        else:
            try:
                print("Compliance data :")
                print(json.dumps(compliance, indent=2))
            except Exception:
                print(f"Compliance data : {compliance}")

    summary = getattr(result, "summary", None)
    if summary:
        try:
            rendered = json.dumps(summary, indent=2)
        except Exception:
            rendered = str(summary)
        preview = rendered[:1000]
        print("Summary preview :")
        print(preview + ("..." if len(rendered) > len(preview) else ""))

    decklist = getattr(result, "decklist", None)
    if decklist:
        try:
            print(f"Decklist cards  : {len(decklist)}")
        except Exception:
            pass

    print("=" * 60)


def _write_random_payload(config: RandomRunConfig, result: Any) -> None:
    if not config.output_json:
        return
    try:
        path = _resolve_pathish_target(config.output_json, getattr(result, "seed", config.seed))
    except Exception as exc:
        print(f"Warning: unable to resolve random output path '{config.output_json}': {exc}")
        return

    seed_value = getattr(result, "seed", config.seed)
    try:
        normalized_seed = int(seed_value) if seed_value is not None else None
    except Exception:
        normalized_seed = seed_value

    payload: Dict[str, Any] = {
        "seed": normalized_seed,
        "commander": getattr(result, "commander", None),
        "themes": {
            "primary": getattr(result, "primary_theme", config.primary_theme),
            "secondary": getattr(result, "secondary_theme", config.secondary_theme),
            "tertiary": getattr(result, "tertiary_theme", config.tertiary_theme),
            "resolved": list(getattr(result, "resolved_themes", []) or []),
            "display": list(getattr(result, "display_themes", []) or []),
            "auto_filled": list(getattr(result, "auto_filled_themes", []) or []),
        },
        "strict_theme_match": bool(config.strict_theme_match),
        "auto_fill": {
            "missing": bool(config.auto_fill_missing),
            "secondary": bool(getattr(result, "auto_fill_secondary_enabled", config.auto_fill_secondary or False)),
            "tertiary": bool(getattr(result, "auto_fill_tertiary_enabled", config.auto_fill_tertiary or False)),
            "applied": bool(getattr(result, "auto_fill_applied", False)),
        },
        "attempts": {
            "configured": config.attempts,
            "used": int(getattr(result, "attempts_tried", config.attempts) or config.attempts),
            "timeout_ms": config.timeout_ms,
            "timeout_hit": bool(getattr(result, "timeout_hit", False)),
            "retries_exhausted": bool(getattr(result, "retries_exhausted", False)),
        },
        "fallback": {
            "combo": bool(getattr(result, "combo_fallback", False)),
            "synergy": bool(getattr(result, "synergy_fallback", False)),
            "reason": getattr(result, "fallback_reason", None),
        },
        "constraints": config.constraints,
        "csv_path": getattr(result, "csv_path", None),
        "txt_path": getattr(result, "txt_path", None),
        "compliance": getattr(result, "compliance", None),
        "summary": getattr(result, "summary", None),
        "decklist": getattr(result, "decklist", None),
    }

    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print(f"Random build payload written to {path}")
    except Exception as exc:
        print(f"Warning: failed to write random payload '{path}': {exc}")


def _run_random_mode(config: RandomRunConfig) -> int:
    try:
        from deck_builder.random_entrypoint import (
            RandomConstraintsImpossibleError,
            RandomThemeNoMatchError,
            build_random_full_deck,
        )
    except Exception as exc:
        print(f"Random mode unavailable: {exc}")
        return 1

    timeout_ms = max(100, int(config.timeout_ms))
    attempts = max(1, int(config.attempts))

    try:
        result = build_random_full_deck(
            theme=config.legacy_theme,
            constraints=config.constraints or None,
            seed=config.seed,
            attempts=attempts,
            timeout_s=float(timeout_ms) / 1000.0,
            primary_theme=config.primary_theme,
            secondary_theme=config.secondary_theme,
            tertiary_theme=config.tertiary_theme,
            auto_fill_missing=config.auto_fill_missing,
            auto_fill_secondary=config.auto_fill_secondary,
            auto_fill_tertiary=config.auto_fill_tertiary,
            strict_theme_match=config.strict_theme_match,
        )
    except RandomThemeNoMatchError as exc:
        print(f"Random mode failed: strict theme match produced no results ({exc})")
        return 3
    except RandomConstraintsImpossibleError as exc:
        print(f"Random mode constraints impossible: {exc}")
        return 4
    except Exception as exc:
        print(f"Random mode encountered an unexpected error: {exc}")
        return 1

    _print_random_summary(result, config)
    _write_random_payload(config, result)
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Headless deck builder runner")
    p.add_argument("--config", metavar="PATH", default=os.getenv("DECK_CONFIG"), 
                   help="Path to JSON config file (string)")
    p.add_argument("--commander", metavar="NAME", default=None,
                   help="Commander name to search for (string)")
    p.add_argument("--secondary-commander", metavar="NAME", default=None,
                   help="Secondary commander name when using Partner/Partner With mechanics")
    p.add_argument("--background", metavar="NAME", default=None,
                   help="Background card name when choosing a Background")
    p.add_argument("--enable-partner-mechanics", metavar="BOOL", type=_parse_bool_cli, default=None,
                   help="Enable partner/background mechanics for this run (bool: true/false/1/0)")
    p.add_argument("--primary-choice", metavar="INT", type=int, default=None,
                   help="Primary theme tag choice number (integer)")
    p.add_argument("--secondary-choice", metavar="INT", type=_parse_opt_int, default=None,
                   help="Secondary theme tag choice number (integer, optional)")
    p.add_argument("--tertiary-choice", metavar="INT", type=_parse_opt_int, default=None,
                   help="Tertiary theme tag choice number (integer, optional)")
    p.add_argument("--primary-tag", metavar="NAME", default=None,
                   help="Primary theme tag name (string, alternative to --primary-choice)")
    p.add_argument("--secondary-tag", metavar="NAME", default=None,
                   help="Secondary theme tag name (string, alternative to --secondary-choice)")
    p.add_argument("--tertiary-tag", metavar="NAME", default=None,
                   help="Tertiary theme tag name (string, alternative to --tertiary-choice)")
    p.add_argument("--bracket-level", metavar="1-5", type=int, default=None,
                   help="Power bracket level 1-5 (integer)")
    
    # Ideal count arguments - new feature!
    ideal_group = p.add_argument_group("Ideal Deck Composition", 
                                     "Override default target counts for deck categories")
    ideal_group.add_argument("--ramp-count", metavar="INT", type=int, default=None,
                           help="Target number of ramp spells (integer, default: 8)")
    ideal_group.add_argument("--land-count", metavar="INT", type=int, default=None,
                           help="Target total number of lands (integer, default: 35)")
    ideal_group.add_argument("--basic-land-count", metavar="INT", type=int, default=None,
                           help="Minimum number of basic lands (integer, default: 15)")
    ideal_group.add_argument("--creature-count", metavar="INT", type=int, default=None,
                           help="Target number of creatures (integer, default: 25)")
    ideal_group.add_argument("--removal-count", metavar="INT", type=int, default=None,
                           help="Target number of spot removal spells (integer, default: 10)")
    ideal_group.add_argument("--wipe-count", metavar="INT", type=int, default=None,
                           help="Target number of board wipes (integer, default: 2)")
    ideal_group.add_argument("--card-advantage-count", metavar="INT", type=int, default=None,
                           help="Target number of card advantage pieces (integer, default: 10)")
    ideal_group.add_argument("--protection-count", metavar="INT", type=int, default=None,
                           help="Target number of protection spells (integer, default: 8)")
    
    # Land-specific counts
    land_group = p.add_argument_group("Land Configuration", 
                                    "Control specific land type counts and options")
    land_group.add_argument("--add-lands", metavar="BOOL", type=_parse_bool, default=None,
                          help="Whether to add lands (bool: true/false/1/0)")
    land_group.add_argument("--fetch-count", metavar="INT", type=_parse_opt_int, default=None,
                          help="Number of fetch lands to include (integer, optional)")
    land_group.add_argument("--dual-count", metavar="INT", type=_parse_opt_int, default=None,
                          help="Number of dual lands to include (integer, optional)")
    land_group.add_argument("--triple-count", metavar="INT", type=_parse_opt_int, default=None,
                          help="Number of triple lands to include (integer, optional)")
    land_group.add_argument("--utility-count", metavar="INT", type=_parse_opt_int, default=None,
                          help="Number of utility lands to include (integer, optional)")
    
    # Card type toggles
    toggle_group = p.add_argument_group("Card Type Toggles", 
                                      "Enable/disable adding specific card types")
    toggle_group.add_argument("--add-creatures", metavar="BOOL", type=_parse_bool, default=None,
                            help="Add creatures to deck (bool: true/false/1/0)")
    toggle_group.add_argument("--add-non-creature-spells", metavar="BOOL", type=_parse_bool, default=None,
                            help="Add non-creature spells to deck (bool: true/false/1/0)")
    toggle_group.add_argument("--add-ramp", metavar="BOOL", type=_parse_bool, default=None,
                            help="Add ramp spells to deck (bool: true/false/1/0)")
    toggle_group.add_argument("--add-removal", metavar="BOOL", type=_parse_bool, default=None,
                            help="Add removal spells to deck (bool: true/false/1/0)")
    toggle_group.add_argument("--add-wipes", metavar="BOOL", type=_parse_bool, default=None,
                            help="Add board wipes to deck (bool: true/false/1/0)")
    toggle_group.add_argument("--add-card-advantage", metavar="BOOL", type=_parse_bool, default=None,
                            help="Add card advantage pieces to deck (bool: true/false/1/0)")
    toggle_group.add_argument("--add-protection", metavar="BOOL", type=_parse_bool, default=None,
                            help="Add protection spells to deck (bool: true/false/1/0)")
    
    # Include/Exclude configuration
    include_group = p.add_argument_group("Include/Exclude Cards", 
                                       "Force include or exclude specific cards")
    include_group.add_argument("--include-cards", metavar="CARDS", 
                             help='Cards to force include (string: comma-separated, max 10). For cards with commas in names like "Krenko, Mob Boss", use semicolons or JSON config.')
    include_group.add_argument("--exclude-cards", metavar="CARDS", 
                             help='Cards to exclude from deck (string: comma-separated, max 15). For cards with commas in names like "Krenko, Mob Boss", use semicolons or JSON config.')
    include_group.add_argument("--enforcement-mode", metavar="MODE", choices=["warn", "strict"], default=None, 
                             help="How to handle missing includes (string: warn=continue, strict=abort)")
    include_group.add_argument("--allow-illegal", metavar="BOOL", type=_parse_bool, default=None,
                             help="Allow illegal cards in includes/excludes (bool: true/false/1/0)")
    include_group.add_argument("--fuzzy-matching", metavar="BOOL", type=_parse_bool, default=None,
                             help="Enable fuzzy card name matching (bool: true/false/1/0)")
    
    theme_group = p.add_argument_group(
        "Additional Themes",
        "Supplement commander themes with catalog-backed user inputs",
    )
    theme_group.add_argument(
        "--additional-themes",
        metavar="THEMES",
    type=parse_theme_list,
        default=None,
        help="Additional theme names (comma or semicolon separated)",
    )
    theme_group.add_argument(
        "--theme-match-mode",
        metavar="MODE",
        choices=["strict", "permissive"],
        default=None,
        help="Theme resolution strategy (strict requires all matches)",
    )
    theme_group.add_argument(
        "--user-theme-weight",
        metavar="FLOAT",
        type=float,
        default=None,
        help="Weight multiplier applied to supplemental themes (default 1.0)",
    )

    # Random mode configuration (parity with web random builder)
    random_group = p.add_argument_group(
        "Random Mode",
        "Generate decks using the random web builder flow",
    )
    random_group.add_argument(
        "--random-mode",
        action="store_true",
        help="Force random-mode build even if other inputs are provided",
    )
    random_group.add_argument(
        "--random-theme",
        metavar="THEME",
        default=None,
        help="Legacy random theme (maps to primary theme if unspecified)",
    )
    random_group.add_argument(
        "--random-primary-theme",
        metavar="THEME",
        default=None,
        help="Primary theme slug for random mode",
    )
    random_group.add_argument(
        "--random-secondary-theme",
        metavar="THEME",
        default=None,
        help="Secondary theme slug for random mode",
    )
    random_group.add_argument(
        "--random-tertiary-theme",
        metavar="THEME",
        default=None,
        help="Tertiary theme slug for random mode",
    )
    random_group.add_argument(
        "--random-auto-fill",
        metavar="BOOL",
        type=_parse_bool,
        default=None,
        help="Enable auto-fill assistance for missing theme slots",
    )
    random_group.add_argument(
        "--random-auto-fill-secondary",
        metavar="BOOL",
        type=_parse_bool,
        default=None,
        help="Enable auto-fill specifically for secondary theme",
    )
    random_group.add_argument(
        "--random-auto-fill-tertiary",
        metavar="BOOL",
        type=_parse_bool,
        default=None,
        help="Enable auto-fill specifically for tertiary theme",
    )
    random_group.add_argument(
        "--random-strict-theme-match",
        metavar="BOOL",
        type=_parse_bool,
        default=None,
        help="Require strict theme matches when selecting commanders",
    )
    random_group.add_argument(
        "--random-attempts",
        metavar="INT",
        type=int,
        default=None,
        help="Maximum attempts before giving up (default 5)",
    )
    random_group.add_argument(
        "--random-timeout-ms",
        metavar="INT",
        type=int,
        default=None,
        help="Timeout in milliseconds for theme search (default 5000)",
    )
    random_group.add_argument(
        "--random-seed",
        metavar="SEED",
        default=None,
        help="Seed value for deterministic random builds",
    )
    random_group.add_argument(
        "--random-constraints",
        metavar="JSON_OR_PATH",
        default=None,
        help="Random constraints as JSON or a path to a JSON file",
    )
    random_group.add_argument(
        "--random-output-json",
        metavar="PATH",
        default=None,
        help="Write random build payload JSON to PATH (directory or file)",
    )

    # Utility
    p.add_argument("--dry-run", action="store_true", 
                   help="Print resolved configuration and exit without building")
    return p


def _resolve_value(
    cli: Optional[Any], env_name: str, json_data: Dict[str, Any], json_key: str, default: Any
) -> Any:
    if cli is not None:
        return cli
    env_val = os.getenv(env_name)
    if env_val is not None:
        # Convert types based on default type
        if isinstance(default, bool):
            b = _parse_bool(env_val)
            return default if b is None else b
        if isinstance(default, int) or default is None:
            # allow optional ints
            try:
                return _parse_opt_int(env_val)
            except ValueError:
                return default
        return env_val
    if json_key in json_data:
        return json_data[json_key]
    return default


def _resolve_string_option(
    cli_value: Optional[str], env_name: str, json_data: Dict[str, Any], json_key: str
) -> Optional[str]:
    if cli_value is not None:
        text = str(cli_value).strip()
        return text or None

    env_val = os.getenv(env_name)
    if env_val:
        text = env_val.strip()
        if text:
            return text

    raw = json_data.get(json_key)
    if raw is not None:
        text = str(raw).strip()
        if text:
            return text
    return None


def _resolve_bool_option(
    cli_value: Optional[bool], env_name: str, json_data: Dict[str, Any], json_key: str
) -> Optional[bool]:
    if cli_value is not None:
        return bool(cli_value)

    env_val = os.getenv(env_name)
    if env_val is not None:
        parsed = _parse_bool(env_val)
        if parsed is not None:
            return parsed

    raw = json_data.get(json_key)
    if raw is not None:
        if isinstance(raw, bool):
            return raw
        parsed = _parse_bool(str(raw))
        if parsed is not None:
            return parsed
    return None


def _main() -> int:
    _ensure_data_ready()
    parser = _build_arg_parser()
    args = parser.parse_args()
    # Optional config discovery (no prompts)
    cfg_path = args.config
    json_cfg: Dict[str, Any] = {}
    if cfg_path and os.path.isfile(cfg_path):
        json_cfg = _load_json_config(cfg_path)
    else:
        # No explicit file; if exactly one config exists in a known dir, use it
        for candidate_dir in [cfg_path] if cfg_path and os.path.isdir(cfg_path) else ["/app/config", "config"]:
            try:
                files = [f for f in (os.listdir(candidate_dir) if os.path.isdir(candidate_dir) else []) if f.lower().endswith(".json")]
            except Exception:
                files = []
            if len(files) == 1:
                chosen = os.path.join(candidate_dir, files[0])
                json_cfg = _load_json_config(chosen)
                os.environ["DECK_CONFIG"] = chosen
                break

    random_config, random_section = _resolve_random_config(args, json_cfg)
    if _should_run_random_mode(args, json_cfg, random_section):
        if args.dry_run:
            print(json.dumps({"random_mode": True, "config": asdict(random_config)}, indent=2))
            return 0
        return _run_random_mode(random_config)

    # Defaults mirror run() signature
    defaults = dict(
        command_name="",
        add_creatures=True,
        add_non_creature_spells=True,
        add_ramp=True,
        add_removal=True,
        add_wipes=True,
        add_card_advantage=True,
        add_protection=True,
        primary_choice=1,
        secondary_choice=None,
        tertiary_choice=None,
        add_lands=True,
        fetch_count=3,
        dual_count=None,
        triple_count=None,
        utility_count=None,
    )

    # Pull optional ideal_counts from JSON if present
    ideal_counts_json = {}
    try:
        if isinstance(json_cfg.get("ideal_counts"), dict):
            ideal_counts_json = json_cfg["ideal_counts"]
    except Exception:
        ideal_counts_json = {}

    # Build ideal_counts dict from CLI args, JSON, or defaults
    ideal_counts_resolved = {}
    ideal_mappings = [
        ("ramp_count", "ramp", 8),
        ("land_count", "lands", 35), 
        ("basic_land_count", "basic_lands", 15),
        ("creature_count", "creatures", 25),
        ("removal_count", "removal", 10),
        ("wipe_count", "wipes", 2),
        ("card_advantage_count", "card_advantage", 10),
        ("protection_count", "protection", 8),
    ]
    
    for cli_key, json_key, default_val in ideal_mappings:
        cli_val = getattr(args, cli_key, None)
        if cli_val is not None:
            ideal_counts_resolved[json_key] = cli_val
        elif json_key in ideal_counts_json:
            ideal_counts_resolved[json_key] = ideal_counts_json[json_key]
        # Don't set defaults here - let the builder use its own defaults

    # Pull include/exclude configuration from JSON (M1: Config + Validation + Persistence)
    include_cards_json = []
    exclude_cards_json = []
    try:
        if isinstance(json_cfg.get("include_cards"), list):
            include_cards_json = [str(x) for x in json_cfg["include_cards"] if x]
        if isinstance(json_cfg.get("exclude_cards"), list):
            exclude_cards_json = [str(x) for x in json_cfg["exclude_cards"] if x]
    except Exception:
        pass

    # M4: Parse CLI include/exclude card lists
    cli_include_cards = _parse_card_list(args.include_cards) if hasattr(args, 'include_cards') else []
    cli_exclude_cards = _parse_card_list(args.exclude_cards) if hasattr(args, 'exclude_cards') else []

    # Resolve tag names to indices BEFORE building resolved dict (so they can override defaults)
    resolved_primary_choice = args.primary_choice
    resolved_secondary_choice = args.secondary_choice  
    resolved_tertiary_choice = args.tertiary_choice
    primary_tag_name: Optional[str] = None
    secondary_tag_name: Optional[str] = None
    tertiary_tag_name: Optional[str] = None
    
    try:
        # Collect tag names from CLI, JSON, and environment (CLI takes precedence)
        primary_tag_name = (
            args.primary_tag or 
            (str(os.getenv("DECK_PRIMARY_TAG") or "").strip()) or 
            str(json_cfg.get("primary_tag", "")).strip()
        )
        secondary_tag_name = (
            args.secondary_tag or 
            (str(os.getenv("DECK_SECONDARY_TAG") or "").strip()) or 
            str(json_cfg.get("secondary_tag", "")).strip()
        )
        tertiary_tag_name = (
            args.tertiary_tag or 
            (str(os.getenv("DECK_TERTIARY_TAG") or "").strip()) or 
            str(json_cfg.get("tertiary_tag", "")).strip()
        )
        
        tag_names = [t for t in [primary_tag_name, secondary_tag_name, tertiary_tag_name] if t]
        if tag_names:
            # Load commander name to resolve tags
            commander_name = _resolve_value(args.commander, "DECK_COMMANDER", json_cfg, "commander", "")
            if commander_name:
                try:
                    # Load commander tags to compute indices
                    tmp = DeckBuilder()
                    df = tmp.load_commander_data()
                    row = df[df["name"] == commander_name]
                    if not row.empty:
                        original = list(dict.fromkeys(row.iloc[0].get("themeTags", []) or []))
                        
                        # Step 1: primary from original
                        if primary_tag_name:
                            for i, t in enumerate(original, start=1):
                                if str(t).strip().lower() == primary_tag_name.strip().lower():
                                    resolved_primary_choice = i
                                    break
                        
                        # Step 2: secondary from remaining after primary
                        if secondary_tag_name:
                            if resolved_primary_choice is not None:
                                # Create remaining list after removing primary choice
                                remaining_1 = [t for j, t in enumerate(original, start=1) if j != resolved_primary_choice]
                                for i2, t in enumerate(remaining_1, start=1):
                                    if str(t).strip().lower() == secondary_tag_name.strip().lower():
                                        resolved_secondary_choice = i2
                                        break
                            else:
                                # If no primary set, secondary maps directly to original list
                                for i, t in enumerate(original, start=1):
                                    if str(t).strip().lower() == secondary_tag_name.strip().lower():
                                        resolved_secondary_choice = i
                                        break
                        
                        # Step 3: tertiary from remaining after primary+secondary
                        if tertiary_tag_name:
                            if resolved_primary_choice is not None and resolved_secondary_choice is not None:
                                # reconstruct remaining after removing primary then secondary as displayed
                                remaining_1 = [t for j, t in enumerate(original, start=1) if j != resolved_primary_choice]
                                remaining_2 = [t for j, t in enumerate(remaining_1, start=1) if j != resolved_secondary_choice]
                                for i3, t in enumerate(remaining_2, start=1):
                                    if str(t).strip().lower() == tertiary_tag_name.strip().lower():
                                        resolved_tertiary_choice = i3
                                        break
                            elif resolved_primary_choice is not None:
                                # Only primary set, tertiary from remaining after primary
                                remaining_1 = [t for j, t in enumerate(original, start=1) if j != resolved_primary_choice]
                                for i, t in enumerate(remaining_1, start=1):
                                    if str(t).strip().lower() == tertiary_tag_name.strip().lower():
                                        resolved_tertiary_choice = i
                                        break
                            else:
                                # No primary or secondary set, tertiary maps directly to original list
                                for i, t in enumerate(original, start=1):
                                    if str(t).strip().lower() == tertiary_tag_name.strip().lower():
                                        resolved_tertiary_choice = i
                                        break
                except Exception:
                    pass
    except Exception:
        pass

    additional_themes_json: List[str] = []
    try:
        collected: List[str] = []
        for key in ("additional_themes", "userThemes"):
            raw_value = json_cfg.get(key)
            if isinstance(raw_value, list):
                collected.extend(raw_value)
        if collected:
            additional_themes_json = clean_theme_inputs(collected)
    except Exception:
        additional_themes_json = []

    cli_additional_themes: List[str] = []
    if hasattr(args, "additional_themes") and args.additional_themes:
        if isinstance(args.additional_themes, list):
            cli_additional_themes = clean_theme_inputs(args.additional_themes)
        else:
            cli_additional_themes = parse_theme_list(str(args.additional_themes))

    env_additional_themes = parse_theme_list(os.getenv("DECK_ADDITIONAL_THEMES"))

    additional_theme_inputs = (
        cli_additional_themes
        or env_additional_themes
        or additional_themes_json
    )

    theme_mode_value = getattr(args, "theme_match_mode", None)
    if not theme_mode_value:
        theme_mode_value = os.getenv("THEME_MATCH_MODE")
    if not theme_mode_value:
        theme_mode_value = json_cfg.get("theme_match_mode") or json_cfg.get("themeMatchMode")
    normalized_theme_mode = normalize_theme_match_mode(theme_mode_value)

    weight_value: Optional[float]
    if hasattr(args, "user_theme_weight") and args.user_theme_weight is not None:
        weight_value = args.user_theme_weight
    else:
        cfg_weight = json_cfg.get("user_theme_weight")
        if cfg_weight is not None:
            try:
                weight_value = float(cfg_weight)
            except Exception:
                weight_value = None
        else:
            weight_value = None

    commander_tag_names = [
        str(tag)
        for tag in (primary_tag_name, secondary_tag_name, tertiary_tag_name)
        if isinstance(tag, str) and tag and str(tag).strip()
    ]

    try:
        theme_resolution = resolve_additional_theme_inputs(
            additional_theme_inputs,
            normalized_theme_mode,
            commander_tags=commander_tag_names,
        )
    except ValueError as exc:
        print(str(exc))
        return 2

    resolved_secondary_commander = _resolve_string_option(
        getattr(args, "secondary_commander", None),
        "DECK_SECONDARY_COMMANDER",
        json_cfg,
        "secondary_commander",
    )
    resolved_background = _resolve_string_option(
        getattr(args, "background", None),
        "DECK_BACKGROUND",
        json_cfg,
        "background",
    )
    resolved_partner_flag = _resolve_bool_option(
        getattr(args, "enable_partner_mechanics", None),
        "ENABLE_PARTNER_MECHANICS",
        json_cfg,
        "enable_partner_mechanics",
    )

    resolved = {
        "command_name": _resolve_value(args.commander, "DECK_COMMANDER", json_cfg, "commander", defaults["command_name"]),
        "add_creatures": _resolve_value(args.add_creatures, "DECK_ADD_CREATURES", json_cfg, "add_creatures", defaults["add_creatures"]),
        "add_non_creature_spells": _resolve_value(args.add_non_creature_spells, "DECK_ADD_NON_CREATURE_SPELLS", json_cfg, "add_non_creature_spells", defaults["add_non_creature_spells"]),
        "add_ramp": _resolve_value(args.add_ramp, "DECK_ADD_RAMP", json_cfg, "add_ramp", defaults["add_ramp"]),
        "add_removal": _resolve_value(args.add_removal, "DECK_ADD_REMOVAL", json_cfg, "add_removal", defaults["add_removal"]),
        "add_wipes": _resolve_value(args.add_wipes, "DECK_ADD_WIPES", json_cfg, "add_wipes", defaults["add_wipes"]),
        "add_card_advantage": _resolve_value(args.add_card_advantage, "DECK_ADD_CARD_ADVANTAGE", json_cfg, "add_card_advantage", defaults["add_card_advantage"]),
        "add_protection": _resolve_value(args.add_protection, "DECK_ADD_PROTECTION", json_cfg, "add_protection", defaults["add_protection"]),
        "primary_choice": _resolve_value(resolved_primary_choice, "DECK_PRIMARY_CHOICE", json_cfg, "primary_choice", defaults["primary_choice"]),
        "secondary_choice": _resolve_value(resolved_secondary_choice, "DECK_SECONDARY_CHOICE", json_cfg, "secondary_choice", defaults["secondary_choice"]),
        "tertiary_choice": _resolve_value(resolved_tertiary_choice, "DECK_TERTIARY_CHOICE", json_cfg, "tertiary_choice", defaults["tertiary_choice"]),
        "bracket_level": _resolve_value(args.bracket_level, "DECK_BRACKET_LEVEL", json_cfg, "bracket_level", None),
        "add_lands": _resolve_value(args.add_lands, "DECK_ADD_LANDS", json_cfg, "add_lands", defaults["add_lands"]),
        "fetch_count": _resolve_value(args.fetch_count, "DECK_FETCH_COUNT", json_cfg, "fetch_count", defaults["fetch_count"]),
        "dual_count": _resolve_value(args.dual_count, "DECK_DUAL_COUNT", json_cfg, "dual_count", defaults["dual_count"]),
        "triple_count": _resolve_value(args.triple_count, "DECK_TRIPLE_COUNT", json_cfg, "triple_count", defaults["triple_count"]),
        "utility_count": _resolve_value(args.utility_count, "DECK_UTILITY_COUNT", json_cfg, "utility_count", defaults["utility_count"]),
        "ideal_counts": ideal_counts_resolved,
        # M4: Include/Exclude configuration (CLI + JSON + Env priority)
        "include_cards": cli_include_cards or include_cards_json,
        "exclude_cards": cli_exclude_cards or exclude_cards_json,
        "enforcement_mode": args.enforcement_mode or json_cfg.get("enforcement_mode", "warn"),
        "allow_illegal": args.allow_illegal if args.allow_illegal is not None else bool(json_cfg.get("allow_illegal", False)),
        "fuzzy_matching": args.fuzzy_matching if args.fuzzy_matching is not None else bool(json_cfg.get("fuzzy_matching", True)),
        "additional_themes": list(theme_resolution.requested),
        "theme_match_mode": theme_resolution.mode,
        "user_theme_weight": weight_value,
        "secondary_commander": resolved_secondary_commander,
        "background": resolved_background,
        "enable_partner_mechanics": bool(resolved_partner_flag) if resolved_partner_flag is not None else False,
    }

    if args.dry_run:
        preview = dict(resolved)
        preview["additional_themes_resolved"] = list(theme_resolution.resolved)
        preview["additional_themes_unresolved"] = list(theme_resolution.unresolved)
        preview["theme_catalog_version"] = theme_resolution.catalog_version
        preview["fuzzy_corrections"] = dict(theme_resolution.fuzzy_corrections)
        preview["user_theme_weight"] = weight_value
        print(json.dumps(preview, indent=2))
        return 0

    if not str(resolved.get("command_name", "")).strip():
        print("Error: commander is required. Provide --commander or a JSON config with a 'commander' field.")
        return 2

    if theme_resolution.requested:
        if theme_resolution.fuzzy_corrections:
            print("Fuzzy theme corrections applied:")
            for original, corrected in theme_resolution.fuzzy_corrections.items():
                print(f"  • {original} → {corrected}")
        if theme_resolution.unresolved and theme_resolution.mode != "strict":
            print("Warning: unresolved additional themes (permissive mode):")
            for item in theme_resolution.unresolved:
                suggestion_text = ", ".join(
                    f"{s['theme']} ({s['score']:.1f})" for s in item.get("suggestions", [])
                )
                if suggestion_text:
                    print(f"  • {item['input']} → suggestions: {suggestion_text}")
                else:
                    print(f"  • {item['input']} (no suggestions)")

    try:
        run_kwargs = dict(resolved)
        run_kwargs["user_theme_resolution"] = theme_resolution
        run_kwargs["enable_partner_mechanics"] = bool(resolved_partner_flag)
        run(**run_kwargs)
    except CommanderValidationError as exc:
        print(str(exc))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
