from __future__ import annotations

from random_util import derive_seed_from_string, set_seed, get_random, generate_seed


def test_derive_seed_from_string_stable():
    # Known value derived from SHA-256('test-seed') first 8 bytes masked to 63 bits
    assert derive_seed_from_string('test-seed') == 6214070892065607348
    # Int passthrough-like behavior (normalized to positive 63-bit)
    assert derive_seed_from_string(42) == 42
    assert derive_seed_from_string(-42) == 42


def test_set_seed_deterministic_stream():
    r1 = set_seed('alpha')
    r2 = set_seed('alpha')
    seq1 = [r1.random() for _ in range(5)]
    seq2 = [r2.random() for _ in range(5)]
    assert seq1 == seq2


def test_get_random_unseeded_independent():
    a = get_random()
    b = get_random()
    # Advance a few steps
    _ = [a.random() for _ in range(3)]
    _ = [b.random() for _ in range(3)]
    # They should not be the same object and streams should diverge vs seeded
    assert a is not b


def test_generate_seed_range():
    s = generate_seed()
    assert isinstance(s, int)
    assert s >= 0
    # Ensure it's within 63-bit range
    assert s < (1 << 63)
