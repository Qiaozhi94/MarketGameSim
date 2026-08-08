"""T702: CALIB-001 calibration microbenchmark (benchmarks/README.md §2 第一层).

Exercises the kernel's two real bottlenecks -- the event-queue heap and the
book's price-level dict index -- so the machine-speed ratio it produces is
representative of the actual workload, unlike a generic CPU benchmark
(README.md explicitly warns against floating-point-matrix-style benchmarks
here, since the domain kernel does almost no float arithmetic).

Formal calibration (recording a reference-machine timing into
benchmarks/reference-machine.md) requires the hardware-locking protocol in
that file (CPU affinity to a P-core, high-performance power plan, 5-run
median) -- this module only provides the deterministic workload + a local
timing helper; it does not attempt to lock affinity itself.
"""

from __future__ import annotations

import heapq
import time
from dataclasses import dataclass

CALIB_001_OPS = 200_000


def run_calib_001(n: int = CALIB_001_OPS) -> float:
    """Push/pop ``n`` items through a heap and do ``n`` dict lookups.
    Returns elapsed wall-clock seconds for this single run (not a median --
    callers wanting the reference-machine.md protocol's 5-run median should
    call this repeatedly and take ``statistics.median``)."""
    start = time.perf_counter()
    heap: list[tuple[int, int]] = []
    index: dict[int, int] = {}
    for i in range(n):
        heapq.heappush(heap, (i % 997, i))
        index[i % 5_000] = i
    while heap:
        key, value = heapq.heappop(heap)
        _ = index.get(key, 0)
        _ = value
    return time.perf_counter() - start


@dataclass
class CalibrationRatio:
    reference_seconds: float
    local_seconds: float

    @property
    def speed_ratio(self) -> float:
        """``reference / local``: > 1 means this machine is faster than the
        reference machine (README.md §2 第一层公式)."""
        if self.local_seconds <= 0:
            raise ValueError("local_seconds must be > 0")
        return self.reference_seconds / self.local_seconds

    def normalize(self, measured_seconds: float) -> float:
        """Fold a locally-measured wall-clock time back into the
        reference-machine's timing frame."""
        return measured_seconds * self.speed_ratio
