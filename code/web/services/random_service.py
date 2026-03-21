"""Service wrapper for deterministic seeded RNG operations.

Follows the R9 BaseService pattern. Route handlers should prefer this
over calling random_util functions directly so that validation and error
handling are centralised.
"""
from __future__ import annotations

import random
from typing import Optional, Union

from code.exceptions import InvalidSeedError
from code.random_util import (
    derive_seed_from_string,
    generate_seed as _generate_seed,
    get_random,
)
from code.web.services.base import BaseService

SeedLike = Union[int, str]


class RandomService(BaseService):
    """Service for deterministic random build operations.

    All methods return independent ``random.Random`` instances so that
    concurrent requests cannot pollute each other's RNG stream.
    """

    # ------------------------------------------------------------------ #
    # Validation                                                           #
    # ------------------------------------------------------------------ #

    def validate_seed(self, seed: Optional[SeedLike]) -> None:
        """Validate that *seed* is an acceptable type and value.

        Args:
            seed: The seed to validate.  ``None`` is always valid (triggers
                auto-generation at build time).

        Raises:
            InvalidSeedError: If the seed is the wrong type, negative, or
                an empty string.
        """
        if seed is None:
            return

        if isinstance(seed, bool):
            # bool is a subclass of int in Python — reject explicitly
            raise InvalidSeedError(
                "Seed must be an integer or string, not bool",
                details={"seed": str(seed), "type": type(seed).__name__},
            )

        if isinstance(seed, int):
            if seed < 0:
                raise InvalidSeedError(
                    f"Integer seed must be non-negative, got {seed}",
                    details={"seed": seed},
                )
            return

        if isinstance(seed, str):
            if not seed:
                raise InvalidSeedError(
                    "String seed cannot be empty",
                    details={"seed": seed},
                )
            return

        raise InvalidSeedError(
            f"Seed must be an int or str, got {type(seed).__name__}",
            details={"seed": str(seed), "type": type(seed).__name__},
        )

    # ------------------------------------------------------------------ #
    # Seed derivation                                                      #
    # ------------------------------------------------------------------ #

    def derive_seed(self, seed: SeedLike) -> int:
        """Derive a stable 63-bit positive integer from *seed*.

        Delegates to :func:`random_util.derive_seed_from_string` after
        validating the input.

        Args:
            seed: Integer or string seed value.

        Returns:
            A stable non-negative 63-bit integer.

        Raises:
            InvalidSeedError: If *seed* fails validation.
        """
        self.validate_seed(seed)
        try:
            return derive_seed_from_string(seed)
        except Exception as exc:
            raise InvalidSeedError(
                f"Failed to derive seed from {type(seed).__name__}",
                details={"seed": str(seed), "error": str(exc)},
            ) from exc

    # ------------------------------------------------------------------ #
    # RNG creation                                                         #
    # ------------------------------------------------------------------ #

    def create_rng(self, seed: Optional[SeedLike] = None) -> random.Random:
        """Return a ``random.Random`` instance, optionally seeded.

        Args:
            seed: Integer or string seed.  Pass ``None`` for an unseeded
                (non-deterministic) instance.

        Returns:
            An independent ``random.Random`` instance.
        """
        return get_random(seed)

    # ------------------------------------------------------------------ #
    # Seed generation                                                      #
    # ------------------------------------------------------------------ #

    def generate_seed(self) -> int:
        """Generate a high-entropy 63-bit seed.

        Returns:
            A fresh positive integer via ``secrets.randbits(63)``.
        """
        return _generate_seed()
