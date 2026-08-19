"""Rule predicates for the Rulebreaker commander mechanic (Roadmap 35).

Each predicate takes a single card row (``pd.Series`` or any Mapping with
``type``/``manaValue``/``text`` keys) plus the archetype's ``params`` dict from
``RULEBREAKER_ARCHETYPES`` and returns whether that card is eligible under the
archetype's rules exception. These predicates only express *type/mana-value*
eligibility for the card-pool exception; the color-identity OR-branch that
combines a predicate match with the "otherwise off-color" check lives in the
builder's card pool filtering (see Roadmap 35, Milestone 3), not here.

``no_max_deck_size`` has no card-pool predicate of its own (it only affects the
deck size cap, not which cards are legal), so it always returns ``False``.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

__all__ = ["RULE_TYPE_PREDICATES", "card_pool_exception"]


def _get(card_row: Mapping[str, Any], key: str, default: Any = "") -> Any:
    try:
        value = card_row.get(key, default)
    except AttributeError:
        value = getattr(card_row, key, default)
    return default if value is None else value


def _type_line(card_row: Mapping[str, Any]) -> str:
    value = _get(card_row, "type", "")
    return str(value) if value else ""


def _mana_value(card_row: Mapping[str, Any]) -> float | None:
    value = _get(card_row, "manaValue", None)
    if value in (None, ""):
        value = _get(card_row, "cmc", None)
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _rule_any_land(card_row: Mapping[str, Any], params: dict) -> bool:
    """Any land card is eligible (Grizzlegom, Hurloon Hero)."""
    return "Land" in _type_line(card_row)


def _rule_type_any_color(card_row: Mapping[str, Any], params: dict) -> bool:
    """Card's type line contains any of ``params['types']``."""
    type_line = _type_line(card_row)
    types = params.get("types", []) or []
    return any(t in type_line for t in types)


def _rule_type_cmc_any_color(card_row: Mapping[str, Any], params: dict) -> bool:
    """Like ``type_any_color``, plus a mana-value floor (``params['mv_min']``)."""
    if not _rule_type_any_color(card_row, params):
        return False
    mv_min = params.get("mv_min")
    if mv_min is None:
        return True
    mana_value = _mana_value(card_row)
    return mana_value is not None and mana_value >= mv_min


def _rule_instant_sorcery_extra_color(card_row: Mapping[str, Any], params: dict) -> bool:
    """Card's type line is Instant or Sorcery (Tolabow, Loch Rascal).

    The extra-color legality check (whether the card's own color identity is
    within the commander's identity plus the chosen extra color) is performed
    by the caller, not here \u2014 this predicate only expresses type eligibility.
    """
    return _rule_type_any_color(card_row, params)


def _rule_no_max_deck_size(card_row: Mapping[str, Any], params: dict) -> bool:
    """No card-pool exception; only the deck size cap is affected (Whtz)."""
    return False


RULE_TYPE_PREDICATES: dict[str, Callable[[Mapping[str, Any], dict], bool]] = {
    "any_land": _rule_any_land,
    "type_any_color": _rule_type_any_color,
    "type_cmc_any_color": _rule_type_cmc_any_color,
    "instant_sorcery_extra_color": _rule_instant_sorcery_extra_color,
    "no_max_deck_size": _rule_no_max_deck_size,
}


def _card_color_identity(card_row: Mapping[str, Any]) -> set[str]:
    """Parse a card row's ``colorIdentity`` field into an uppercase letter set."""
    value = _get(card_row, "colorIdentity", None)
    if value is None:
        return set()
    if isinstance(value, str):
        return {c.strip().upper() for c in value.split(",") if c.strip()}
    if isinstance(value, Iterable):
        return {str(c).strip().upper() for c in value if str(c).strip()}
    return set()


def card_pool_exception(
    card_row: Mapping[str, Any],
    active_rulebreakers: Iterable[Mapping[str, Any]],
    extra_color: str | None = None,
) -> bool:
    """Return True if any active Rulebreaker archetype makes this card legal
    regardless of the normal color-identity subset check (Contract §3's
    card-pool OR-branch). Basic-land relaxation is handled separately by the
    land phases, not here (see Milestone 3).
    """
    for meta in active_rulebreakers or []:
        rule_type = meta.get("rule_type")
        if rule_type == "no_max_deck_size":
            continue
        predicate = RULE_TYPE_PREDICATES.get(rule_type)
        if predicate is None:
            continue
        params = meta.get("params") or {}
        if not predicate(card_row, params):
            continue
        if rule_type == "instant_sorcery_extra_color":
            if not extra_color:
                continue
            card_ci = _card_color_identity(card_row)
            if not card_ci or not card_ci.issubset({str(extra_color).strip().upper()}):
                continue
        return True
    return False
