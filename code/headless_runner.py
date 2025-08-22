from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional
from pathlib import Path

from code.deck_builder.builder import DeckBuilder

"""Headless (non-interactive) runner.

Features:
    - Script commander selection.
    - Script primary / optional secondary / tertiary tags.
    - Apply bracket & accept default ideal counts.
    - Invoke multi-theme creature addition if available (fallback to primary-only).

Use run(..., secondary_choice=2, tertiary_choice=3, use_multi_theme=True) to exercise multi-theme logic.
Indices correspond to the numbered tag list presented during interaction.
"""

def run(
    command_name: str = "Pantlaza",
    add_creatures: bool = True,
    add_non_creature_spells: bool = True,
    # Fine-grained toggles (used only if add_non_creature_spells is False)
    add_ramp: bool = True,
    add_removal: bool = True,
    add_wipes: bool = True,
    add_card_advantage: bool = True,
    add_protection: bool = True,
    use_multi_theme: bool = True,
    primary_choice: int = 2,
    secondary_choice: Optional[int] = 2,
    tertiary_choice: Optional[int] = 2,
    add_lands: bool = True,
    fetch_count: Optional[int] = 3,
    dual_count: Optional[int] = None,
    triple_count: Optional[int] = None,
    utility_count: Optional[int] = None,
    ideal_counts: Optional[Dict[str, int]] = None,
) -> DeckBuilder:
    """Run a scripted non-interactive deck build and return the DeckBuilder instance.

    Integer parameters (primary_choice, secondary_choice, tertiary_choice) correspond to the
    numeric indices shown during interactive tag selection. Pass None to omit secondary/tertiary.
    Optional counts (fetch_count, dual_count, triple_count, utility_count) constrain land steps.
    
    """
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
    # Bracket (meta power / style) selection; keeping existing scripted value
    scripted_inputs.append("3")
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
        if hasattr(builder, 'run_land_step1'):
            builder.run_land_step1()  # Basics / initial
        if hasattr(builder, 'run_land_step2'):
            builder.run_land_step2()  # Utility basics / rebalancing
        if hasattr(builder, 'run_land_step3'):
            builder.run_land_step3()  # Kindred lands if applicable
        if hasattr(builder, 'run_land_step4'):
            builder.run_land_step4(requested_count=fetch_count)
        if hasattr(builder, 'run_land_step5'):
            builder.run_land_step5(requested_count=dual_count)
        if hasattr(builder, 'run_land_step6'):
            builder.run_land_step6(requested_count=triple_count)
        if hasattr(builder, 'run_land_step7'):
            
            builder.run_land_step7(requested_count=utility_count)
        if hasattr(builder, 'run_land_step8'):
            builder.run_land_step8()

    if add_creatures:
        builder.add_creatures()
    # Non-creature spell categories (ramp / removal / wipes / draw / protection)
    if add_non_creature_spells and hasattr(builder, 'add_non_creature_spells'):
        builder.add_non_creature_spells()
    else:
        # Allow selective invocation if orchestrator not desired
        if add_ramp and hasattr(builder, 'add_ramp'):
            builder.add_ramp()
        if add_removal and hasattr(builder, 'add_removal'):
            builder.add_removal()
        if add_wipes and hasattr(builder, 'add_board_wipes'):
            builder.add_board_wipes()
        if add_card_advantage and hasattr(builder, 'add_card_advantage'):
            builder.add_card_advantage()
        if add_protection and hasattr(builder, 'add_protection'):
            builder.add_protection()
        

    # Suppress verbose library print in headless run since CSV export is produced.
    # builder.print_card_library()
    builder.post_spell_land_adjust()
    # Export decklist CSV (commander first word + date)
    csv_path: Optional[str] = None
    if hasattr(builder, 'export_decklist_csv'):
        try:
            csv_path = builder.export_decklist_csv()
        except Exception:
            csv_path = None
    if hasattr(builder, 'export_decklist_text'):
        try:
            if csv_path:
                base = os.path.splitext(os.path.basename(csv_path))[0]
                builder.export_decklist_text(filename=base + '.txt')
                if hasattr(builder, 'export_run_config_json'):
                    try:
                        cfg_path_env = os.getenv('DECK_CONFIG')
                        if cfg_path_env:
                            cfg_dir = os.path.dirname(cfg_path_env) or '.'
                        elif os.path.isdir('/app/config'):
                            cfg_dir = '/app/config'
                        else:
                            cfg_dir = 'config'
                        os.makedirs(cfg_dir, exist_ok=True)
                        builder.export_run_config_json(directory=cfg_dir, filename=base + '.json')
                        # If an explicit DECK_CONFIG path is given, also write to exactly that path
                        if cfg_path_env:
                            cfg_dir2 = os.path.dirname(cfg_path_env) or '.'
                            cfg_name2 = os.path.basename(cfg_path_env)
                            os.makedirs(cfg_dir2, exist_ok=True)
                            builder.export_run_config_json(directory=cfg_dir2, filename=cfg_name2)
                    except Exception:
                        pass
            else:
                builder.export_decklist_text()
        except Exception:
            pass
    return builder

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
    p.add_argument("--use-multi-theme", type=_parse_bool, default=None)
    p.add_argument("--dry-run", action="store_true", help="Print resolved config and exit")
    p.add_argument("--auto-select-config", action="store_true", help="If set, and multiple JSON configs exist, list and prompt to choose one before running.")
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
    # Optional config auto-discovery/prompting
    cfg_path = args.config
    json_cfg: Dict[str, Any] = {}
    def _discover_json_configs() -> List[str]:
        # Determine directory to scan for JSON configs
        if cfg_path and os.path.isdir(cfg_path):
            cfg_dir = cfg_path
        elif os.path.isdir('/app/config'):
            cfg_dir = '/app/config'
        else:
            cfg_dir = 'config'
        try:
            p = Path(cfg_dir)
            return sorted([str(fp) for fp in p.glob('*.json')]) if p.exists() else []
        except Exception:
            return []

    # If a file path is provided, load it directly
    if cfg_path and os.path.isfile(cfg_path):
        json_cfg = _load_json_config(cfg_path)
    else:
        # If auto-select is requested, we may prompt user to choose a config
        configs = _discover_json_configs()
        if cfg_path and os.path.isdir(cfg_path):
            # Directory explicitly provided, prefer auto selection behavior
            if len(configs) == 1:
                json_cfg = _load_json_config(configs[0])
                os.environ['DECK_CONFIG'] = configs[0]
            elif len(configs) > 1 and args.auto_select_config:
                def _label(p: str) -> str:
                    try:
                        with open(p, 'r', encoding='utf-8') as fh:
                            data = json.load(fh)
                        cmd = str(data.get('commander') or '').strip() or 'Unknown Commander'
                        themes = [t for t in [data.get('primary_tag'), data.get('secondary_tag'), data.get('tertiary_tag')] if isinstance(t, str) and t.strip()]
                        return f"{cmd} - {', '.join(themes)}" if themes else cmd
                    except Exception:
                        return p
                print("\nAvailable JSON configs:")
                for idx, f in enumerate(configs, start=1):
                    print(f"  {idx}) {_label(f)}")
                print("  0) Cancel")
                while True:
                    try:
                        sel = input("Select a config to run [0]: ").strip() or '0'
                    except KeyboardInterrupt:
                        print("")
                        sel = '0'
                    if sel == '0':
                        return 0
                    try:
                        i = int(sel)
                        if 1 <= i <= len(configs):
                            chosen = configs[i - 1]
                            json_cfg = _load_json_config(chosen)
                            os.environ['DECK_CONFIG'] = chosen
                            break
                    except ValueError:
                        pass
                    print("Invalid selection. Try again.")
        else:
            # No explicit file; if exactly one config exists, auto use it; else leave empty
            if len(configs) == 1:
                json_cfg = _load_json_config(configs[0])
                os.environ['DECK_CONFIG'] = configs[0]

    # Defaults mirror run() signature
    defaults = dict(
        command_name="Pantlaza",
        add_creatures=True,
        add_non_creature_spells=True,
        add_ramp=True,
        add_removal=True,
        add_wipes=True,
        add_card_advantage=True,
        add_protection=True,
        use_multi_theme=True,
        primary_choice=2,
        secondary_choice=2,
        tertiary_choice=2,
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
        "use_multi_theme": _resolve_value(args.use_multi_theme, "DECK_USE_MULTI_THEME", json_cfg, "use_multi_theme", defaults["use_multi_theme"]),
        "primary_choice": _resolve_value(args.primary_choice, "DECK_PRIMARY_CHOICE", json_cfg, "primary_choice", defaults["primary_choice"]),
        "secondary_choice": _resolve_value(args.secondary_choice, "DECK_SECONDARY_CHOICE", json_cfg, "secondary_choice", defaults["secondary_choice"]),
        "tertiary_choice": _resolve_value(args.tertiary_choice, "DECK_TERTIARY_CHOICE", json_cfg, "tertiary_choice", defaults["tertiary_choice"]),
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

    run(**resolved)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
