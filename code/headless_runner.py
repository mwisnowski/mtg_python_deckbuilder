from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional

from deck_builder.builder import DeckBuilder

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
) -> DeckBuilder:
    """Run a scripted non-interactive deck build and return the DeckBuilder instance."""
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
    # Bracket (meta power / style) selection; default to 3 if not provided
    scripted_inputs.append(str(bracket_level if isinstance(bracket_level, int) and 1 <= bracket_level <= 5 else 3))
    # Ideal count prompts (press Enter for defaults)
    for _ in range(8):
        scripted_inputs.append("")

    def scripted_input(prompt: str) -> str:
        if scripted_inputs:
            return scripted_inputs.pop(0)
        raise RuntimeError("Ran out of scripted inputs for prompt: " + prompt)

    builder = DeckBuilder(input_func=scripted_input)
    # Mark this run as headless so builder can adjust exports and logging
    try:
        builder.headless = True  # type: ignore[attr-defined]
    except Exception:
        pass
    # If ideal_counts are provided (from JSON), use them as the current defaults
    # so the step 2 prompts will show these values and our blank entries will accept them.
    if isinstance(ideal_counts, dict) and ideal_counts:
        try:
            ic: Dict[str, int] = {}
            for k, v in ideal_counts.items():
                try:
                    iv = int(v) if v is not None else None  # type: ignore
                except Exception:
                    continue
                if iv is None:
                    continue
                # Only accept known keys
                if k in {"ramp","lands","basic_lands","creatures","removal","wipes","card_advantage","protection"}:
                    ic[k] = iv
            if ic:
                builder.ideal_counts.update(ic)  # type: ignore[attr-defined]
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

def _export_outputs(builder: DeckBuilder) -> None:
    csv_path: Optional[str] = None
    try:
        csv_path = builder.export_decklist_csv() if hasattr(builder, "export_decklist_csv") else None
    except Exception:
        csv_path = None
    try:
        if hasattr(builder, "export_decklist_text"):
            if csv_path:
                base = os.path.splitext(os.path.basename(csv_path))[0]
                builder.export_decklist_text(filename=base + ".txt")
            else:
                builder.export_decklist_text()
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


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Headless deck builder runner")
    p.add_argument("--config", default=os.getenv("DECK_CONFIG"), help="Path to JSON config file")
    p.add_argument("--commander", default=None)
    p.add_argument("--primary-choice", type=int, default=None)
    p.add_argument("--secondary-choice", type=_parse_opt_int, default=None)
    p.add_argument("--tertiary-choice", type=_parse_opt_int, default=None)
    p.add_argument("--bracket-level", type=int, default=None)
    p.add_argument("--add-lands", type=_parse_bool, default=None)
    p.add_argument("--fetch-count", type=_parse_opt_int, default=None)
    p.add_argument("--dual-count", type=_parse_opt_int, default=None)
    p.add_argument("--triple-count", type=_parse_opt_int, default=None)
    p.add_argument("--utility-count", type=_parse_opt_int, default=None)
    # no seed support
    # Booleans
    p.add_argument("--add-creatures", type=_parse_bool, default=None)
    p.add_argument("--add-non-creature-spells", type=_parse_bool, default=None)
    p.add_argument("--add-ramp", type=_parse_bool, default=None)
    p.add_argument("--add-removal", type=_parse_bool, default=None)
    p.add_argument("--add-wipes", type=_parse_bool, default=None)
    p.add_argument("--add-card-advantage", type=_parse_bool, default=None)
    p.add_argument("--add-protection", type=_parse_bool, default=None)
    p.add_argument("--dry-run", action="store_true", help="Print resolved config and exit")
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


