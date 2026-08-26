from __future__ import annotations

from typing import Dict, List

from deck_builder.tokens import detect_tokens_created as _detect_tokens_created


def detect_all(names: List[str], *, tokens_path: str | None = None) -> Dict[str, object]:
    """Detect tokens/emblems created for a list of card names.

    Returns a dict with key: tokens_created. Mirrors combo_utils.detect_all's
    graceful-fallback convention (never raises; empty list on failure).
    """
    try:
        if tokens_path is not None:
            detected = _detect_tokens_created(names, tokens_path=tokens_path)
        else:
            detected = _detect_tokens_created(names)
    except Exception:
        detected = []
    return {"tokens_created": detected}
