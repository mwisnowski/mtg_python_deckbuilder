from __future__ import annotations

import hashlib
import secrets
import random
from typing import Union

"""
Seeded RNG utilities for deterministic behavior.

Contract (minimal):
- derive_seed_from_string(s): produce a stable, platform-independent int seed from a string or int.
- set_seed(seed): return a new random.Random instance seeded deterministically.
- generate_seed(): return a high-entropy, non-negative int suitable for seeding.
- get_random(seed=None): convenience to obtain a new Random instance (seeded when provided).

No globals/state: each call returns an independent Random instance.
"""


SeedLike = Union[int, str]


def _to_bytes(s: str) -> bytes:
    try:
        return s.encode("utf-8", errors="strict")
    except Exception:
        # Best-effort fallback
        return s.encode("utf-8", errors="ignore")


def derive_seed_from_string(seed: SeedLike) -> int:
    """Derive a stable positive integer seed from a string or int.

    - int inputs are normalized to a non-negative 63-bit value.
    - str inputs use SHA-256 to generate a deterministic 63-bit value.
    """
    if isinstance(seed, int):
        # Normalize to 63-bit positive
        return abs(int(seed)) & ((1 << 63) - 1)
    # String path: deterministic, platform-independent
    data = _to_bytes(str(seed))
    h = hashlib.sha256(data).digest()
    # Use first 8 bytes (64 bits) and mask to 63 bits to avoid sign issues
    n = int.from_bytes(h[:8], byteorder="big", signed=False)
    return n & ((1 << 63) - 1)


def set_seed(seed: SeedLike) -> random.Random:
    """Return a new Random instance seeded deterministically from the given seed."""
    r = random.Random()
    r.seed(derive_seed_from_string(seed))
    return r


def get_random(seed: SeedLike | None = None) -> random.Random:
    """Return a new Random instance; seed when provided.

    This avoids mutating the module-global PRNG and keeps streams isolated.
    """
    if seed is None:
        return random.Random()
    return set_seed(seed)


def generate_seed() -> int:
    """Return a high-entropy positive 63-bit integer suitable for seeding."""
    # secrets is preferred for entropy here; mask to 63 bits for consistency
    return secrets.randbits(63)
