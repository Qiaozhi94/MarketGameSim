"""bench/leverage_seed.py: structural + conservation tests.

NOT a test that this triggers real liquidations end-to-end (that's
tests/unit/bench/test_runner.py's calibrated-mode test). These lock the
account-construction contract: correct unit conversion, C1 balance against
the counterparty, and the staggering behavior the chain-depth calibration
depends on.
"""

from __future__ import annotations

from market_game_sim.bench.leverage_seed import build_leveraged_victims


def test_produces_requested_count_plus_one_counterparty():
    positions = build_leveraged_victims(count=5)
    assert len(positions) == 6
    assert "bench-victim-counterparty" in positions


def test_c1_balances_against_the_counterparty():
    positions = build_leveraged_victims(count=7, position_human=500, stagger_position_step=3)
    total = sum(p["position_units"] for p in positions.values())
    assert total == 0


def test_wallet_and_notional_unit_conversion_matches_case7():
    """acceptance-vectors.md 案例7: wallet=5000 human -> 5e11 cash_units;
    position=500 human @ price 100 -> 5e5 position_units, entry_notional
    5e12 cash_units (already verified against the real engine in
    TestCase7PartialLiquidationRecalc)."""
    positions = build_leveraged_victims(
        count=1, wallet_human=5_000, position_human=500, entry_price_human=100
    )
    v0 = positions["bench-victim-0"]
    assert v0["wallet_units"] == 5_000 * 10**8
    assert v0["position_units"] == 500 * 1_000
    assert v0["entry_notional_units"] == 500 * 1_000 * (100 * 100) * 1_000


def test_short_side_negates_position_and_entry():
    long_positions = build_leveraged_victims(count=1, side="LONG")
    short_positions = build_leveraged_victims(count=1, side="SHORT")
    long_v = long_positions["bench-victim-0"]
    short_v = short_positions["bench-victim-0"]
    assert short_v["position_units"] == -long_v["position_units"]
    assert short_v["entry_notional_units"] == -long_v["entry_notional_units"]


def test_stagger_step_zero_gives_identical_positions():
    positions = build_leveraged_victims(count=4, position_human=500, stagger_position_step=0)
    sizes = {positions[f"bench-victim-{i}"]["position_units"] for i in range(4)}
    assert len(sizes) == 1  # negative case: no stagger, no spread


def test_stagger_step_positive_spreads_position_sizes():
    positions = build_leveraged_victims(count=4, position_human=500, stagger_position_step=10)
    sizes = [positions[f"bench-victim-{i}"]["position_units"] for i in range(4)]
    assert sizes == sorted(sizes)
    assert len(set(sizes)) == 4  # positive case: each victim gets a distinct threshold


def test_counterparty_wallet_is_large_enough_to_never_breach():
    positions = build_leveraged_victims(count=10, wallet_human=5_000, position_human=500)
    victim_wallet = positions["bench-victim-0"]["wallet_units"]
    assert positions["bench-victim-counterparty"]["wallet_units"] > victim_wallet * 10
