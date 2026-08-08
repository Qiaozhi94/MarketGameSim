"""T704 (0.1.2 附加门槛): cross-process determinism.

Verified this had zero test coverage: no existing test re-runs the same
config/seed and compares outputs, and CI's own comment
(.github/workflows/ci.yml) explicitly says the real cross-process,
different-PYTHONHASHSEED check "由 0.1.1 T602 / 退出条件 E4 负责" without
ever pointing at an implementation -- ``PYTHONHASHSEED=0`` in CI only makes
an existing ``hash()`` misuse reproducible within one run, it proves
nothing about cross-process reproducibility on its own (reference-machine.md
§3).

This spawns ``tools/determinism_probe.py`` as two real subprocesses with
different ``PYTHONHASHSEED`` values and asserts their JSON output (event
digest via hashlib/blake2b, classification, liquidation metrics, and the
full study report) is byte-identical -- the only way to actually catch an
accidental dependency on Python's per-process hash randomization.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROBE = Path(__file__).resolve().parents[2] / "tools" / "determinism_probe.py"


def _run_probe(hashseed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": hashseed}
    result = subprocess.run(
        [sys.executable, str(PROBE)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"probe failed (PYTHONHASHSEED={hashseed}): {result.stderr}"
    return result.stdout


def test_output_is_byte_identical_across_different_hashseeds():
    out_a = _run_probe("0")
    out_b = _run_probe("1")
    assert out_a == out_b


def test_output_is_not_trivially_empty():
    """Negative guard against a vacuously-true comparison (e.g. the probe
    crashing silently or printing nothing on both sides)."""
    out = _run_probe("0")
    payload = json.loads(out)
    assert len(payload["event_digests"]) == 2
    assert all(len(d) == 64 for d in payload["event_digests"])  # blake2b hex, not empty/None
    assert payload["report"]["n_runs"] == 2


def test_event_digests_differ_between_the_two_seeds_in_the_run():
    """A different sanity check in the opposite direction: seed=1 and
    seed=2 within the SAME probe invocation must not collide (would
    indicate the digest ignores the seed entirely, e.g. hashing an
    always-empty projection)."""
    payload = json.loads(_run_probe("0"))
    d1, d2 = payload["event_digests"]
    assert d1 != d2
