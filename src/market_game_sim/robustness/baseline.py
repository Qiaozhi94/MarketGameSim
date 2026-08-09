"""T002 (方法论 §9.4/§10.3): freeze the 0.1.2 baseline.

Captures the 0.1.2 baseline state -- git commit, experiment config hash,
protocol (three-zone), seeds, behavior mapping, KPI metric definitions and
schema version -- into a stable, immutable ``baseline_id``.

The baseline is *frozen*: ``freeze_baseline`` writes a baseline manifest file
and refuses to overwrite an existing one for the same id.  Any later 0.1.3
change to config / mapping / metrics / protocol / commit produces a different
``baseline_id`` (never reuses or overwrites the 0.1.2 result), so robustness
results can always be attributed to exactly one baseline.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
from dataclasses import asdict, dataclass
from typing import Any

from market_game_sim.experiment.config import ExperimentConfig, compute_config_hash

BASELINE_SCHEMA_VERSION = 1


class BaselineError(RuntimeError):
    """Raised when a baseline cannot be frozen or a frozen baseline is missing."""


def git_head_commit(repo_root: str | pathlib.Path) -> str:
    """Short SHA of the current git HEAD, or ``"unknown"`` if unavailable."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


@dataclass
class BaselineFrozen:
    git_commit: str
    config_hash: str
    protocol: str
    seeds: tuple[int, ...]
    behavior_mapping: str
    metric_definitions: tuple[str, ...]
    schema_version: int = BASELINE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["seeds"] = list(d["seeds"])
        d["metric_definitions"] = list(d["metric_definitions"])
        return d


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def baseline_id(baseline: BaselineFrozen) -> str:
    """Stable content hash of the frozen baseline -- any field change yields a
    different id, so 0.1.3 results never collide with or overwrite 0.1.2."""
    return hashlib.blake2b(
        _canonical(baseline.to_dict()).encode("utf-8"), digest_size=16
    ).hexdigest()


def build_baseline(
    config: ExperimentConfig,
    *,
    repo_root: str | pathlib.Path,
    protocol: str = "three-zone",
    seeds: list[int] | tuple[int, ...] = (),
    behavior_mapping: str = "linear",
    metric_definitions: list[str] | tuple[str, ...] = (
        "KPI-005",
        "KPI-006",
        "KPI-007",
        "KPI-009",
        "KPI-010",
        "KPI-011",
    ),
) -> BaselineFrozen:
    """Assemble the 0.1.2 baseline for the given config and environment."""
    return BaselineFrozen(
        git_commit=git_head_commit(repo_root),
        config_hash=compute_config_hash(config),
        protocol=protocol,
        seeds=tuple(seeds),
        behavior_mapping=behavior_mapping,
        metric_definitions=tuple(metric_definitions),
    )


def freeze_baseline(
    baseline: BaselineFrozen,
    path: str | pathlib.Path,
    *,
    force: bool = False,
) -> str:
    """Persist the baseline to a manifest file and return its id.

    Idempotent for identical content; refuses to overwrite an existing
    manifest whose id differs unless ``force=True`` (a *different* config /
    mapping / commit must never silently replace the 0.1.2 baseline).
    """
    p = pathlib.Path(path)
    bid = baseline_id(baseline)
    if p.exists() and not force:
        existing = json.loads(p.read_text(encoding="utf-8"))
        if existing.get("baseline_id") != bid:
            raise BaselineError(
                f"refusing to overwrite baseline {existing.get('baseline_id')} "
                f"with different baseline {bid} at {p}"
            )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"baseline_id": bid, **baseline.to_dict()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return bid
