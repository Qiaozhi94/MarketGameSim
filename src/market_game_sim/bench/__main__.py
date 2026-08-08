"""CLI entry point (benchmarks/README.md §5):

    python -m market_game_sim.bench --config benchmarks/BENCH-001.yaml
    python -m market_game_sim.bench --calibrate

Prints a JSON report to stdout; does not write back into BENCH-001.yaml or
reference-machine.md -- freezing ``book_operations_golden`` / the reference
CALIB-001 timing is a separate, deliberate action requiring the
hardware-locking protocol in reference-machine.md §2 (not something this
CLI should do unattended on every run).
"""

from __future__ import annotations

import argparse
import json
import sys
from statistics import median

from market_game_sim.bench.calib import run_calib_001
from market_game_sim.bench.runner import run_benchmark


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m market_game_sim.bench")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config", help="path to a BENCH-001-shaped YAML config")
    group.add_argument("--calibrate", action="store_true", help="run CALIB-001 (5x, report median)")
    args = parser.parse_args(argv)

    if args.calibrate:
        samples = [run_calib_001() for _ in range(5)]
        report = {
            "benchmark_id": "CALIB-001",
            "samples_seconds": samples,
            "median_seconds": median(samples),
            "min_seconds": min(samples),
        }
        print(json.dumps(report, indent=2))
        return 0

    result = run_benchmark(args.config)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.coverage_valid else 1


if __name__ == "__main__":
    sys.exit(main())
