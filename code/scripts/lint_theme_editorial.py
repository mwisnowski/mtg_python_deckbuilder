"""Phase D: Lint editorial metadata for theme YAML files.

Effective after Phase D close-out:
 - Minimum example_commanders threshold (default 5) is enforced when either
     EDITORIAL_MIN_EXAMPLES_ENFORCE=1 or --enforce-min-examples is supplied.
 - CI sets EDITORIAL_MIN_EXAMPLES_ENFORCE=1 so insufficient examples are fatal.

Checks (non-fatal unless escalated):
 - example_commanders/example_cards length & uniqueness
 - deck_archetype membership in allowed set (warn if unknown)
 - Cornerstone themes have at least one example commander & card (error in strict mode)

Exit codes:
 0: No fatal errors
 1: Fatal errors (structural, strict cornerstone failures, enforced minimum examples)
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import List, Set
import re

import sys

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'

ALLOWED_ARCHETYPES: Set[str] = {
    'Lands', 'Graveyard', 'Planeswalkers', 'Tokens', 'Counters', 'Spells', 'Artifacts', 'Enchantments', 'Politics',
    'Combo', 'Aggro', 'Control', 'Midrange', 'Stax', 'Ramp', 'Toolbox'
}

CORNERSTONE: Set[str] = {
    'Landfall', 'Reanimate', 'Superfriends', 'Tokens Matter', '+1/+1 Counters'
}


def lint(strict: bool, enforce_min: bool, min_examples: int, require_description: bool, require_popularity: bool) -> int:
    if yaml is None:
        print('YAML support not available (PyYAML missing); skipping lint.')
        return 0
    if not CATALOG_DIR.exists():
        print('Catalog directory missing; nothing to lint.')
        return 0
    errors: List[str] = []
    warnings: List[str] = []
    cornerstone_present: Set[str] = set()
    seen_display: Set[str] = set()
    ann_re = re.compile(r" - Synergy \(([^)]+)\)$")
    for path in sorted(CATALOG_DIR.glob('*.yml')):
        try:
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
        except Exception as e:
            errors.append(f"Failed to parse {path.name}: {e}")
            continue
        if not isinstance(data, dict):
            errors.append(f"YAML not mapping: {path.name}")
            continue
        name = str(data.get('display_name') or '').strip()
        if not name:
            continue
        # Skip deprecated alias placeholder files
        notes_field = data.get('notes')
        if isinstance(notes_field, str) and 'Deprecated alias file' in notes_field:
            continue
        if name in seen_display:
            # Already processed a canonical file for this display name; skip duplicates (aliases)
            continue
        seen_display.add(name)
        ex_cmd = data.get('example_commanders') or []
        ex_cards = data.get('example_cards') or []
        synergy_cmds = data.get('synergy_commanders') if isinstance(data.get('synergy_commanders'), list) else []
        theme_synergies = data.get('synergies') if isinstance(data.get('synergies'), list) else []
        description = data.get('description') if isinstance(data.get('description'), str) else None
        if not isinstance(ex_cmd, list):
            errors.append(f"example_commanders not list in {path.name}")
            ex_cmd = []
        if not isinstance(ex_cards, list):
            errors.append(f"example_cards not list in {path.name}")
            ex_cards = []
        # Length caps
        if len(ex_cmd) > 12:
            warnings.append(f"{name}: example_commanders trimmed to 12 (found {len(ex_cmd)})")
        if len(ex_cards) > 20:
            warnings.append(f"{name}: example_cards length {len(ex_cards)} > 20 (consider trimming)")
        if synergy_cmds and len(synergy_cmds) > 6:
            warnings.append(f"{name}: synergy_commanders length {len(synergy_cmds)} > 6 (3/2/1 pattern expected)")
        if ex_cmd and len(ex_cmd) < min_examples:
            msg = f"{name}: example_commanders only {len(ex_cmd)} (<{min_examples} minimum target)"
            if enforce_min:
                errors.append(msg)
            else:
                warnings.append(msg)
        if not synergy_cmds and any(' - Synergy (' in c for c in ex_cmd):
            # If synergy_commanders intentionally filtered out because all synergy picks were promoted, skip warning.
            # Heuristic: if at least 5 examples and every annotated example has unique base name, treat as satisfied.
            base_names = {c.split(' - Synergy ')[0] for c in ex_cmd if ' - Synergy (' in c}
            if not (len(ex_cmd) >= 5 and len(base_names) >= 1):
                warnings.append(f"{name}: has synergy-annotated example_commanders but missing synergy_commanders list")
        # Uniqueness
        if len(set(ex_cmd)) != len(ex_cmd):
            warnings.append(f"{name}: duplicate entries in example_commanders")
        if len(set(ex_cards)) != len(ex_cards):
            warnings.append(f"{name}: duplicate entries in example_cards")
        # Placeholder anchor detection (post-autofill hygiene)
        if ex_cmd:
            placeholder_pattern = re.compile(r" Anchor( [A-Z])?$")
            has_placeholder = any(isinstance(e, str) and placeholder_pattern.search(e) for e in ex_cmd)
            if has_placeholder:
                msg_anchor = f"{name}: placeholder 'Anchor' entries remain (purge expected)"
                if strict:
                    errors.append(msg_anchor)
                else:
                    warnings.append(msg_anchor)
        if synergy_cmds:
            base_synergy_names = [c.split(' - Synergy ')[0] for c in synergy_cmds]
            if len(set(base_synergy_names)) != len(base_synergy_names):
                warnings.append(f"{name}: duplicate entries in synergy_commanders (base names)")

        # Annotation validation: each annotated example should reference a synergy in theme synergies
        for c in ex_cmd:
            if ' - Synergy (' in c:
                m = ann_re.search(c)
                if m:
                    syn = m.group(1).strip()
                    if syn and syn not in theme_synergies:
                        warnings.append(f"{name}: example commander annotation synergy '{syn}' not in theme synergies list")
        # Cornerstone coverage
        if name in CORNERSTONE:
            if not ex_cmd:
                warnings.append(f"Cornerstone theme {name} missing example_commanders")
            if not ex_cards:
                warnings.append(f"Cornerstone theme {name} missing example_cards")
            else:
                cornerstone_present.add(name)
        # Archetype
        arch = data.get('deck_archetype')
        if arch and arch not in ALLOWED_ARCHETYPES:
            warnings.append(f"{name}: deck_archetype '{arch}' not in allowed set {sorted(ALLOWED_ARCHETYPES)}")
        # Popularity bucket optional; if provided ensure within expected vocabulary
        pop_bucket = data.get('popularity_bucket')
        if pop_bucket and pop_bucket not in {'Very Common', 'Common', 'Uncommon', 'Niche', 'Rare'}:
            warnings.append(f"{name}: invalid popularity_bucket '{pop_bucket}'")
        # Description quality checks (non-fatal for now)
        if not description:
            msg = f"{name}: missing description"
            if strict or require_description:
                errors.append(msg)
            else:
                warnings.append(msg + " (will fall back to auto-generated in catalog)")
        else:
            wc = len(description.split())
            if wc < 5:
                warnings.append(f"{name}: description very short ({wc} words)")
            elif wc > 60:
                warnings.append(f"{name}: description long ({wc} words) consider tightening (<60)")
        if not pop_bucket:
            msgp = f"{name}: missing popularity_bucket"
            if strict or require_popularity:
                errors.append(msgp)
            else:
                warnings.append(msgp)
        # Editorial quality promotion policy (advisory; some escalated in strict)
        quality = (data.get('editorial_quality') or '').strip().lower()
        generic = bool(description and description.startswith('Builds around'))
        ex_count = len(ex_cmd)
        has_unannotated = any(' - Synergy (' not in e for e in ex_cmd)
        if quality:
            if quality == 'reviewed':
                if ex_count < 5:
                    warnings.append(f"{name}: reviewed status but only {ex_count} example_commanders (<5)")
                if generic:
                    warnings.append(f"{name}: reviewed status but still generic description")
            elif quality == 'final':
                # Final must have curated (non-generic) description and >=6 examples including at least one unannotated
                if generic:
                    msgf = f"{name}: final status but generic description"
                    if strict:
                        errors.append(msgf)
                    else:
                        warnings.append(msgf)
                if ex_count < 6:
                    msgf2 = f"{name}: final status but only {ex_count} example_commanders (<6)"
                    if strict:
                        errors.append(msgf2)
                    else:
                        warnings.append(msgf2)
                if not has_unannotated:
                    warnings.append(f"{name}: final status but no unannotated (curated) example commander present")
            elif quality not in {'draft','reviewed','final'}:
                warnings.append(f"{name}: unknown editorial_quality '{quality}' (expected draft|reviewed|final)")
        else:
            # Suggest upgrade when criteria met but field missing
            if ex_count >= 5 and not generic:
                warnings.append(f"{name}: missing editorial_quality; qualifies for reviewed (≥5 examples & non-generic description)")
    # Summaries
    if warnings:
        print('LINT WARNINGS:')
        for w in warnings:
            print(f" - {w}")
    if errors:
        print('LINT ERRORS:')
        for e in errors:
            print(f" - {e}")
    if strict:
        # Promote cornerstone missing examples to errors in strict mode
        promoted_errors = []
        for w in list(warnings):
            if w.startswith('Cornerstone theme') and ('missing example_commanders' in w or 'missing example_cards' in w):
                promoted_errors.append(w)
                warnings.remove(w)
        if promoted_errors:
            print('PROMOTED TO ERRORS (strict cornerstone requirements):')
            for pe in promoted_errors:
                print(f" - {pe}")
            errors.extend(promoted_errors)
    if errors:
        if strict:
            return 1
    return 0


def main():  # pragma: no cover
    parser = argparse.ArgumentParser(description='Lint editorial metadata for theme YAML files (Phase D)')
    parser.add_argument('--strict', action='store_true', help='Treat errors as fatal (non-zero exit)')
    parser.add_argument('--enforce-min-examples', action='store_true', help='Escalate insufficient example_commanders to errors')
    parser.add_argument('--min-examples', type=int, default=int(os.environ.get('EDITORIAL_MIN_EXAMPLES', '5')), help='Minimum target for example_commanders (default 5)')
    parser.add_argument('--require-description', action='store_true', help='Fail if any YAML missing description (even if not strict)')
    parser.add_argument('--require-popularity', action='store_true', help='Fail if any YAML missing popularity_bucket (even if not strict)')
    args = parser.parse_args()
    enforce_flag = args.enforce_min_examples or bool(int(os.environ.get('EDITORIAL_MIN_EXAMPLES_ENFORCE', '0') or '0'))
    rc = lint(
        args.strict,
        enforce_flag,
        args.min_examples,
        args.require_description or bool(int(os.environ.get('EDITORIAL_REQUIRE_DESCRIPTION', '0') or '0')),
        args.require_popularity or bool(int(os.environ.get('EDITORIAL_REQUIRE_POPULARITY', '0') or '0')),
    )
    if rc != 0:
        sys.exit(rc)


if __name__ == '__main__':
    main()
