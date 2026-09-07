"""AC-301/AC-303/AC-304（H2-A 成果门，T909）+ AC-307（完整交付，T920/T921）。

T909 部分已实现：单命令 `python -m market_game_sim.experiment protocol preview`
生成可打开的冻结协议、配对 manifest diff 与 guard 矩阵，标记 `experiment-preview`。
AC-307 部分仍是 strict-xfail 骨架，等 T920/T921 的完整交付入口。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from market_game_sim.experiment.h2 import outcomes, preview, preview_b, session

# --------------------------------------------------------------------------- #
# T909 `[成果门:H2-A]`：单命令生成可打开的 preview 包
# --------------------------------------------------------------------------- #


def test_h2a_cli_generates_the_complete_preview_bundle(tmp_path):
    """真正跑 `python -m market_game_sim.experiment protocol preview`，不是内部函数捷径。"""
    out = tmp_path / "H2-A"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "market_game_sim.experiment",
            "protocol",
            "preview",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert {path.name for path in out.iterdir()} == set(preview.BUNDLE_FILES)

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["evidence_class"] == "experiment-preview"
    assert len(manifest["protocol_hash"]) == 64


def test_h2a_default_output_directory_generates_without_out_flag(tmp_path, monkeypatch):
    """反面：不传 --out 也必须能跑，默认目录来自 preview.DEFAULT_OUT。"""
    monkeypatch.chdir(tmp_path)
    completed = subprocess.run(
        [sys.executable, "-m", "market_game_sim.experiment", "protocol", "preview"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (tmp_path / preview.DEFAULT_OUT / "manifest.json").is_file()


def test_h2a_protocol_json_is_openable_and_content_addressed(tmp_path):
    target = preview.generate(tmp_path / "bundle")
    payload = json.loads((target / "protocol.json").read_text(encoding="utf-8"))
    assert payload["evidence_class"] == "experiment-preview"
    assert payload["payload"]["minimum_blocks"] == 168
    assert payload["protocol_hash"]


def test_h2a_pair_manifest_diff_shows_matrix_same_and_different_fields(tmp_path):
    target = preview.generate(tmp_path / "bundle")
    diff = json.loads((target / "pair-manifest-diff.json").read_text(encoding="utf-8"))
    assert set(diff["policies"]) == {"risk_budget_linear_v1", "risk_budget_threshold_v1"}
    assert set(diff["identical_fields"]) == {
        "accounts",
        "action_space",
        "information_set",
        "initial_price_ticks",
        "window_schedule",
    }
    assert set(diff["disclosed_differences"]["policy_id"]) == set(diff["policies"])
    assert len(set(diff["disclosed_differences"]["policy_id"])) == 2


def test_h2a_guard_matrix_rejects_h1_interactive_and_protocol_drift(tmp_path):
    """验收明文要求的两条：H1 交互数据被拒绝、协议漂移被拒绝，必须都能在产物里看到。"""
    target = preview.generate(tmp_path / "bundle")
    matrix = json.loads((target / "guard-matrix.json").read_text(encoding="utf-8"))["scenarios"]
    by_label = {row["label"]: row for row in matrix}

    assert by_label["h1_interactive_data_rejected"]["admitted"] is False
    assert by_label["protocol_drift_rejected"]["admitted"] is False
    # 正例同样必须出现，否则"全部拒绝"也能通过上面两条断言。
    assert by_label["ai_track_formal_frozen_protocol"]["admitted"] is True
    assert by_label["owner_track_formal_frozen_protocol"]["admitted"] is True


def test_h2a_guard_matrix_leaves_no_residue_in_the_shared_ledger(tmp_path):
    """preview 生成过程会调用 evidence_guard.admit 多次；这些探测不得污染共享账本。"""
    from market_game_sim.experiment.h2 import evidence_guard

    evidence_guard.reset()
    preview.generate(tmp_path / "bundle")
    assert evidence_guard.partial_writes() == []
    assert evidence_guard.admitted_count() == 0


# --------------------------------------------------------------------------- #
# T915 `[成果门:H2-B]`：锁定客户端、结果与机制的单命令 preview 包
# --------------------------------------------------------------------------- #


def test_h2b_cli_generates_the_complete_preview_bundle(tmp_path):
    """真正跑验收入口，并检查默认路径和全部可打开产物。"""
    completed = subprocess.run(
        [sys.executable, "-m", "market_game_sim.experiment", "preview"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    target = tmp_path / preview_b.DEFAULT_OUT
    assert {path.name for path in target.iterdir()} == set(preview_b.BUNDLE_FILES)
    payloads = {
        name: json.loads((target / name).read_text(encoding="utf-8"))
        for name in preview_b.BUNDLE_FILES
    }
    assert all(payload["evidence_class"] == "experiment-preview" for payload in payloads.values())


def test_h2b_preview_exposes_window_stage_replay_outcome_and_mechanism_evidence(tmp_path):
    """成果包本身必须足以验收 T915，不能只靠生成过程未报错。"""
    target = preview_b.generate(tmp_path / "H2-B")
    training = json.loads((target / "training-session.json").read_text(encoding="utf-8"))
    formal = json.loads((target / "formal-session.json").read_text(encoding="utf-8"))
    replay = json.loads((target / "replay-verification.json").read_text(encoding="utf-8"))
    outcome_report = json.loads((target / "outcomes-preview.json").read_text(encoding="utf-8"))
    mechanism_report = json.loads((target / "mechanisms-preview.json").read_text(encoding="utf-8"))

    assert training["stage"] == "training"
    assert formal["stage"] == "formal"
    assert training["completed_windows"] == training["total_windows"]
    assert formal["completed_windows"] == formal["total_windows"]
    assert session.NO_ACTION in {item["decision"] for item in formal["decisions"]}
    assert {item["intent_id"] for item in training["recorded_decisions"]}.isdisjoint(
        {item["intent_id"] for item in formal["recorded_decisions"]}
    )
    for forbidden in ("pause", "step", "set_param", "reveal_future"):
        assert forbidden not in formal["formal_client_controls"]

    assert replay["states_match"] is True
    assert replay["recorded_decisions_match"] is True

    assert set(outcome_report["families"]) == set(outcomes.FAMILIES)
    assert "composite_score" not in outcome_report
    for family in outcome_report["families"].values():
        assert family["primary_metric"] == "severity"
        assert family["occurrence_role"] == "descriptive"
        assert family["ci_low"] <= family["effect"] <= family["ci_high"]
        assert "occurrence_rate_diff" in family

    assert mechanism_report["row_count"] == len(mechanism_report["rows"])
    mechanism_names = {"aggressive_orders", "liquidity_withdrawal", "risk_reduction"}
    assert all(set(row["values"]) == mechanism_names for row in mechanism_report["rows"])
    for name in mechanism_names:
        assert any(row["values"][name]["evidence_event_ids"] for row in mechanism_report["rows"])


@pytest.mark.xfail(strict=True, reason="T920/T921 未实现：H2 交付入口尚不存在")
def test_ac307_bundle_rebuilds_from_the_index_only():
    """新进程只读 evidence index 即可重建，机器结果内容哈希一致。"""
    from market_game_sim.experiment.h2 import delivery

    first = delivery.build_from_index(delivery.frozen_index_path())
    second = delivery.build_from_index(delivery.frozen_index_path())
    assert first.machine_results_sha256 == second.machine_results_sha256


@pytest.mark.xfail(strict=True, reason="T921 未实现：结论语法检查尚不存在")
def test_ac307_conclusion_syntax_forbids_the_human_effect_shorthand():
    """结论必须带三限定词，且禁用人类效应这一简称。"""
    from market_game_sim.experiment.h2 import delivery

    report = delivery.build_from_index(delivery.frozen_index_path()).report_text
    assert "人类效应" not in report
    for qualifier in ("模型族", "参数范围", "seed 分布"):
        assert qualifier in report


def test_ac307_owner_track_results_are_marked_descriptive():
    """所有者轨交付包是 experiment-preview 且标注描述性。

    信封与证据级别标注已由 T905 落地，故摘除 xfail；完整交付流水线仍属 T920/T921。
    """
    from market_game_sim.experiment.h2 import delivery

    bundle = delivery.build_owner_bundle()
    assert bundle.evidence_class == "experiment-preview"
    assert bundle.marked_descriptive is True
