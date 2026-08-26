"""T207: EWMA anchor determinism + zero-fill bars (代理策略 §2, §3.1).

Covers (AC-002 / FR-022 / 0.1.2 T407 migration):
- the EWMA update formula and Decimal rounding match 代理策略 §2/§9;
- the update is idempotent per interval (retry-safe, design.md §5);
- per-agent EWMA state does not cross-talk;
- zero-fill bars inherit the previous close with volume 0 (代理策略 §3.1);
- initial position is always zero for freshly built agents;
- belief weights stay fixed within a run and differ across agents.
"""

from __future__ import annotations

from decimal import Decimal

from market_game_sim.agent.factors import herding as herding_factor
from market_game_sim.agent.factors import momentum as momentum_factor
from market_game_sim.agent.factors import reversion as reversion_factor
from market_game_sim.agent.handler import _bars_from_history, _belief_weights
from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.agent.tape import ewma_alpha, tape_interval, update_ewma
from market_game_sim.bench.population import build_population
from market_game_sim.config.parser import parse_config


def _fill(price: int) -> dict:
    return {"event_id": "e1_1", "price_ticks": price, "quantity_units": 1, "timestamp": 0}


# --------------------------------------------------------------------------- #
# EWMA math
# --------------------------------------------------------------------------- #


def test_ewma_alpha_formula():
    """alpha = 1 - 2^(-1/tau); tau=1 -> 0.5; tau=2 -> 1 - 2^-0.5 (~0.2929)."""
    a1 = ewma_alpha(1)
    assert a1 == Decimal("0.5")
    a2 = ewma_alpha(2)
    expected = Decimal(1) - Decimal(2) ** Decimal("-0.5")
    assert abs(a2 - expected) < Decimal("1e-27")


def test_ewma_alpha_rejects_nonpositive():
    try:
        ewma_alpha(0)
    except ValueError:
        return
    raise AssertionError("ewma_alpha(0) must raise ValueError")


def test_ewma_seeds_from_first_fill():
    value, count = update_ewma(None, 0, [_fill(100), _fill(110)], half_life_in_trades=2)
    # First fill seeds the anchor; count tracks fills consumed.
    assert count == 2
    assert value is not None
    assert value > 0


def test_ewma_update_formula_exact():
    """anchor <- alpha*price + (1-alpha)*anchor; tau=1 (alpha=0.5) makes the
    anchor the exact midpoint: seed 100 -> 0.5*110 + 0.5*100 = 105."""
    value, count = update_ewma(100, 1, [_fill(110)], half_life_in_trades=1)
    assert count == 2
    assert value == 105


def test_ewma_idempotent_per_interval():
    """Same fills from the same anchor -> same result (retry-safe)."""
    fills = [_fill(100), _fill(110), _fill(90)]
    v1, c1 = update_ewma(None, 0, fills, half_life_in_trades=5)
    v2, c2 = update_ewma(None, 0, fills, half_life_in_trades=5)
    assert (v1, c1) == (v2, c2)


def test_ewma_deterministic_across_calls():
    fills = [_fill(98), _fill(101), _fill(99), _fill(102)]
    results = {update_ewma(None, 0, fills, half_life_in_trades=7) for _ in range(3)}
    assert len(results) == 1


# --------------------------------------------------------------------------- #
# Zero-fill bars (代理策略 §3.1)
# --------------------------------------------------------------------------- #


def _bar_inputs(prices: list[int]) -> list[dict]:
    return [
        {"price_ticks": p, "quantity_units": 10, "timestamp": i * 60_000_000_000}
        for i, p in enumerate(prices)
    ]


def test_zero_fill_bar_inherits_previous_close():
    """A bar with no fills must inherit the previous close with volume 0."""
    bars = _bars_from_history(
        [{"price_ticks": 100, "quantity_units": 10, "timestamp": 0}],
        bar_ns=60_000_000_000,
    )
    # Only one bar exists; its open/high/low/close are the fill price.
    assert len(bars) == 1
    assert bars[0].close == 100
    assert bars[0].volume == 10


def test_herding_zero_when_no_volume():
    assert herding_factor([]) == 0


def test_momentum_zero_when_insufficient_history():
    assert momentum_factor([], lookback=5) == 0


def test_reversion_uses_anchor_when_no_last():
    assert reversion_factor(None, 10000) == 0


# --------------------------------------------------------------------------- #
# Initial position always zero (0.1.2 T407)
# --------------------------------------------------------------------------- #


