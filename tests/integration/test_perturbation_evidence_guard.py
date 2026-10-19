"""0.4.2 T1131（NFR-602 / AC-607）：人类扰动产物进不了任何 evidence index。

既有拦截点（design §4）：``showcase/evidence_index.py`` 的构建入口只接受
``run_family = SPONTANEOUS`` 且 ``evidence_class = formal-research``；
``evidence/evidence_guard.py`` 在读取任何事件体之前拒绝 ``run_mode: interactive``。
本里程碑的会话 artifact 与效应量报告显式携带 ``experiment-preview`` 与 ``interactive``。
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.evidence.evidence_guard import (
    EvidenceBundleCandidate,
    EvidenceClassError,
    EvidenceRunModeError,
    guard_evidence_bundle,
    guard_evidence_class,
)
from market_game_sim.experiment.perturbation import session
from market_game_sim.metrics import stability_effect as se
from market_game_sim.showcase import evidence_index

S = 1_000_000_000


def _session(path):
    writer = session.SessionWriter.create(
        path,
        {
            "format_version": 1,
            "session_id": "s-guard",
            "arm": "human",
            "replay_mode": "original",
            "roster_id": "roster-" + "e" * 32,
            "seed": 7,
            "engine_config_digest": "a" * 32,
            "evidence_class": "experiment-preview",
            "run_mode": "interactive",
        },
    )
    writer.close()
    return path


def _report():
    m = se.ArmMeasurement(0, 600 * S, dict.fromkeys(se.METRIC_IDS, 0.1), (), 0, 10)
    arm = {
        "run_digest": "d",
        "aborted": None,
        "logical_ns": 600 * S,
        "measurement": m,
        "sc501_failed": [],
        "out_of_window_actions": 0,
        "cancel_outcomes": [],
    }
    return se.build_effect_report(
        pairs=[{"seed": 2001, "replay_mode": "open_loop_replay", "baseline": arm, "human": arm}],
        original_cases=[],
        preregistration={
            "min_valid_pairs": 2,
            "sigma_b": dict.fromkeys(se.METRIC_IDS, 0.1),
            "statistics": {"ci_level": 0.9, "n_resamples": 100, "bootstrap_seed": 0},
        },
        preregistration_sha256="p" * 64,
        treatment={"content_hash": "c" * 64, "session_id": "s-guard"},
        label="固定订单流扰动",
        carrier_disclaimer="只作载体",
    )


def test_perturbation_products_rejected_by_evidence_index(tmp_path):
    """AC-607：
    带 experiment-preview 与 run_mode interactive 的 artifact/报告交给 evidence index 构建入口被拒；
    合规 SPONTANEOUS + formal-research 输入不受影响
    """
    report = _report()
    header = json.loads(_session(tmp_path / "s.jsonl").read_text().splitlines()[0])
    for product in (report, header):
        assert product["evidence_class"] == "experiment-preview"
        assert product["run_mode"] == "interactive"

    # 1. 证据索引构建入口：把报告/会话头当作 T215 的三份输入交进去，第一道范围检查即拒。
    t215 = tmp_path / "T215"
    t215.mkdir()
    for name, payload in (
        ("progress.json", report),
        ("analysis.json", report),
        ("run-manifest.json", header),
    ):
        (t215 / name).write_text(json.dumps(payload, ensure_ascii=False))
    with pytest.raises(evidence_index.EvidenceIndexError, match="run_family"):
        evidence_index.build_evidence_index(t215)
    for product in (report, header):
        with pytest.raises(evidence_index.EvidenceIndexError):
            evidence_index._validate_common_scope({**product, "run_family": "SPONTANEOUS"}, "x")

    # 2. 证据包守卫：interactive 在读取任何事件体之前就被拒。
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(report, ensure_ascii=False))
    candidate = EvidenceBundleCandidate(manifest_path=manifest, event_log_path=tmp_path / "s.jsonl")
    with pytest.raises(EvidenceRunModeError, match="interactive"):
        guard_evidence_bundle(candidate)

    # 3. 证据类别：BENCHMARK 族不接受 experiment-preview 作为证据。
    with pytest.raises(EvidenceClassError):
        guard_evidence_class("BENCHMARK", report["evidence_class"])

    # 正向：合规的 SPONTANEOUS + formal-research 输入通过同一道范围检查。
    evidence_index._validate_common_scope(
        {"run_family": "SPONTANEOUS", "evidence_class": "formal-research"}, "ok"
    )
    assert guard_evidence_class("SPONTANEOUS", "formal-research").value == "formal-research"
