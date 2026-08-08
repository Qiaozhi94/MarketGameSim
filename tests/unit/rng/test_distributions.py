"""T301, T302, T304: RNG distribution tests against golden vectors (代理策略 §10)."""

from __future__ import annotations

from decimal import Decimal

from market_game_sim.rng.distributions import (
    blake2b_uniform,
    dirichlet_draw,
    discrete_choice,
    gamma_draw,
    lognormal_draw,
    standard_normal,
    uniform_range,
)


def test_blake2b_uniform_in_open_interval():
    u = blake2b_uniform(42, "agent-000", "test", 0, 0)
    assert 0 < u < 1


def test_blake2b_uniform_deterministic():
    u1 = blake2b_uniform(42, "agent-000", "test", 0, 0)
    u2 = blake2b_uniform(42, "agent-000", "test", 0, 0)
    assert u1 == u2


def test_blake2b_uniform_different_keys_differ():
    u1 = blake2b_uniform(42, "agent-000", "test", 0, 0)
    u2 = blake2b_uniform(42, "agent-000", "test", 0, 1)
    assert u1 != u2


def test_blake2b_uniform_collision_free_for_delimiter_collision():
    u1 = blake2b_uniform(42, "x|y", "noise", 0, 0)
    u2 = blake2b_uniform(42, "x", "y|noise", 0, 0)
    assert u1 != u2


def test_standard_normal_returns_value_and_next_index():
    z, next_idx = standard_normal(42, "agent-000", "noise_factor", 0, 0)
    assert isinstance(z, Decimal)
    assert next_idx > 0


def test_standard_normal_deterministic():
    z1, idx1 = standard_normal(42, "agent-000", "noise_factor", 0, 0)
    z2, idx2 = standard_normal(42, "agent-000", "noise_factor", 0, 0)
    assert z1 == z2
    assert idx1 == idx2


def test_gamma_draw_returns_positive_value():
    g, _ = gamma_draw(Decimal("2.0"), 42, "agent-000", "belief_weights_0", 0, 0)
    assert g > 0


def test_gamma_draw_alpha_less_than_one():
    g, _ = gamma_draw(Decimal("0.5"), 42, "agent-000", "belief_weights_0", 0, 0)
    assert g > 0


def test_dirichlet_draw_sums_to_one():
    alpha = [Decimal("1.0"), Decimal("1.0"), Decimal("0.8"), Decimal("0.8"), Decimal("1.5")]
    w, _ = dirichlet_draw(alpha, 42, "agent-000", "belief_weights", 0)
    assert len(w) == 5
    s = sum(w, Decimal(0))
    assert abs(s - Decimal(1)) < Decimal("1e-20")


def test_dirichlet_draw_golden_vector():
    """代理策略 §10.3.4 golden vector: master_seed=42, agent-000, alpha=[1.0,1.0,0.8,0.8,1.5]."""
    alpha = [Decimal("1.0"), Decimal("1.0"), Decimal("0.8"), Decimal("0.8"), Decimal("1.5")]
    w, _ = dirichlet_draw(alpha, 42, "agent-000", "belief_weights", 0)
    expected = [
        Decimal("0.1263946241600740412702771089"),
        Decimal("0.2512845414401946144867249532"),
        Decimal("0.2279915631952186024773230701"),
        Decimal("0.01823517847453035830910800003"),
        Decimal("0.3760940927299823834565668676"),
    ]
    for i, (got, exp) in enumerate(zip(w, expected, strict=True)):
        assert abs(got - exp) < Decimal("1e-25"), f"component {i}: {got} != {exp}"


def test_dirichlet_draw_independent_mechanisms():
    """Different agents draw different samples from the same alpha (independence)."""
    alpha_a = [Decimal("1.0"), Decimal("1.0"), Decimal("1.0")]
    alpha_b = [Decimal("1.0"), Decimal("1.0"), Decimal("1.0")]
    w_a, _ = dirichlet_draw(alpha_a, 42, "a", "x", 0)
    w_b, _ = dirichlet_draw(alpha_b, 42, "b", "x", 0)
    assert w_a != w_b


def test_dirichlet_draw_deterministic_per_agent():
    """Same agent+alpha gives same sample (reproducibility per agent)."""
    alpha = [Decimal("1.0"), Decimal("1.0"), Decimal("1.0")]
    w1, _ = dirichlet_draw(alpha, 42, "a", "x", 0)
    w2, _ = dirichlet_draw(alpha, 42, "a", "x", 0)
    assert w1 == w2


def test_lognormal_draw_positive():
    v, _ = lognormal_draw(200, Decimal("0.5"), 42, "agent-000", "half_life", 0, 0)
    assert v > 0


def test_uniform_range_in_bounds():
    v, _ = uniform_range(
        Decimal("0.0"),
        Decimal("1.0"),
        42,
        "agent-000",
        "aggressiveness",
        0,
        0,
    )
    assert Decimal("0.0") <= v < Decimal("1.0")


def test_discrete_choice_returns_key():
    weights = {1: 6000, 3: 3000, 10: 1000}
    k, _ = discrete_choice(weights, 42, "agent-000", "leverage_tier", 0, 0)
    assert k in {1, 3, 10}


def test_discrete_choice_numerically_sorted():
    weights = {1: 0, 3: 0, 10: 10000}
    k, _ = discrete_choice(weights, 42, "agent-000", "leverage_tier", 0, 0)
    assert k == 10


def test_discrete_choice_distribution_respected():
    weights = {1: 5000, 3: 5000}
    counts = {1: 0, 3: 0}
    n = 200
    for i in range(n):
        k, _ = discrete_choice(weights, 42, "agent-000", "leverage_tier", i, 0)
        counts[k] += 1
    assert abs(counts[1] - counts[3]) < n // 4