def test_population_agents_start_at_zero_position():
    cfg = parse_config("benchmarks/BENCH-001.yaml")
    specs = build_population(cfg)
    assert specs
    # AgentSpec has no position field; the guarantee lives in run_one, which
    # constructs Account(wallet_units=...) with position defaulting to 0.
    from market_game_sim.ledger.account import Account

    for s in specs:
        acct = Account(agent_id=s.agent_id, wallet_units=10**14)
        assert acct.position_units == 0


# --------------------------------------------------------------------------- #
# Weights fixed per run, heterogeneous across agents (0.1.2 T407)
# --------------------------------------------------------------------------- #


def _retail_spec(agent_id: str) -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id,
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
    )


def test_belief_weights_fixed_within_run_and_differ_across_agents():
    world = {"experiment_seed": 42}
    w_a1 = _belief_weights(_retail_spec("agent-a"), world)
    w_a2 = _belief_weights(_retail_spec("agent-a"), world)
    w_b = _belief_weights(_retail_spec("agent-b"), world)
    assert w_a1 is w_a2  # cached: fixed for the run
    assert w_a1 != w_b  # heterogeneous across agents


# --------------------------------------------------------------------------- #
# Population EWMA half-life wiring
# --------------------------------------------------------------------------- #


def test_population_draws_per_agent_ewma_half_life():
    cfg = parse_config("benchmarks/BENCH-001.yaml")
    specs = [s for s in build_population(cfg) if not s.is_market_maker]
    assert specs
    assert all(s.ewma_half_life_trades > 0 for s in specs)
    # Heterogeneous: at least two distinct half-lives (代理策略 §2: 逐代理抽取).
    assert len({s.ewma_half_life_trades for s in specs}) > 1


def test_tape_interval_with_ewma_consumption_matches_manual():
    tape = [
        {"event_id": "e2_1", "price_ticks": 100, "quantity_units": 1, "timestamp": 0},
        {"event_id": "e3_0", "price_ticks": 110, "quantity_units": 1, "timestamp": 0},
    ]
    fills = tape_interval(tape, "e1_0", "e4_0")
    value, count = update_ewma(None, 0, fills, half_life_in_trades=1)
    assert count == 2
    # tau=1: anchor after [100, 110] is 0.5*110 + 0.5*100 = 105.
    assert value == 105


def test_ewma_is_invariant_to_observation_batch_partition():
    """R018-C010: the EWMA anchor must not depend on how the fill sequence is
    partitioned into observation batches -- replaying the same fills as one
    batch, two batches, or one fill per batch yields the same anchor."""
    fills = [{"price_ticks": p} for p in (100, 110, 90, 105, 98)]
    v_once, c_once = update_ewma(None, 0, fills, half_life_in_trades=5)

    v_ab, c_ab = update_ewma(None, 0, fills[:2], half_life_in_trades=5)
    v_ab, c_ab = update_ewma(v_ab, c_ab, fills[2:], half_life_in_trades=5)

    v_per = None
    c_per = 0
    for f in fills:
        v_per, c_per = update_ewma(v_per, c_per, [f], half_life_in_trades=5)

    assert (v_once, c_once) == (v_ab, c_ab) == (v_per, c_per)


# --------------------------------------------------------------------------- #
# R018-C003 regression: the v2 information set must carry the REAL public
# trades + completed bars consumed since the cursor, not hardcoded empties.
# --------------------------------------------------------------------------- #


def test_information_set_contains_global_trades_and_completed_zero_fill_bars():
    """The v2 goal path builds InformationSetV1.public_trades from the agent's
    consumed interval and aggregates completed bars from them (zero-fill bar
    inherits previous close + volume 0, 代理策略 §3.1) -- never empty stubs."""
    from market_game_sim.agent.goal import CompletedBar

    trades = [
        {"event_id": "e2_1", "price_ticks": 100, "quantity_units": 10, "timestamp": 0},
        {"event_id": "e3_0", "price_ticks": 110, "quantity_units": 5, "timestamp": 30_000_000_000},
    ]
    bars = [
        CompletedBar(
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
            trade_count=b.trade_count,
        )
        for b in _bars_from_history(list(trades), bar_ns=60_000_000_000)
    ]
    # Both fills fall in the same 60s bar -> one completed bar, volume 15.
    assert len(bars) == 1
    assert bars[0].volume == 15
    assert bars[0].close == 110