def _main() -> int:
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

    resolved = {
        "command_name": _resolve_value(args.commander, "DECK_COMMANDER", json_cfg, "commander", defaults["command_name"]),
        "add_creatures": _resolve_value(args.add_creatures, "DECK_ADD_CREATURES", json_cfg, "add_creatures", defaults["add_creatures"]),
        "add_non_creature_spells": _resolve_value(args.add_non_creature_spells, "DECK_ADD_NON_CREATURE_SPELLS", json_cfg, "add_non_creature_spells", defaults["add_non_creature_spells"]),
        "add_ramp": _resolve_value(args.add_ramp, "DECK_ADD_RAMP", json_cfg, "add_ramp", defaults["add_ramp"]),
        "add_removal": _resolve_value(args.add_removal, "DECK_ADD_REMOVAL", json_cfg, "add_removal", defaults["add_removal"]),
        "add_wipes": _resolve_value(args.add_wipes, "DECK_ADD_WIPES", json_cfg, "add_wipes", defaults["add_wipes"]),
        "add_card_advantage": _resolve_value(args.add_card_advantage, "DECK_ADD_CARD_ADVANTAGE", json_cfg, "add_card_advantage", defaults["add_card_advantage"]),
        "add_protection": _resolve_value(args.add_protection, "DECK_ADD_PROTECTION", json_cfg, "add_protection", defaults["add_protection"]),
        "primary_choice": _resolve_value(args.primary_choice, "DECK_PRIMARY_CHOICE", json_cfg, "primary_choice", defaults["primary_choice"]),
        "secondary_choice": _resolve_value(args.secondary_choice, "DECK_SECONDARY_CHOICE", json_cfg, "secondary_choice", defaults["secondary_choice"]),
        "tertiary_choice": _resolve_value(args.tertiary_choice, "DECK_TERTIARY_CHOICE", json_cfg, "tertiary_choice", defaults["tertiary_choice"]),
    "bracket_level": _resolve_value(args.bracket_level, "DECK_BRACKET_LEVEL", json_cfg, "bracket_level", None),
        "add_lands": _resolve_value(args.add_lands, "DECK_ADD_LANDS", json_cfg, "add_lands", defaults["add_lands"]),
        "fetch_count": _resolve_value(args.fetch_count, "DECK_FETCH_COUNT", json_cfg, "fetch_count", defaults["fetch_count"]),
        "dual_count": _resolve_value(args.dual_count, "DECK_DUAL_COUNT", json_cfg, "dual_count", defaults["dual_count"]),
    "triple_count": _resolve_value(args.triple_count, "DECK_TRIPLE_COUNT", json_cfg, "triple_count", defaults["triple_count"]),
    "utility_count": _resolve_value(args.utility_count, "DECK_UTILITY_COUNT", json_cfg, "utility_count", defaults["utility_count"]),
    "ideal_counts": ideal_counts_json,
    }

    if args.dry_run:
        print(json.dumps(resolved, indent=2))
        return 0

    # Optional: map tag names from JSON/env to numeric indices for this commander
    try:
        primary_tag_name = (str(os.getenv("DECK_PRIMARY_TAG") or "").strip()) or str(json_cfg.get("primary_tag", "")).strip()
        secondary_tag_name = (str(os.getenv("DECK_SECONDARY_TAG") or "").strip()) or str(json_cfg.get("secondary_tag", "")).strip()
        tertiary_tag_name = (str(os.getenv("DECK_TERTIARY_TAG") or "").strip()) or str(json_cfg.get("tertiary_tag", "")).strip()
        tag_names = [t for t in [primary_tag_name, secondary_tag_name, tertiary_tag_name] if t]
        if tag_names:
            try:
                # Load commander tags to compute indices
                tmp = DeckBuilder()
                df = tmp.load_commander_data()
                row = df[df["name"] == resolved["command_name"]]
                if not row.empty:
                    original = list(dict.fromkeys(row.iloc[0].get("themeTags", []) or []))
                    # Step 1: primary from original
                    if primary_tag_name:
                        for i, t in enumerate(original, start=1):
                            if str(t).strip().lower() == primary_tag_name.strip().lower():
                                resolved["primary_choice"] = i
                                break
                    # Step 2: secondary from remaining after primary
                    if secondary_tag_name:
                        primary_idx = resolved.get("primary_choice")
                        remaining_1 = [t for j, t in enumerate(original, start=1) if j != primary_idx]
                        for i2, t in enumerate(remaining_1, start=1):
                            if str(t).strip().lower() == secondary_tag_name.strip().lower():
                                resolved["secondary_choice"] = i2
                                break
                    # Step 3: tertiary from remaining after primary+secondary
                    if tertiary_tag_name and resolved.get("secondary_choice") is not None:
                        primary_idx = resolved.get("primary_choice")
                        secondary_idx = resolved.get("secondary_choice")
                        # reconstruct remaining after removing primary then secondary as displayed
                        remaining_1 = [t for j, t in enumerate(original, start=1) if j != primary_idx]
                        remaining_2 = [t for j, t in enumerate(remaining_1, start=1) if j != secondary_idx]
                        for i3, t in enumerate(remaining_2, start=1):
                            if str(t).strip().lower() == tertiary_tag_name.strip().lower():
                                resolved["tertiary_choice"] = i3
                                break
            except Exception:
                pass
    except Exception:
        pass

    if not str(resolved.get("command_name", "")).strip():
        print("Error: commander is required. Provide --commander or a JSON config with a 'commander' field.")
        return 2

    run(**resolved)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
