"""Tests for RandomService.

Covers seed validation, seed derivation, and RNG creation via the service.
"""
from __future__ import annotations

import pytest

from code.exceptions import InvalidSeedError
from code.web.services.random_service import RandomService


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #

@pytest.fixture
def service() -> RandomService:
    return RandomService()


# --------------------------------------------------------------------------- #
# validate_seed                                                                #
# --------------------------------------------------------------------------- #

class TestValidateSeed:
    def test_none_is_valid(self, service):
        service.validate_seed(None)  # should not raise

    def test_positive_int_is_valid(self, service):
        service.validate_seed(0)
        service.validate_seed(1)
        service.validate_seed(12345)
        service.validate_seed((1 << 63) - 1)

    def test_nonempty_string_is_valid(self, service):
        service.validate_seed("dragons")
        service.validate_seed("1")
        service.validate_seed("  ")  # whitespace-only is allowed by service

    def test_negative_int_raises(self, service):
        with pytest.raises(InvalidSeedError) as exc_info:
            service.validate_seed(-1)
        assert exc_info.value.code == "INVALID_SEED"

    def test_empty_string_raises(self, service):
        with pytest.raises(InvalidSeedError):
            service.validate_seed("")

    def test_bool_raises(self, service):
        with pytest.raises(InvalidSeedError):
            service.validate_seed(True)
        with pytest.raises(InvalidSeedError):
            service.validate_seed(False)

    def test_list_raises(self, service):
        with pytest.raises(InvalidSeedError):
            service.validate_seed([1, 2, 3])  # type: ignore

    def test_dict_raises(self, service):
        with pytest.raises(InvalidSeedError):
            service.validate_seed({"seed": 1})  # type: ignore


# --------------------------------------------------------------------------- #
# derive_seed                                                                  #
# --------------------------------------------------------------------------- #

class TestDeriveSeed:
    def test_int_seed_stable(self, service):
        assert service.derive_seed(42) == 42
        assert service.derive_seed(0) == 0

    def test_string_seed_stable(self, service):
        s1 = service.derive_seed("test-seed")
        s2 = service.derive_seed("test-seed")
        assert s1 == s2

    def test_string_seed_known_value(self, service):
        # Same expected value as test_random_util.py
        assert service.derive_seed("test-seed") == 6214070892065607348

    def test_different_strings_differ(self, service):
        a = service.derive_seed("alpha")
        b = service.derive_seed("beta")
        assert a != b

    def test_negative_int_raises(self, service):
        with pytest.raises(InvalidSeedError):
            service.derive_seed(-5)

    def test_result_within_63_bits(self, service):
        for seed in [0, 1, 99999, "hello", "dragons"]:
            result = service.derive_seed(seed)
            assert 0 <= result < (1 << 63)


# --------------------------------------------------------------------------- #
# create_rng                                                                   #
# --------------------------------------------------------------------------- #

class TestCreateRng:
    def test_seeded_rng_is_deterministic(self, service):
        rng1 = service.create_rng(seed=12345)
        rng2 = service.create_rng(seed=12345)
        seq1 = [rng1.random() for _ in range(5)]
        seq2 = [rng2.random() for _ in range(5)]
        assert seq1 == seq2

    def test_string_seeded_rng_is_deterministic(self, service):
        rng1 = service.create_rng(seed="dragons")
        rng2 = service.create_rng(seed="dragons")
        seq1 = [rng1.random() for _ in range(5)]
        seq2 = [rng2.random() for _ in range(5)]
        assert seq1 == seq2

    def test_different_seeds_produce_different_streams(self, service):
        rng1 = service.create_rng(seed=1)
        rng2 = service.create_rng(seed=2)
        seq1 = [rng1.random() for _ in range(10)]
        seq2 = [rng2.random() for _ in range(10)]
        assert seq1 != seq2

    def test_unseeded_returns_independent_instance(self, service):
        rng1 = service.create_rng()
        rng2 = service.create_rng()
        assert rng1 is not rng2

    def test_seeded_rng_is_independent_object(self, service):
        rng1 = service.create_rng(seed=42)
        rng2 = service.create_rng(seed=42)
        assert rng1 is not rng2


# --------------------------------------------------------------------------- #
# generate_seed                                                                #
# --------------------------------------------------------------------------- #

class TestGenerateSeed:
    def test_returns_int_in_range(self, service):
        for _ in range(10):
            s = service.generate_seed()
            assert isinstance(s, int)
            assert 0 <= s < (1 << 63)

    def test_seeds_are_not_all_identical(self, service):
        seeds = {service.generate_seed() for _ in range(5)}
        # With 63-bit entropy collisions are astronomically unlikely
        assert len(seeds) > 1
