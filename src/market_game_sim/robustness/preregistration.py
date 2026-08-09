"""T003 (0.1.3 §2): model-robustness preregistration.

Freezes, before any result is read, the full 0.1.3 robustness design:

- at least one alternative behavior mapping vs. the linear baseline (T102);
- at least two model families with declared difference boundaries (T006);
- three scan dimensions: leverage-cap distribution, maint_bp, MM thickness (T201);
- five-factor ablation (T301);
- common-random-path rule (T401);
- frozen holdout zone (T501);
- primary effect size, interval estimate, and failure-boundary definitions (T601/T205).

The preregistration is a pure data contract: once ``freeze`` writes the JSON,
every field is fixed and any later divergence is rejected (fail-closed), so
scanning / ablation / alternative-mapping / holdout outcomes cannot be
retrofitted into the design after they are observed.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import asdict, dataclass, field
from typing import Any

PREREG_SCHEMA_VERSION = 1


class PreregistrationError(RuntimeError):
    """Raised when a preregistration cannot be frozen or is inconsistent."""


@dataclass
class ScanAxis:
    name: str
    description: str
    type: str  # e.g. "leverage_tier_distribution", "maint_bp", "mm_thickness"
    values: list[Any] = field(default_factory=list)


@dataclass
class ModelFamily:
    family_id: str
    version: str
    description: str
    family_defining_fields: list[str] = field(default_factory=list)


@dataclass
class AblationFactor:
    name: str
    enabled_by_default: bool = True
    renormalize_rule: str = "uniform"


@dataclass
class EffectSizeSpec:
    metric_name: str = "economic_endpoint_rate"
    estimator: str = "paired_proportion_diff"
    ci_level: float = 0.95
    pairing_unit: str = "pair_id"


@dataclass
class Preregistration:
    schema_version: int = PREREG_SCHEMA_VERSION
    alternative_behavior_mappings: list[str] = field(default_factory=list)
    linear_baseline_mapping: str = "linear"
    model_families: list[ModelFamily] = field(default_factory=list)
    scan_axes: list[ScanAxis] = field(default_factory=list)
    ablation_factors: list[AblationFactor] = field(default_factory=list)
    common_random_path_rule: str = ""
    holdout_zone: str = ""
    effect_size: EffectSizeSpec = field(default_factory=EffectSizeSpec)
    failure_boundary_definition: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> list[str]:
        """Structural consistency checks; returns a list of violation strings
        (empty when valid)."""
        problems: list[str] = []
        # T003: at least one ALTERNATIVE mapping beyond the linear baseline.
        # v013: a list containing only "linear" is not a valid preregistration
        # (the old condition only fired on an EMPTY list, so "linear"-only
        # passed silently).
        alternatives = [m for m in self.alternative_behavior_mappings if m != "linear"]
        if not alternatives:
            problems.append("no alternative behavior mappings preregistered")
        if len(self.model_families) < 2:
            problems.append("fewer than two model families preregistered")
        axis_names = {a.name for a in self.scan_axes}
        if "leverage_tier_distribution" not in axis_names:
            problems.append("missing leverage_tier_distribution scan axis")
        if "maint_bp" not in axis_names:
            problems.append("missing maint_bp scan axis")
        if "mm_thickness" not in axis_names:
            problems.append("missing mm_thickness scan axis")
        if not self.common_random_path_rule:
            problems.append("common_random_path_rule not set")
        if not self.holdout_zone:
            problems.append("holdout_zone not set")
        if not self.failure_boundary_definition:
            problems.append("failure_boundary_definition not set")
        return problems


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def prereg_id(prereg: Preregistration) -> str:
    return hashlib.blake2b(_canonical(prereg.to_dict()).encode("utf-8"), digest_size=16).hexdigest()


def freeze(prereg: Preregistration, path: str | pathlib.Path, *, force: bool = False) -> str:
    """Validate + persist the preregistration; returns its id.

    ``validate`` must pass (fail-closed on incomplete preregistration), and
    the file must not already hold a different prereg id unless ``force``.
    """
    problems = prereg.validate()
    if problems:
        raise PreregistrationError("incomplete preregistration: " + "; ".join(problems))

    p = pathlib.Path(path)
    pid = prereg_id(prereg)
    if p.exists() and not force:
        existing = json.loads(p.read_text(encoding="utf-8"))
        if existing.get("prereg_id") != pid:
            raise PreregistrationError(
                f"refusing to overwrite prereg {existing.get('prereg_id')} with {pid}"
            )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"prereg_id": pid, **prereg.to_dict()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return pid
