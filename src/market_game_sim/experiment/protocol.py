"""T603 (方法论 §9.3/§10.1/§10.3): three-zone experiment protocol enforcement.

校准区 -> 冻结验证区 -> 信念实验区，顺序固定、不可跳过或回退（§10.1"验证顺序
不可颠倒"）。进入冻结验证区后，除预注册的单一处理维度（``treatment_field``，
默认 ``leverage_tier``）外，全部配置字段被冻结为快照；后续任何一次调用如果
配置字段偏离快照，判定为协议违规：``raise ProtocolViolation`` 并向审计日志
追加一条记录（fail-stop，不静默继续，呼应内核自身对因果链/schema 违规的处理
哲学，见 kernel/scheduling.py）。

信念实验区声明的处理维度取值集合，必须与校准区实际试过的取值集合不相交
（§10.3"信念实验区预注册，与校准区不重叠"）——防止"校准时刚好看到某个杠杆
倍数表现不错，就拿它当信念实验的处理值"这种数据窥探（data snooping）。
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig


class ProtocolStage(Enum):
    CALIBRATION = "CALIBRATION"
    FROZEN_VALIDATION = "FROZEN_VALIDATION"
    BELIEF_EXPERIMENT = "BELIEF_EXPERIMENT"


class ProtocolViolation(Exception):
    """Raised on any T603 protocol violation.  Fail-stop: callers must not
    catch this and continue silently -- it means the run is not a valid
    single-dimension, non-data-snooped contrast and must not feed into
    conclusions (方法论 §10.3/§10.5)."""


def _frozen_snapshot(config: ExperimentConfig, treatment_field: str) -> dict[str, Any]:
    """Every ExperimentConfig field (except seed/group_label/agent_specs,
    which legitimately vary run-to-run or are handled separately) plus
    every AgentSpec field except treatment_field, keyed by agent_id."""
    snapshot: dict[str, Any] = {}
    for f in dataclasses.fields(ExperimentConfig):
        if f.name in ("seed", "group_label", "agent_specs"):
            continue
        snapshot[f.name] = getattr(config, f.name)
    agent_snapshot: dict[str, dict[str, Any]] = {}
    for spec in config.agent_specs:
        spec_snapshot = {}
        for f in dataclasses.fields(AgentSpec):
            if f.name == treatment_field:
                continue
            spec_snapshot[f.name] = getattr(spec, f.name)
        agent_snapshot[spec.agent_id] = spec_snapshot
    snapshot["agent_specs"] = agent_snapshot
    return snapshot


def _treatment_values(config: ExperimentConfig, treatment_field: str) -> set[Any]:
    return {
        getattr(spec, treatment_field)
        for spec in config.agent_specs
        if hasattr(spec, treatment_field)
    }


def _first_diff(frozen: dict[str, Any], current: dict[str, Any]) -> tuple[str, Any, Any]:
    """Locate the first field where ``current`` deviates from ``frozen``,
    descending into the nested ``agent_specs`` dict when needed."""
    for k, frozen_v in frozen.items():
        if k == "agent_specs":
            if set(frozen_v) != set(current.get(k, {})):
                return "agent_specs.agent_ids", sorted(frozen_v), sorted(current.get(k, {}))
            for aid, spec_snap in frozen_v.items():
                cur_spec = current[k][aid]
                if cur_spec != spec_snap:
                    for sk, sv in spec_snap.items():
                        if cur_spec.get(sk) != sv:
                            return f"agent_specs[{aid}].{sk}", sv, cur_spec.get(sk)
            continue
        if frozen_v != current.get(k):
            return k, frozen_v, current.get(k)
    return "unknown", None, None


class ExperimentProtocol:
    """Stateful three-zone protocol guard for one pre-registered study.

    Usage::

        protocol = ExperimentProtocol(treatment_field="leverage_tier")
        # calibration: try whatever, results don't feed conclusions
        for cfg in calibration_configs:
            protocol.record_calibration_trial(cfg)
            run_one(cfg, protocol=protocol)
        # freeze on the chosen calibration config
        protocol.freeze_calibration(chosen_config)
        # frozen-validation: only the frozen config (any treatment_field
        # value) may run
        run_one(validation_config, protocol=protocol)
        # pre-register the belief-experiment treatment range, non-
        # overlapping with what calibration tried
        protocol.enter_belief_experiment(belief_treatment_values=[1, 10, 50])
        run_one(belief_config, protocol=protocol)
    """

    def __init__(
        self,
        treatment_field: str = "leverage_tier",
        audit_log_path: str | Path = "docs/experiments/protocol-audit.jsonl",
    ) -> None:
        self.treatment_field = treatment_field
        self.audit_log_path = Path(audit_log_path)
        self.stage = ProtocolStage.CALIBRATION
        self._calibration_trial_values: set[Any] = set()
        self._frozen: dict[str, Any] | None = None
        self._belief_values: set[Any] | None = None

    def record_calibration_trial(self, config: ExperimentConfig) -> None:
        """Log a config tried during calibration -- only valid while still
        in the CALIBRATION stage.  Feeds enter_belief_experiment's
        non-overlap check."""
        if self.stage != ProtocolStage.CALIBRATION:
            raise ProtocolViolation(
                f"record_calibration_trial called in stage {self.stage.value}, "
                "only valid during CALIBRATION"
            )
        self._calibration_trial_values |= _treatment_values(config, self.treatment_field)

    def freeze_calibration(self, config: ExperimentConfig) -> None:
        """CALIBRATION -> FROZEN_VALIDATION: snapshot every field except
        treatment_field as the frozen baseline (方法论 §10.3 "划定后不得
        再调参数")."""
        if self.stage != ProtocolStage.CALIBRATION:
            raise ProtocolViolation(
                f"freeze_calibration called in stage {self.stage.value}, expected CALIBRATION"
            )
        self._frozen = _frozen_snapshot(config, self.treatment_field)
        self.stage = ProtocolStage.FROZEN_VALIDATION

    def enter_belief_experiment(self, belief_treatment_values: Iterable[Any]) -> None:
        """FROZEN_VALIDATION -> BELIEF_EXPERIMENT: pre-register the
        treatment-dimension value set for the belief-experiment zone; must
        not intersect values already tried during calibration."""
        if self.stage != ProtocolStage.FROZEN_VALIDATION:
            raise ProtocolViolation(
                f"enter_belief_experiment called in stage {self.stage.value}, "
                "expected FROZEN_VALIDATION"
            )
        values = set(belief_treatment_values)
        overlap = values & self._calibration_trial_values
        if overlap:
            overlap_sorted = sorted(overlap, key=repr)
            self._audit(
                "belief-experiment treatment values overlap calibration-explored values",
                field_name=self.treatment_field,
                detail={"overlap": overlap_sorted},
            )
            raise ProtocolViolation(
                f"belief-experiment {self.treatment_field} values {overlap_sorted} were "
                "already explored during calibration (方法论 §10.3 单调参数空间三区分离)"
            )
        self._belief_values = values
        self.stage = ProtocolStage.BELIEF_EXPERIMENT

    def check_config(self, config: ExperimentConfig) -> None:
        """Verify ``config`` respects the current stage's lock, before
        actually running it.  No-op during CALIBRATION."""
        if self.stage == ProtocolStage.CALIBRATION:
            return
        assert self._frozen is not None  # always set once out of CALIBRATION
        current = _frozen_snapshot(config, self.treatment_field)
        if current != self._frozen:
            field_name, frozen_val, got_val = _first_diff(self._frozen, current)
            self._audit(
                f"calibration-frozen field {field_name} modified after freeze",
                field_name=field_name,
                detail={"frozen_value": frozen_val, "attempted_value": got_val},
            )
            raise ProtocolViolation(
                f"calibration-frozen field {field_name!r} was modified after freeze "
                f"(frozen={frozen_val!r}, attempted={got_val!r}) -- 方法论 §10.3 冻结验证区/"
                "信念实验区不得再调校准参数"
            )
        if self.stage == ProtocolStage.BELIEF_EXPERIMENT:
            assert self._belief_values is not None
            used = _treatment_values(config, self.treatment_field)
            not_registered = used - self._belief_values
            if not_registered:
                not_registered_sorted = sorted(not_registered, key=repr)
                self._audit(
                    "treatment value used outside pre-registered belief-experiment range",
                    field_name=self.treatment_field,
                    detail={
                        "used": not_registered_sorted,
                        "registered": sorted(self._belief_values, key=repr),
                    },
                )
                raise ProtocolViolation(
                    f"{self.treatment_field} value(s) {not_registered_sorted} not in "
                    f"pre-registered belief-experiment range "
                    f"{sorted(self._belief_values, key=repr)}"
                )

    def _audit(self, violation: str, field_name: str, detail: dict[str, Any]) -> None:
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "stage": self.stage.value,
            "violation": violation,
            "field": field_name,
            **detail,
        }
        with self.audit_log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
