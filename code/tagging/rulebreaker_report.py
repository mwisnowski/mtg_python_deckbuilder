"""Roadmap 35 Milestone 9: shared helpers for reporting unrecognized Rulebreaker candidates.

Used by both the CI auto-filing step (`build-similarity-cache.yml`, via a small
Python one-liner) and the web app's `/status/setup` panel, so the CI-filed issue
and the local copy-paste textarea always render the same body shape. No `gh`/
network code beyond the plain, unauthenticated GitHub search used by
`lookup_existing_issue()`; CI files issues via the `gh` CLI directly, not
through this module.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import requests

import logging_util

logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)

REPO = "mwisnowski/mtg_python_deckbuilder"
_SEARCH_URL = "https://api.github.com/search/issues"
_LOOKUP_CACHE_TTL_SECONDS = 300

# name (casefolded) -> (cached_at_monotonic, html_url_or_None)
_lookup_cache: dict[str, tuple[float, Optional[str]]] = {}


def build_candidate_issue_body(candidate: dict[str, Any]) -> str:
    """Render one candidate into the same section structure as the
    `.github/ISSUE_TEMPLATE/rulebreaker-card-report.md` template, so a
    CI-filed issue and the web UI's copy-paste textarea are always identical
    in shape.
    """
    name = str(candidate.get('name', '')).strip()
    text = str(candidate.get('text_snippet') or candidate.get('text') or '')
    matched_signal = str(candidate.get('matched_signal', ''))
    detected_by = str(candidate.get('detected_by') or 'Automated tagging pass (flagged during run_tagging())')
    slug = (
        name.lower().replace(',', '').replace("'", '').replace(' ', '_').strip('_')
        or 'card_name_slug'
    )
    return (
        "### Card Name\n"
        f"{name}\n\n"
        "### Set / Collector Number\n"
        "_Unknown (detected automatically during tagging)._\n\n"
        "### Detected By\n"
        f"{detected_by}\n\n"
        "### Oracle Text\n"
        "```\n"
        f"{text}\n"
        "```\n\n"
        "### Suggested Rule Type\n"
        "_Not yet reviewed; please classify against the existing `rule_type` values._\n\n"
        "### Proposed Registry Entry\n"
        "```python\n"
        f"'{slug}': {{\n"
        f"    'id': '{slug}',\n"
        f"    'name': '{name}',\n"
        "    'color_identity': [],\n"
        "    'rule_type': '',\n"
        "    'params': {},\n"
        "    'basic_lands_scope': 'any',\n"
        "    'no_max_deck_size': False,\n"
        "    'requires_user_input': False,\n"
        "},\n"
        "```\n\n"
        "### Additional Notes\n"
        f"Matched signal: `{matched_signal}`\n"
    )


def lookup_existing_issue(name: str) -> Optional[str]:
    """Unauthenticated GitHub issue search for an existing report of `name`.

    Fails soft (returns None) on any network error, non-200 response, or empty
    result set -- never raises. Results are cached in-process for a few
    minutes per name to stay well under GitHub's low unauthenticated search
    rate limit across repeated status polls.
    """
    now = time.monotonic()
    cached = _lookup_cache.get(name)
    if cached is not None and (now - cached[0]) < _LOOKUP_CACHE_TTL_SECONDS:
        return cached[1]

    result: Optional[str] = None
    try:
        query = f'repo:{REPO} "Rulebreaker: {name}" in:title'
        resp = requests.get(_SEARCH_URL, params={"q": query}, timeout=5)
        if resp.status_code == 200:
            items = (resp.json() or {}).get("items") or []
            if items:
                result = items[0].get("html_url")
        else:
            logger.debug(f"lookup_existing_issue: non-200 response ({resp.status_code}) for '{name}'")
    except Exception as e:
        logger.debug(f"lookup_existing_issue: request failed for '{name}': {e}")

    _lookup_cache[name] = (now, result)
    return result
