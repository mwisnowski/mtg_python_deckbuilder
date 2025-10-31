"""Regenerate commander catalog with MDFC merge applied.

This helper refreshes `commander_cards.csv` using the latest setup pipeline and
then runs the tagging/merge step so downstream consumers pick up the unified
multi-face rows. The merge is now always enabled; use the optional
`--compat-snapshot` flag to emit an unmerged compatibility snapshot alongside
the merged catalog for downstream validation.

Examples (run from repo root after activating the virtualenv):

    python -m code.scripts.refresh_commander_catalog
    python -m code.scripts.refresh_commander_catalog --compat-snapshot --skip-setup

The legacy `--mode` argument is retained for backwards compatibility but no
longer disables the merge. `--mode compat` is treated the same as
`--compat-snapshot`, while `--mode off` now issues a warning and still runs the
merge.
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

from settings import CSV_DIRECTORY

DEFAULT_COMPAT_SNAPSHOT = False
SUPPORTED_COLORS = ("commander",)


def _refresh_setup() -> None:
    setup_mod = importlib.import_module("code.file_setup.setup")
    setup_mod.determine_commanders()


def _refresh_tags() -> None:
    tagger = importlib.import_module("code.tagging.tagger")
    tagger = importlib.reload(tagger)
    for color in SUPPORTED_COLORS:
        tagger.load_dataframe(color)


def _summarize_outputs(compat_snapshot: bool) -> str:
    merged = Path(CSV_DIRECTORY) / "commander_cards.csv"
    compat_dir = Path(os.getenv("DFC_COMPAT_DIR", "csv_files/compat_faces"))
    parts = ["✔ Commander catalog refreshed (multi-face merge always on)"]
    parts.append(f"  merged file: {merged.resolve()}")
    if compat_snapshot:
        compat_path = compat_dir / "commander_cards_unmerged.csv"
        parts.append(f"  compat snapshot: {compat_path.resolve()}")
    return "\n".join(parts)


def _resolve_compat_snapshot(mode: str, cli_override: bool | None) -> bool:
    """Determine whether to write the compatibility snapshot."""

    if cli_override is not None:
        return cli_override

    normalized = str(mode or "").strip().lower()

    if normalized in {"", "1", "true", "on"}:
        return False
    if normalized in {"compat", "dual", "both"}:
        return True
    if normalized in {"0", "false", "off", "disabled"}:
        print(
            "⚠ ENABLE_DFC_MERGE=off is deprecated; the merge remains enabled and no compatibility snapshot is written by default.",
            flush=True,
        )
        return False

    if normalized:
        print(
            f"ℹ Legacy --mode value '{normalized}' detected. Multi-face merge is always enabled; pass --compat-snapshot to write the unmerged CSV.",
            flush=True,
        )

    return DEFAULT_COMPAT_SNAPSHOT


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Refresh commander catalog with MDFC merge")
    parser.add_argument(
        "--mode",
        default="",
        help="[Deprecated] Legacy ENABLE_DFC_MERGE value (compat|1|0 etc.).",
    )
    parser.add_argument(
        "--skip-setup",
        action="store_true",
        help="Skip the setup.determine_commanders() step if commander_cards.csv is already up to date.",
    )
    parser.add_argument(
        "--compat-snapshot",
        dest="compat_snapshot",
        action="store_true",
        help="Write compatibility snapshots to csv_files/compat_faces/commander_cards_unmerged.csv",
    )
    parser.add_argument(
        "--no-compat-snapshot",
        dest="compat_snapshot",
        action="store_false",
        help="Skip writing compatibility snapshots (default).",
    )
    parser.set_defaults(compat_snapshot=None)
    args = parser.parse_args(argv)

    compat_snapshot = _resolve_compat_snapshot(str(args.mode or ""), args.compat_snapshot)
    os.environ.pop("ENABLE_DFC_MERGE", None)
    os.environ["DFC_COMPAT_SNAPSHOT"] = "1" if compat_snapshot else "0"
    importlib.invalidate_caches()

    if not args.skip_setup:
        _refresh_setup()

    _refresh_tags()

    print(_summarize_outputs(compat_snapshot))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
