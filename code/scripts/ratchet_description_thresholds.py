"""Analyze description_fallback_history.jsonl and propose updated regression test thresholds.

Algorithm:
 - Load all history records (JSON lines) that include generic_total & generic_pct.
 - Use the most recent N (default 5) snapshots to compute a smoothed (median) generic_pct.
 - If median is at least 2 percentage points below current test ceiling OR
   the latest generic_total is at least 10 below current ceiling, propose new targets.
 - Output JSON with keys: current_total_ceiling, current_pct_ceiling,
   proposed_total_ceiling, proposed_pct_ceiling, rationale.

Defaults assume current ceilings (update if test changes):
   total <= 365, pct < 52.0

Usage:
  python code/scripts/ratchet_description_thresholds.py \
      --history config/themes/description_fallback_history.jsonl

You can override current thresholds:
  --current-total 365 --current-pct 52.0
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from statistics import median
from typing import List, Dict, Any


def load_history(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and 'generic_total' in obj:
                out.append(obj)
        except Exception:
            continue
    # Sort by timestamp lexicographically (ISO) ensures chronological
    out.sort(key=lambda x: x.get('timestamp',''))
    return out


def propose(history: List[Dict[str, Any]], current_total: int, current_pct: float, window: int) -> Dict[str, Any]:
    if not history:
        return {
            'error': 'No history records found',
            'current_total_ceiling': current_total,
            'current_pct_ceiling': current_pct,
        }
    recent = history[-window:] if len(history) > window else history
    generic_pcts = [h.get('generic_pct') for h in recent if isinstance(h.get('generic_pct'), (int,float))]
    generic_totals = [h.get('generic_total') for h in recent if isinstance(h.get('generic_total'), int)]
    if not generic_pcts or not generic_totals:
        return {'error': 'Insufficient numeric data', 'current_total_ceiling': current_total, 'current_pct_ceiling': current_pct}
    med_pct = median(generic_pcts)
    latest = history[-1]
    latest_total = latest.get('generic_total', 0)
    # Proposed ceilings start as current
    proposed_total = current_total
    proposed_pct = current_pct
    rationale: List[str] = []
    # Condition 1: median improvement >= 2 pct points vs current ceiling (i.e., headroom exists)
    if med_pct + 2.0 <= current_pct:
        proposed_pct = round(max(med_pct + 1.0, med_pct * 1.02), 2)  # leave ~1pct or small buffer
        rationale.append(f"Median generic_pct {med_pct}% well below ceiling {current_pct}%")
    # Condition 2: latest total at least 10 below current total ceiling
    if latest_total + 10 <= current_total:
        proposed_total = latest_total + 5  # leave small absolute buffer
        rationale.append(f"Latest generic_total {latest_total} well below ceiling {current_total}")
    return {
        'current_total_ceiling': current_total,
        'current_pct_ceiling': current_pct,
        'median_recent_pct': med_pct,
        'latest_total': latest_total,
        'proposed_total_ceiling': proposed_total,
        'proposed_pct_ceiling': proposed_pct,
        'rationale': rationale,
        'records_considered': len(recent),
    }


def main():  # pragma: no cover (I/O tool)
    ap = argparse.ArgumentParser(description='Propose ratcheted generic description regression thresholds')
    ap.add_argument('--history', type=str, default='config/themes/description_fallback_history.jsonl')
    ap.add_argument('--current-total', type=int, default=365)
    ap.add_argument('--current-pct', type=float, default=52.0)
    ap.add_argument('--window', type=int, default=5, help='Number of most recent records to consider')
    args = ap.parse_args()
    hist = load_history(Path(args.history))
    result = propose(hist, args.current_total, args.current_pct, args.window)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()