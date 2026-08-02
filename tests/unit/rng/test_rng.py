"""T601: RNG tests (uniform, determinism)."""

from market_game_sim.rng import uniform


def test_uniform_range():
    for i in range(100):
        v = uniform(b"test-seed", i)
        assert 0.0 <= v < 1.0


def test_deterministic():
    a = uniform(b"seed", 0)
    b = uniform(b"seed", 0)
    assert a == b


def test_different_counter_different_value():
    a = uniform(b"seed", 0)
    b = uniform(b"seed", 1)
    assert a != b


def test_different_seed_different_value():
    a = uniform(b"A", 0)
    b = uniform(b"B", 0)
    assert a != b
