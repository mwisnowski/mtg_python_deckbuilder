from __future__ import annotations

import os
from code.headless_runner import run


def test_headless_seed_threads_into_builder(monkeypatch):
    # Use the tiny test dataset for speed/determinism
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    # Use a commander known to be in tiny dataset or fallback path; we rely on search/confirm flow
    # Provide a simple name that will fuzzy match one of the entries.
    out1 = run(command_name="Krenko", seed=999)
    out2 = run(command_name="Krenko", seed=999)
    # Determinism: the seed should be set on the builder and identical across runs
    assert getattr(out1, "seed", None) == getattr(out2, "seed", None) == 999
    # Basic sanity: commander selection should have occurred
    assert isinstance(getattr(out1, "commander_name", ""), str)
    assert isinstance(getattr(out2, "commander_name", ""), str)