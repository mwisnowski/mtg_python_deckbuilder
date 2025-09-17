from deck_builder import builder_utils as bu
from random_util import set_seed


def test_weighted_sample_deterministic_same_seed():
    pool = [("a", 1), ("b", 2), ("c", 3), ("d", 4)]
    k = 3
    rng1 = set_seed(12345)
    sel1 = bu.weighted_sample_without_replacement(pool, k, rng=rng1)
    # Reset to the same seed and expect the same selection order
    rng2 = set_seed(12345)
    sel2 = bu.weighted_sample_without_replacement(pool, k, rng=rng2)
    assert sel1 == sel2


def test_compute_adjusted_target_deterministic_same_seed():
    # Use a simple output func that collects messages (but we don't assert on them here)
    msgs: list[str] = []
    out = msgs.append
    original_cfg = 10
    existing = 4

    rng1 = set_seed(999)
    to_add1, bonus1 = bu.compute_adjusted_target(
        "Ramp", original_cfg, existing, out, plural_word="ramp spells", rng=rng1
    )

    rng2 = set_seed(999)
    to_add2, bonus2 = bu.compute_adjusted_target(
        "Ramp", original_cfg, existing, out, plural_word="ramp spells", rng=rng2
    )

    assert (to_add1, bonus1) == (to_add2, bonus2)
