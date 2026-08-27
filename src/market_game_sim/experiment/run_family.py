"""T209: run-family configuration closed set + fail-closed allow/deny matrix.

The three run families (``SPONTANEOUS`` / ``STRESS`` / ``BENCHMARK``) and the
per-field allow/deny verdicts are frozen in ``schema/goal_contract_v2.json``
``run_family_matrix`` (whitelist policy; unlisted fields forbidden).  This
module is the **runtime** consumer of that matrix -- it loads the same JSON
(ADR-003 §3, FR-023, IR-501) and rejects any config whose fields violate the
family's allowed set.  Unknown fields fail closed (never silently ignored).

Injection fields are forbidden in ``SPONTANEOUS``: ``agent_signals``,
``extra_positions``, ``extra_events``, ``synthetic_shock_accounts``,
``outcome_conditional_orders`` (ADR-003 §3.1) -- a config carrying any of
them cannot claim the spontaneous family.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from enum import StrEnum

from market_game_sim.experiment.config import ExperimentConfig

_SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[1] / "schema" / "goal_contract_v2.json"


class RunFamilyError(ValueError):
    """Raised when a config violates its declared run family's allow/deny set."""


class RunFamily(StrEnum):
    SPONTANEOUS = "SPONTANEOUS"
    STRESS = "STRESS"
    BENCHMARK = "BENCHMARK"


@dataclass
class RunFamilyConfig:
    """The config surface the run-family matrix validates.

    Carries the 11 matrix fields (present or None).  Convert from an
    ``ExperimentConfig`` via :func:`from_experiment_config`; the default
    ``None``s mean the field is absent from the config.
    """

    run_family: str | None = None
    seed_plan: object | None = None
    goal_model_id: str | None = None
    l_level: str | None = None
    m_level: str | None = None
    stress_protocol: object | None = None
    agent_signals: object | None = None
    extra_positions: object | None = None
    extra_events: object | None = None
    synthetic_shock_accounts: object | None = None
    outcome_conditional_orders: object | None = None


def from_experiment_config(config: ExperimentConfig) -> RunFamilyConfig:
    """Map an ``ExperimentConfig`` onto the matrix surface.

    ``goal_model_id`` is the spec's goal model id if *all* belief agents
    share one (mixed / absent -> None); the five injection fields map
    directly onto the config attributes; ``seed_plan`` / ``l_level`` /
    ``m_level`` / ``stress_protocol`` / ``run_family`` are new config
    attributes (None until a later task wires them).
    """
    goal_ids = {s.goal_model_id for s in config.agent_specs if not s.is_market_maker}
    return RunFamilyConfig(
        run_family=getattr(config, "run_family", None),
        seed_plan=getattr(config, "seed_plan", None),
        goal_model_id=next(iter(goal_ids)) if len(goal_ids) == 1 else None,
        l_level=getattr(config, "l_level", None),
        m_level=getattr(config, "m_level", None),
        stress_protocol=getattr(config, "stress_protocol", None),
        agent_signals=config.agent_signals or None,
        extra_positions=config.extra_positions or None,
        extra_events=config.extra_events or None,
        synthetic_shock_accounts=getattr(config, "synthetic_shock_accounts", None),
        outcome_conditional_orders=getattr(config, "outcome_conditional_orders", None),
    )


def load_run_family_matrix() -> dict:
    """Load the frozen ``run_family_matrix`` from the contract JSON."""
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    matrix = data.get("run_family_matrix")
    if not isinstance(matrix, dict):
        raise RunFamilyError("run_family_matrix missing from goal_contract_v2.json")
    return matrix


def _verdict(matrix: dict, family: str, field: str) -> str:
    fields = matrix.get("fields", {})
    if field not in fields:
        return matrix.get("unlisted_field_verdict", "forbidden")
    return fields[field].get(family, "forbidden")


def _is_present(value: object) -> bool:
    return value is not None and (not isinstance(value, (dict, list)) or bool(value))


def validate_run_family(cfg: RunFamilyConfig, matrix: dict | None = None) -> None:
    """Fail-closed check of ``cfg`` against its declared run family.

    Rules (IR-501, fail closed):
    - the family must be one of the three frozen values;
    - every matrix field's verdict is enforced: ``forbidden`` fields must be
      absent, ``required`` fields must be present, ``optional`` fields may be
      either;
    - ``SPONTANEOUS`` additionally forbids the five injection fields
      (``spontaneous_forbidden_min_set``), asserted independently of the
      matrix so the rule survives a matrix edit.
    Errors include the field path and reason.
    """
    if matrix is None:
        matrix = load_run_family_matrix()

    family = cfg.run_family
    if family not in matrix.get("families", ()):
        raise RunFamilyError(
            f"run_family must be one of {list(matrix.get('families', []))}, got {family!r}"
        )

    # Independent min-set guard (ADR-003 §3.1): the five injection fields are
    # never allowed in SPONTANEOUS, asserted separately from the matrix rows.
    if family == RunFamily.SPONTANEOUS:
        for field in matrix.get("spontaneous_forbidden_min_set", ()):
            value = getattr(cfg, field, None)
            if _is_present(value):
                raise RunFamilyError(
                    f"SPONTANEOUS rejects injected field '{field}' (ADR-003 §3.1); "
                    "spontaneous runs must build positions endogenously"
                )

    problems: list[str] = []
    for field in matrix.get("fields", {}):
        verdict = _verdict(matrix, family, field)
        value = getattr(cfg, field, None)
        present = _is_present(value)
        if verdict == "forbidden" and present:
            problems.append(f"field '{field}' is forbidden in {family} but present in config")
        elif verdict == "required" and not present:
            problems.append(f"field '{field}' is required in {family} but absent from config")
    if problems:
        raise RunFamilyError(
            f"{family} config violates the allow/deny matrix: " + "; ".join(problems)
        )


def validate_seed_plan(plan: object) -> dict:
    """Validate a frozen seed plan structure (R018-C012: one shared validator
    for the experiment entry, the report manifest and the Schema truth).

    Closed shape: keys exactly ``{n_seeds, seeds}``, ``n_seeds`` a positive
    int (bool excluded), ``seeds`` a list of ints whose length equals
    ``n_seeds``.  Returns the validated dict (normalised).
    """
    if not isinstance(plan, dict):
        raise RunFamilyError(f"seed_plan must be an object, got {type(plan).__name__}")
    allowed = {"n_seeds", "seeds"}
    unknown = set(plan) - allowed
    if unknown:
        raise RunFamilyError(
            f"seed_plan has unknown keys {sorted(unknown)}; allowed: {sorted(allowed)}"
        )
    if "n_seeds" not in plan or type(plan["n_seeds"]) is not int or plan["n_seeds"] <= 0:
        raise RunFamilyError("seed_plan.n_seeds must be a positive integer")
    seeds = plan.get("seeds")
    if not isinstance(seeds, list) or not all(type(s) is int for s in seeds):
        raise RunFamilyError("seed_plan.seeds must be a list of integers")
    if len(seeds) != plan["n_seeds"]:
        raise RunFamilyError(f"seed_plan.seeds length {len(seeds)} != n_seeds {plan['n_seeds']}")
    return {"n_seeds": plan["n_seeds"], "seeds": list(seeds)}


__all__ = [
    "RunFamily",
    "RunFamilyConfig",
    "RunFamilyError",
    "from_experiment_config",
    "load_run_family_matrix",
    "validate_run_family",
    "validate_seed_plan",
]
