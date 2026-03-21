# Seed Infrastructure

**Module**: `code/random_util.py`  
**Updated**: 2026-03-20

---

## Overview

Random Mode builds use a deterministic, seeded RNG so that any build can be exactly reproduced from its seed value. Every random operation flows through isolated `random.Random` instances — the module-level PRNG is never mutated.

---

## Core Components

### `code/random_util.py`

| Function | Signature | Description |
|----------|-----------|-------------|
| `derive_seed_from_string` | `(seed: int \| str) -> int` | Stable 63-bit seed from int or string (SHA-256 for strings) |
| `set_seed` | `(seed: int \| str) -> random.Random` | Create a seeded `Random` instance |
| `get_random` | `(seed: int \| str \| None) -> random.Random` | Convenience wrapper; unseeded when `None` |
| `generate_seed` | `() -> int` | High-entropy 63-bit seed via `secrets.randbits` |

### `code/web/services/random_service.py`

Thin service wrapper following the R9 `BaseService` pattern. Adds input validation and a standardised interface for route handlers.

| Method | Description |
|--------|-------------|
| `derive_seed(seed)` | Validated seed derivation (raises `InvalidSeedError` on bad input) |
| `create_rng(seed)` | Return seeded or unseeded `random.Random` |
| `generate_seed()` | Delegates to `random_util.generate_seed()` |
| `validate_seed(seed)` | Validates type and range; raises `InvalidSeedError` |

---

## Seed Types

### Integer seeds
- Must be non-negative
- Normalised to 63-bit via `abs(n) & ((1 << 63) - 1)`
- Zero is a valid, deterministic seed

### String seeds
- Encoded as UTF-8 bytes
- Hashed with SHA-256; first 8 bytes taken as big-endian unsigned int
- Masked to 63 bits for consistency with int path
- Empty string is valid (produces a fixed deterministic seed)

### None (auto-seed)
- `get_random(None)` returns an unseeded `random.Random()`
- `generate_seed()` returns a fresh `secrets.randbits(63)` value each call

---

## Integration Points

### DeckBuilder
```python
# code/deck_builder/builder.py
builder = DeckBuilder(...)
builder.set_seed(12345)          # Sets builder.seed and recreates builder.rng
rng = builder.rng                # Seeded random.Random instance
```

### Random entrypoint
```python
# code/deck_builder/random_entrypoint.py
result = build_random_full_deck(
    seed=12345,
    theme="dragons",
    # ...
)
# result.seed == 12345 (or auto-generated if None was passed)
```

### CLI
```bash
python code/headless_runner.py --random-seed 12345
# or via environment variable
RANDOM_SEED=12345 python code/headless_runner.py
# or in deck.json config
{ "random_seed": 12345 }
```
Seed resolution order: `--random-seed` CLI arg > `RANDOM_SEED` env var > `random_seed` in JSON config.

### Web UI
- Seed input field on the Random Build page
- Seed persisted in session across rerolls
- Reroll increments the seed by 1 for deterministic variation (`seed + 1`)
- Favorite seeds stored in session for quick reuse

---

## Edge Cases

| Scenario | Behaviour |
|----------|-----------|
| Negative int seed | Normalised via `abs()` before masking |
| `MAX_INT` seed | Masked to 63 bits — stays valid |
| Empty string `""` | Valid; SHA-256 hash of empty bytes used |
| String with special chars / Unicode | UTF-8 encoded; `errors="strict"`, fallback to `errors="ignore"` |
| `None` seed | Unseeded `random.Random()` — non-deterministic |

---

## Testing

| File | Coverage |
|------|----------|
| `code/tests/test_random_util.py` | Core function contracts |
| `code/tests/test_random_determinism_comprehensive.py` | End-to-end determinism validation |
| `code/tests/test_random_features_comprehensive.py` | Random mode feature integration |
| `code/tests/test_random_api_comprehensive.py` | API-level behaviour |
| `code/tests/test_random_service.py` | `RandomService` unit tests |

Run the fast subset:
```powershell
.venv/Scripts/python.exe -m pytest -q code/tests/test_random_util.py code/tests/test_random_service.py
```
