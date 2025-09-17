from __future__ import annotations

from deck_builder.builder import DeckBuilder


def test_builder_rng_same_seed_identical_streams():
    b1 = DeckBuilder()
    b1.set_seed('alpha')
    seq1 = [b1.rng.random() for _ in range(5)]

    b2 = DeckBuilder()
    b2.set_seed('alpha')
    seq2 = [b2.rng.random() for _ in range(5)]

    assert seq1 == seq2
