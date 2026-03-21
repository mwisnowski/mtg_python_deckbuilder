# Random Mode Developer Guide

**Updated**: 2026-03-20

---

## Overview

This guide covers how to use the seeded RNG infrastructure in new code, how to wire seeds through routes and services, and how to test deterministic builds.

See [seed_infrastructure.md](seed_infrastructure.md) for the API reference.

---

## Quick Start

### Reproduce a build from a seed

```python
from code.random_util import set_seed

rng = set_seed(12345)
value = rng.choice(["a", "b", "c"])  # Always the same for seed 12345
```

### Generate a fresh seed

```python
from code.random_util import generate_seed

seed = generate_seed()  # High-entropy 63-bit int
```

### Use the service (preferred in route handlers)

```python
from code.web.services.random_service import RandomService

service = RandomService()
rng = service.create_rng(seed=12345)
```

---

## Integration Examples

### 1. Seeded random build (headless / CLI)

```python
from code.deck_builder.random_entrypoint import build_random_full_deck

result = build_random_full_deck(
    seed=12345,
    theme="dragons",
    color_identity=["R", "G"],
    # ...
)
print(result.seed)  # 12345
```

### 2. Web route handler with seed from request

```python
# code/web/app.py or a route file
from code.web.services.random_service import RandomService

async def my_random_route(request: Request):
    body = await request.json()
    raw_seed = body.get("seed")          # int, str, or None

    service = RandomService()
    service.validate_seed(raw_seed)      # raises InvalidSeedError on bad input
    seed = service.derive_seed(raw_seed) if raw_seed is not None else service.generate_seed()

    rng = service.create_rng(seed)
    # ... pass rng or seed into build function
```

### 3. Builder-level seeding

```python
from code.deck_builder.builder import DeckBuilder

builder = DeckBuilder(...)
builder.set_seed(99999)          # builder.rng is now seeded

cards = builder.rng.sample(card_pool, 10)  # Reproducible sample
```

### 4. Reroll (increment seed)

```python
old_seed = session.get("random_seed")
new_seed = (old_seed + 1) & ((1 << 63) - 1)   # Stay in 63-bit range
session["random_seed"] = new_seed
```

---

## Seed Validation Rules

| Input | Valid? | Notes |
|-------|--------|-------|
| `42` | Yes | Non-negative int |
| `-1` | No | Negative int → `InvalidSeedError` |
| `"dragons"` | Yes | String → SHA-256 derivation |
| `""` | No | Empty string → `InvalidSeedError` |
| `None` | Yes | Triggers auto-generation |
| `[]` or `{}` | No | Wrong type → `InvalidSeedError` |

---

## Error Handling

```python
from code.exceptions import InvalidSeedError
from code.web.services.random_service import RandomService

service = RandomService()
try:
    service.validate_seed(user_input)
except InvalidSeedError as e:
    return {"error": str(e), "code": e.code}
```

---

## Testing Deterministic Code

### Assert two builds produce the same result

```python
def test_build_is_deterministic():
    result1 = build_random_full_deck(seed=42, ...)
    result2 = build_random_full_deck(seed=42, ...)
    assert result1.commander == result2.commander
```

### Assert different seeds produce different results (probabilistic)

```python
def test_different_seeds_differ():
    result1 = build_random_full_deck(seed=1, ...)
    result2 = build_random_full_deck(seed=2, ...)
    # Not guaranteed, but highly likely for large pools
    assert result1.commander != result2.commander or result1.theme != result2.theme
```

### Test seed derivation stability

```python
from code.random_util import derive_seed_from_string

def test_string_seed_stable():
    s1 = derive_seed_from_string("test")
    s2 = derive_seed_from_string("test")
    assert s1 == s2

def test_int_and_string_differ():
    assert derive_seed_from_string(0) != derive_seed_from_string("0")
```

---

## Diagnostics

When `WEB_RANDOM_DIAGNOSTICS=1` is set, the endpoint `/api/random/diagnostics` returns seed derivation test vectors and algorithm metadata. Useful for verifying cross-platform consistency.

```bash
WEB_RANDOM_DIAGNOSTICS=1 curl http://localhost:5000/api/random/diagnostics
```

---

## Related Files

| File | Purpose |
|------|---------|
| `code/random_util.py` | Core RNG utilities |
| `code/web/services/random_service.py` | Service wrapper with validation |
| `code/exceptions.py` | `InvalidSeedError` |
| `code/deck_builder/random_entrypoint.py` | `build_random_deck`, `build_random_full_deck` |
| `code/deck_builder/builder.py` | `DeckBuilder.seed` / `DeckBuilder.rng` |
| `docs/random_mode/seed_infrastructure.md` | API reference |
| `docs/random_mode/diagnostics.md` | Diagnostics endpoint reference |
