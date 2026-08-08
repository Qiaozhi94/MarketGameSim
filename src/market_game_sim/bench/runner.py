"""T701-T703: BENCH-001 end-to-end runner.

Loads a benchmark config (BENCH-001.yaml), builds the agent population,
runs it through the real experiment kernel once, and reports the three
judgement layers from benchmarks/README.md §2:

1. throughput / wall-clock (caller applies CalibrationRatio.normalize to
   get the §2 第一层 normalized-seconds judgement -- this module does not
   assume a frozen reference-machine timing exists yet, see calib.py);
2. ``book_operation_count`` (§2 第二层, hardware-independent regression
   signal -- comparison against a frozen ``book_operations_golden`` is the
   caller's responsibility once that value has been formally calibrated);
3. coverage assertions (§1.1 -- a run whose coverage is not valid must not
   be used for either of the above, regardless of how fast it ran).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from market_game_sim.bench.coverage import CoverageAssertions, compute_coverage
from market_game_sim.bench.leverage_seed import build_leveraged_victims
from market_game_sim.bench.population import build_population
from market_game_sim.bench.shock import build_shock_series
from market_game_sim.config.parser import ParsedConfig, parse_config
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.experiment.runner import RunResult, run_one

# T701/E5-E6 calibration: empirically found to satisfy all five README §1.1
# coverage assertions (liquidation, chained liquidation, partial fill,
# cancel, one-sided book) against BENCH-001.yaml's default 190-agent
# population, deterministically (verified: identical coverage counts across
# repeated runs of the same config). See docs/experiments/
# 0.1.2-exit-evidence-index.json's E5 entry for the calibration trace this
# was derived from -- these are tuned for THIS population; a substantially
# different participant mix would need re-tuning, not just re-use.
_CALIBRATED_VICTIM_KW = {
    "count": 20,
    "wallet_human": 5_000,
    "position_human": 500,
    "entry_price_human": 100,
    "stagger_position_step": 5,
}
_CALIBRATED_SHOCK_KW = {
    "side": "SELL",
    "quantity_units_per_shock": 1_500_000,
    "count": 150,
    "interval_ns": 50_000_000,
}


def build_experiment_config(parsed: ParsedConfig, *, calibrated: bool = False) -> ExperimentConfig:
    """Bridge a parsed BENCH-001-shaped config into the experiment runner's
    ``ExperimentConfig``.

    ``mult`` uses the same ``tick_size * min_quantity / cash_unit`` formula
    as ``book/simulator.py::run_simulation``'s ``config`` branch (ADR-001
    cash_unit scaling) -- both derive it from the same three
    ``MarketConfig`` fields; kept as a duplicated one-liner rather than a
    shared helper to avoid touching the already-tested simulator module.

    ``calibrated=True`` adds the pre-positioned leveraged accounts
    (``bench/leverage_seed.py``) and sustained forcing trades
    (``bench/shock.py``) needed for the coverage assertions to actually be
    exercised (see module docstring) -- belief-agent/market-maker research
    configs never set this, and the underlying population/decision logic is
    unaffected either way.
    """
    market = parsed.market
    mult = int(market.tick_size * market.min_quantity / market.cash_unit)
    cfg = ExperimentConfig(
        seed=parsed.random.master_seed,
        max_transactions=parsed.termination.max_transactions,
        initial_price_ticks=market.initial_price_ticks,
        mult=mult,
        maker_bps=market.fees.maker_bps,
        taker_bps=market.fees.taker_bps,
        maint_bp=parsed.margin.maint_bp,
        target_bp=parsed.margin.target_bp,
        liquidation_latency_ns=parsed.margin.liquidation_latency_ns,
        agent_specs=build_population(parsed),
    )
    if calibrated:
        victims = build_leveraged_victims(**_CALIBRATED_VICTIM_KW)
        extra_accounts, extra_events = build_shock_series(**_CALIBRATED_SHOCK_KW)
        cfg.extra_positions = victims
        cfg.extra_accounts = extra_accounts
        cfg.extra_events = extra_events
    return cfg


@dataclass
class BenchmarkResult:
    terminated: str
    wall_seconds: float
    max_transactions: int
    transactions_per_second: float
    event_record_count: int
    event_records_per_second: float
    book_operation_count: int
    coverage: CoverageAssertions
    coverage_failures: list[str]

    @property
    def coverage_valid(self) -> bool:
        return not self.coverage_failures

    def as_dict(self) -> dict:
        return {
            "terminated": self.terminated,
            "wall_seconds": self.wall_seconds,
            "max_transactions": self.max_transactions,
            "transactions_per_second": self.transactions_per_second,
            "event_record_count": self.event_record_count,
            "event_records_per_second": self.event_records_per_second,
            "book_operation_count": self.book_operation_count,
            "coverage_valid": self.coverage_valid,
            "coverage_failures": list(self.coverage_failures),
            "coverage": {
                "liquidations": self.coverage.liquidations,
                "chained_liquidations": self.coverage.chained_liquidations,
                "partial_fills": self.coverage.partial_fills,
                "cancels": self.coverage.cancels,
                "one_sided_book_events": self.coverage.one_sided_book_events,
            },
        }


def _build_result(
    exp_config: ExperimentConfig, run: RunResult, wall_seconds: float
) -> BenchmarkResult:
    n_tx = exp_config.max_transactions
    n_events = len(run.events)
    coverage = compute_coverage(run.events, run.liquidation_metrics)
    return BenchmarkResult(
        terminated=run.terminated,
        wall_seconds=wall_seconds,
        max_transactions=n_tx,
        transactions_per_second=(n_tx / wall_seconds) if wall_seconds > 0 else 0.0,
        event_record_count=n_events,
        event_records_per_second=(n_events / wall_seconds) if wall_seconds > 0 else 0.0,
        book_operation_count=run.book_operation_count,
        coverage=coverage,
        coverage_failures=coverage.failures(),
    )


def run_benchmark_config(parsed: ParsedConfig, *, calibrated: bool = False) -> BenchmarkResult:
    """Run an already-parsed config once and report timing/coverage.

    Timing wraps ``run_one`` only (not config parsing/population building),
    matching README §1's "归一化墙钟时间" scope -- the thing being timed is
    the kernel run, not I/O or setup. ``calibrated=True`` is required for
    the coverage assertions to actually pass (see ``build_experiment_config``).
    """
    exp_config = build_experiment_config(parsed, calibrated=calibrated)
    start = time.perf_counter()
    run = run_one(exp_config)
    wall_seconds = time.perf_counter() - start
    return _build_result(exp_config, run, wall_seconds)


def run_benchmark(config_path: str | Path, *, calibrated: bool = False) -> BenchmarkResult:
    return run_benchmark_config(parse_config(config_path), calibrated=calibrated)
