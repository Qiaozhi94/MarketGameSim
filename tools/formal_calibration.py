"""benchmarks/reference-machine.md §2 formal calibration runner.

Locks THIS process's CPU affinity to the reference machine's P-cores
before running anything (via ``SetProcessAffinityMask``, Windows-only) --
locking from inside the process itself avoids the race condition of trying
to set affinity on an already-launched external process. Runs CALIB-001
and the calibrated BENCH-001 benchmark 5x each and reports median/min per
reference-machine.md §2 ("计时结果取5次运行的中位数，并同时报告最小值与
四分位距。单次运行结果不作为判定依据").

Usage::

    python tools/formal_calibration.py --p-core-mask 0xFFF

``--p-core-mask`` is a bitmask over Windows logical processor indices (bit i
set = logical processor i included). For 6 physical P-cores with
hyperthreading occupying logical processors 0-11, that is ``0xFFF``
(bits 0-11).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from market_game_sim.bench.calib import run_calib_001  # noqa: E402
from market_game_sim.bench.runner import run_benchmark  # noqa: E402


def set_self_affinity(mask: int) -> None:
    """Locks this process to the given logical-processor bitmask.

    ``ctypes.windll.kernel32`` without explicit ``argtypes``/``restype``
    silently mis-marshals the pointer-sized HANDLE/SIZE_T arguments on
    64-bit Windows and the call fails (returns 0) without raising -- must
    declare the signatures explicitly.
    """
    if sys.platform != "win32":
        raise RuntimeError("formal_calibration.py only implements affinity locking on Windows")
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
    kernel32.SetProcessAffinityMask.restype = wintypes.BOOL

    handle = kernel32.GetCurrentProcess()
    ok = kernel32.SetProcessAffinityMask(handle, ctypes.c_size_t(mask))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())


def _stats(samples: list[float]) -> dict:
    sorted_samples = sorted(samples)
    n = len(sorted_samples)
    q1 = sorted_samples[n // 4]
    q3 = sorted_samples[(3 * n) // 4]
    return {
        "samples_seconds": samples,
        "median_seconds": statistics.median(samples),
        "min_seconds": min(samples),
        "iqr_seconds": q3 - q1,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--p-core-mask",
        type=lambda s: int(s, 0),
        required=True,
        help="hex or decimal bitmask over logical processor indices, e.g. 0xFFF",
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent.parent / "benchmarks" / "BENCH-001.yaml"),
    )
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()

    set_self_affinity(args.p_core_mask)

    calib_samples = [run_calib_001() for _ in range(args.runs)]

    bench_wall_samples = []
    bench_op_counts = set()
    last_result = None
    for _ in range(args.runs):
        result = run_benchmark(args.config, calibrated=True)
        bench_wall_samples.append(result.wall_seconds)
        bench_op_counts.add(result.book_operation_count)
        last_result = result

    report = {
        "affinity_mask": hex(args.p_core_mask),
        "calib_001": _stats(calib_samples),
        "bench_001_calibrated": {
            **_stats(bench_wall_samples),
            "book_operation_count_values": sorted(bench_op_counts),
            "book_operation_count_deterministic": len(bench_op_counts) == 1,
            "coverage_valid": last_result.coverage_valid if last_result else None,
            "coverage_failures": last_result.coverage_failures if last_result else None,
        },
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
