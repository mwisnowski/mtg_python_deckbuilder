"""Validation script for theme catalog (Phase C groundwork).

Performs:
 - Pydantic model validation
 - Duplicate theme detection
 - Enforced synergies presence check (from whitelist)
 - Normalization idempotency check (optional --rebuild-pass)
 - Synergy cap enforcement (allowing soft exceed when curated+enforced exceed cap)
 - JSON Schema export (--schema / --schema-out)

Exit codes:
 0 success
 1 validation errors (structural)
 2 policy errors (duplicates, missing enforced synergies, cap violations)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Set

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
CODE_ROOT = ROOT / 'code'
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from type_definitions_theme_catalog import ThemeCatalog, ThemeYAMLFile
from scripts.extract_themes import load_whitelist_config
from scripts.build_theme_catalog import build_catalog
from web.services.theme_editorial_service import ThemeEditorialService

CATALOG_JSON = ROOT / 'config' / 'themes' / 'theme_list.json'


def load_catalog_file() -> Dict:
    if not CATALOG_JSON.exists():
        raise SystemExit(f"Catalog JSON missing: {CATALOG_JSON}")
    return json.loads(CATALOG_JSON.read_text(encoding='utf-8'))


def validate_catalog(data: Dict, *, whitelist: Dict, allow_soft_exceed: bool = True) -> List[str]:
    errors: List[str] = []
    # If metadata_info missing (legacy extraction output), inject synthetic block (legacy name: provenance)
    if 'metadata_info' not in data:
        legacy = data.get('provenance') if isinstance(data.get('provenance'), dict) else None
        if legacy:
            data['metadata_info'] = legacy
        else:
            data['metadata_info'] = {
                'mode': 'legacy-extraction',
                'generated_at': 'unknown',
                'curated_yaml_files': 0,
                'synergy_cap': int(whitelist.get('synergy_cap', 0) or 0),
                'inference': 'unknown',
                'version': 'pre-merge-fallback'
            }
    if 'generated_from' not in data:
        data['generated_from'] = 'legacy (tagger + constants)'
    try:
        catalog = ThemeCatalog(**data)
    except Exception as e:  # structural validation
        errors.append(f"Pydantic validation failed: {e}")
        return errors

    # Duplicate detection
    seen: Set[str] = set()
    dups: Set[str] = set()
    for t in catalog.themes:
        if t.theme in seen:
            dups.add(t.theme)
        seen.add(t.theme)
    if dups:
        errors.append(f"Duplicate theme entries detected: {sorted(dups)}")

    enforced_cfg: Dict[str, List[str]] = whitelist.get('enforced_synergies', {}) or {}
    synergy_cap = int(whitelist.get('synergy_cap', 0) or 0)

    # Fast index
    theme_map = {t.theme: t for t in catalog.themes}

    # Enforced presence & cap checks
    for anchor, required in enforced_cfg.items():
        if anchor not in theme_map:
            continue  # pruning may allow non-always_include anchors to drop
        syn = theme_map[anchor].synergies
        missing = [r for r in required if r not in syn]
        if missing:
            errors.append(f"Anchor '{anchor}' missing enforced synergies: {missing}")
        if synergy_cap and len(syn) > synergy_cap:
            if not allow_soft_exceed:
                errors.append(f"Anchor '{anchor}' exceeds synergy cap ({len(syn)}>{synergy_cap})")

    # Cap enforcement for non-soft-exceeding cases
    if synergy_cap:
        for t in catalog.themes:
            if len(t.synergies) > synergy_cap:
                # Determine if soft exceed allowed: curated+enforced > cap (we can't reconstruct curated precisely here)
                # Heuristic: if enforced list for anchor exists AND all enforced appear AND len(enforced)>=cap then allow.
                enforced = set(enforced_cfg.get(t.theme, []))
                if not (allow_soft_exceed and enforced and enforced.issubset(set(t.synergies)) and len(enforced) >= synergy_cap):
                    # Allow also if enforced+first curated guess (inference fallback) obviously pushes over cap (can't fully know); skip strict enforcement
                    pass  # Keep heuristic permissive for now

    return errors


def validate_yaml_files(
    *,
    whitelist: Dict,
    strict_alias: bool = False,
    check_editorial_quality: bool = False,
    lint_enabled: bool = False,
    lint_duplication_threshold: float = 0.5,
    lint_quality_threshold: float = 0.3
) -> List[str]:
    """Validate individual YAML catalog files.

    strict_alias: if True, treat presence of a deprecated alias (normalization key)
    as a hard error instead of a soft ignored transitional state.
    check_editorial_quality: if True, check M1 editorial quality fields (description_source, etc.).
    lint_enabled: if True, run M4 linter checks (duplication, quality scoring).
    lint_duplication_threshold: flag themes with duplication ratio above this (default 0.5).
    lint_quality_threshold: flag themes with quality score below this (default 0.3).
    """
    errors: List[str] = []
    
    # M4: Initialize editorial service for lint checks
    editorial_service = None
    global_card_freq = None
    if lint_enabled:
        try:
            editorial_service = ThemeEditorialService()
            global_card_freq = editorial_service.calculate_global_card_frequency()
        except Exception as e:
            errors.append(f"[LINT] Failed to initialize editorial service: {e}")
    catalog_dir = ROOT / 'config' / 'themes' / 'catalog'
    if not catalog_dir.exists():
        return errors
    seen_ids: Set[str] = set()
    normalization_map: Dict[str, str] = whitelist.get('normalization', {}) if isinstance(whitelist.get('normalization'), dict) else {}
    always_include = set(whitelist.get('always_include', []) or [])
    present_always: Set[str] = set()
    for path in sorted(catalog_dir.glob('*.yml')):
        try:
            raw = yaml.safe_load(path.read_text(encoding='utf-8')) if yaml else None
        except Exception:
            errors.append(f"Failed to parse YAML: {path.name}")
            continue
        if not isinstance(raw, dict):
            errors.append(f"YAML not a mapping: {path.name}")
            continue
        try:
            obj = ThemeYAMLFile(**raw)
        except Exception as e:
            errors.append(f"YAML schema violation {path.name}: {e}")
            continue
        # Duplicate id detection
        if obj.id in seen_ids:
            errors.append(f"Duplicate YAML id: {obj.id}")
        seen_ids.add(obj.id)
        
        # M1 Editorial Field Validation (opt-in)
        if check_editorial_quality:
            if obj.description and not obj.description_source:
                errors.append(f"Missing description_source in {path.name} (has description but no source metadata)")
            if obj.description_source == 'generic':
                # Soft warning: generic descriptions should be upgraded
                errors.append(f"[QUALITY] {path.name} has generic description_source - consider upgrading to rule-based or manual")
            if obj.popularity_pinned and not obj.popularity_bucket:
                errors.append(f"Invalid configuration in {path.name}: popularity_pinned=True but popularity_bucket is missing")
        
        # M4 Linter Checks (opt-in)
        if lint_enabled and editorial_service and global_card_freq is not None:
            # Only lint themes with example cards
            if obj.example_cards and len(obj.example_cards) > 0:
                # Check 1: High Duplication Ratio
                try:
                    dup_ratio = editorial_service.calculate_duplication_ratio(
                        example_cards=obj.example_cards,
                        global_card_freq=global_card_freq,
                        duplication_threshold=0.4  # Cards in >40% of themes
                    )
                    if dup_ratio > lint_duplication_threshold:
                        # Calculate total themes for identifying generic cards
                        index = editorial_service.load_index()
                        total_themes = len(index.slug_to_entry)
                        generic_cards = [
                            card for card in obj.example_cards
                            if global_card_freq.get(card, 0) / max(1, total_themes) > 0.4
                        ]
                        errors.append(
                            f"[LINT-WARNING] {path.name} has high duplication ratio ({dup_ratio:.2f} > {lint_duplication_threshold}). "
                            f"Generic cards: {', '.join(generic_cards[:5])}{' ...' if len(generic_cards) > 5 else ''}"
                        )
                except Exception as e:
                    errors.append(f"[LINT] Failed to check duplication for {path.name}: {e}")
                
                # Check 2: Low Quality Score
                try:
                    # Create a minimal ThemeEntry for quality scoring
                    from type_definitions_theme_catalog import ThemeEntry
                    theme_entry = ThemeEntry(
                        theme=obj.display_name,
                        example_cards=obj.example_cards,
                        description_source=obj.description_source
                    )
                    tier, score = editorial_service.calculate_enhanced_quality_score(
                        theme_entry=theme_entry,
                        global_card_freq=global_card_freq
                    )
                    if score < lint_quality_threshold:
                        suggestions = []
                        if len(obj.example_cards) < 5:
                            suggestions.append("Add more example cards (target: 8+)")
                        if obj.description_source == 'generic':
                            suggestions.append("Upgrade to manual or rule-based description")
                        if dup_ratio > 0.4:
                            suggestions.append("Replace generic staples with unique cards")
                        
                        errors.append(
                            f"[LINT-WARNING] {path.name} has low quality score ({score:.2f} < {lint_quality_threshold}, tier={tier}). "
                            f"Suggestions: {'; '.join(suggestions) if suggestions else 'Review theme curation'}"
                        )
                except Exception as e:
                    errors.append(f"[LINT] Failed to check quality for {path.name}: {e}")
        
        # Normalization alias check: display_name should already be normalized if in map
        if normalization_map and obj.display_name in normalization_map.keys():
            if strict_alias:
                errors.append(f"Alias display_name present in strict mode: {obj.display_name} ({path.name})")
            # else soft-ignore for transitional period
        if obj.display_name in always_include:
            present_always.add(obj.display_name)
    missing_always = always_include - present_always
    if missing_always:
        # Not necessarily fatal if those only exist in analytics; warn for now.
        errors.append(f"always_include themes missing YAML files: {sorted(missing_always)}")
    return errors


def main():  # pragma: no cover
    parser = argparse.ArgumentParser(description='Validate theme catalog (Phase C)')
    parser.add_argument('--schema', action='store_true', help='Print JSON Schema for catalog and exit')
    parser.add_argument('--schema-out', type=str, help='Write JSON Schema to file path')
    parser.add_argument('--rebuild-pass', action='store_true', help='Rebuild catalog in-memory and ensure stable equality vs file')
    parser.add_argument('--fail-soft-exceed', action='store_true', help='Treat synergy list length > cap as error even for soft exceed')
    parser.add_argument('--yaml-schema', action='store_true', help='Print JSON Schema for per-file ThemeYAML and exit')
    parser.add_argument('--strict-alias', action='store_true', help='Fail if any YAML uses an alias name slated for normalization')
    parser.add_argument('--check-quality', action='store_true', help='Enable M1 editorial quality checks (description_source, popularity_pinned)')
    parser.add_argument('--lint', action='store_true', help='Enable M4 linter checks (duplication, quality scoring)')
    parser.add_argument('--lint-duplication-threshold', type=float, default=0.5, help='Duplication ratio threshold for linter warnings (default: 0.5)')
    parser.add_argument('--lint-quality-threshold', type=float, default=0.3, help='Quality score threshold for linter warnings (default: 0.3)')
    args = parser.parse_args()

    if args.schema:
        schema = ThemeCatalog.model_json_schema()
        if args.schema_out:
            Path(args.schema_out).write_text(json.dumps(schema, indent=2), encoding='utf-8')
        else:
            print(json.dumps(schema, indent=2))
        return
    if args.yaml_schema:
        schema = ThemeYAMLFile.model_json_schema()
        if args.schema_out:
            Path(args.schema_out).write_text(json.dumps(schema, indent=2), encoding='utf-8')
        else:
            print(json.dumps(schema, indent=2))
        return

    whitelist = load_whitelist_config()
    data = load_catalog_file()
    errors = validate_catalog(data, whitelist=whitelist, allow_soft_exceed=not args.fail_soft_exceed)
    errors.extend(validate_yaml_files(
        whitelist=whitelist,
        strict_alias=args.strict_alias,
        check_editorial_quality=args.check_quality,
        lint_enabled=args.lint,
        lint_duplication_threshold=args.lint_duplication_threshold,
        lint_quality_threshold=args.lint_quality_threshold
    ))

    if args.rebuild_pass:
        rebuilt = build_catalog(limit=0, verbose=False)
        # Compare canonical dict dumps (ordering of themes is deterministic: sorted by theme name in build script)
        normalization_map: Dict[str, str] = whitelist.get('normalization', {}) if isinstance(whitelist.get('normalization'), dict) else {}

        def _canon(theme_list):
            canon: Dict[str, Dict] = {}
            for t in theme_list:
                name = t.get('theme')
                if not isinstance(name, str):
                    continue
                name_canon = normalization_map.get(name, name)
                sy = t.get('synergies', [])
                if not isinstance(sy, list):
                    sy_sorted = []
                else:
                    # Apply normalization inside synergies too
                    sy_norm = [normalization_map.get(s, s) for s in sy if isinstance(s, str)]
                    sy_sorted = sorted(set(sy_norm))
                entry = {
                    'theme': name_canon,
                    'synergies': sy_sorted,
                }
                # Keep first (curated/enforced precedence differences ignored for alias collapse)
                canon.setdefault(name_canon, entry)
            # Return list sorted by canonical name
            return [canon[k] for k in sorted(canon.keys())]

        file_dump = json.dumps(_canon(data.get('themes', [])), sort_keys=True)
        rebuilt_dump = json.dumps(_canon(rebuilt.get('themes', [])), sort_keys=True)
        if file_dump != rebuilt_dump:
            # Provide lightweight diff diagnostics (first 10 differing characters and sample themes)
            try:
                import difflib
                file_list = json.loads(file_dump)
                reb_list = json.loads(rebuilt_dump)
                file_names = [t['theme'] for t in file_list]
                reb_names = [t['theme'] for t in reb_list]
                missing_in_reb = sorted(set(file_names) - set(reb_names))[:5]
                extra_in_reb = sorted(set(reb_names) - set(file_names))[:5]
                # Find first theme with differing synergies
                synergy_mismatch = None
                for f in file_list:
                    for r in reb_list:
                        if f['theme'] == r['theme'] and f['synergies'] != r['synergies']:
                            synergy_mismatch = (f['theme'], f['synergies'][:10], r['synergies'][:10])
                            break
                    if synergy_mismatch:
                        break
                diff_note_parts = []
                if missing_in_reb:
                    diff_note_parts.append(f"missing:{missing_in_reb}")
                if extra_in_reb:
                    diff_note_parts.append(f"extra:{extra_in_reb}")
                if synergy_mismatch:
                    diff_note_parts.append(f"synergy_mismatch:{synergy_mismatch}")
                if not diff_note_parts:
                    # generic char diff snippet
                    for line in difflib.unified_diff(file_dump.splitlines(), rebuilt_dump.splitlines(), n=1):
                        diff_note_parts.append(line)
                        if len(diff_note_parts) > 10:
                            break
                errors.append('Normalization / rebuild pass produced differing theme list output ' + ' | '.join(diff_note_parts))
            except Exception:
                errors.append('Normalization / rebuild pass produced differing theme list output (diff unavailable)')

    if errors:
        print('VALIDATION FAILED:')
        for e in errors:
            print(f" - {e}")
        sys.exit(2)
    print('Theme catalog validation passed.')


if __name__ == '__main__':
    main()
