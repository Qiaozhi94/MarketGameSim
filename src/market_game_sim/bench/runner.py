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
from market_game_sim.bench.population import build_population
from market_game_sim.config.parser import ParsedConfig, parse_config
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.experiment.runner import RunResult, run_one


def build_experiment_config(parsed: ParsedConfig) -> ExperimentConfig:
    """Bridge a parsed BENCH-001-shaped config into the experiment runner's
    ``ExperimentConfig``.

    ``mult`` uses the same ``tick_size * min_quantity / cash_unit`` formula
    as ``book/simulator.py::run_simulation``'s ``config`` branch (ADR-001
    cash_unit scaling) -- both derive it from the same three
    ``MarketConfig`` fields; kept as a duplicated one-liner rather than a
    shared helper to avoid touching the already-tested simulator module.
    """
    market = parsed.market
    mult = int(market.tick_size * market.min_quantity / market.cash_unit)
    return ExperimentConfig(
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


def run_benchmark_config(parsed: ParsedConfig) -> BenchmarkResult:
    """Run an already-parsed config once and report timing/coverage.

    Timing wraps ``run_one`` only (not config parsing/population building),
    matching README §1's "归一化墙钟时间" scope -- the thing being timed is
    the kernel run, not I/O or setup.
    """
    exp_config = build_experiment_config(parsed)
    start = time.perf_counter()
    run = run_one(exp_config)
    wall_seconds = time.perf_counter() - start
    return _build_result(exp_config, run, wall_seconds)


def run_benchmark(config_path: str | Path) -> BenchmarkResult:
    return run_benchmark_config(parse_config(config_path))
