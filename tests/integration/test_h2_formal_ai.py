"""T917：AI 轨正式采样驱动。

核心不变量：顺序由冻结分配表拥有（本模块只消费）、准入在落盘之前（拒绝路径
零产物）、断点续跑不重打、配对合同字段进工件（重放可比对）。
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.experiment.h2 import evidence_guard, formal_ai


@pytest.fixture(autouse=True)
def _clean_guard_ledger():
    evidence_guard.reset()
    yield
    evidence_guard.reset()


@pytest.fixture(scope="module")
def assignments():
    from market_game_sim.experiment.h2 import artifacts

    return artifacts.load_assignments()


def test_sample_runs_frozen_order_and_admits(tmp_path, assignments):
    written = formal_ai.sample_ai_blocks(count=3, out_dir=tmp_path, assignments=assignments)
    assert [item["order_index"] for item in written] == [0, 1, 2]
    assert [item["seed"] for item in written] == [50_000, 50_001, 50_002]
    assert evidence_guard.admitted_count() == 3
    for item in written:
        assert item["run_mode"] == "ai-mechanism-experiment"
        assert item["evidence_class"] == "formal-research"
        path = formal_ai.block_artifact_path(tmp_path, item["order_index"], item["seed"])
        assert path.exists()


def test_resume_skips_completed_blocks(tmp_path, assignments):
    formal_ai.sample_ai_blocks(count=2, out_dir=tmp_path, assignments=assignments)
    second = formal_ai.sample_ai_blocks(count=5, out_dir=tmp_path, assignments=assignments)
    assert [item["order_index"] for item in second] == [2, 3, 4, 5, 6]
    assert formal_ai.completed_block_count(tmp_path) == 7


def test_pair_contract_recorded_in_artifact(tmp_path, assignments):
    written = formal_ai.sample_ai_blocks(count=1, out_dir=tmp_path, assignments=assignments)
    pair = written[0]["pair"]
    assert "window_schedule" in pair["identical_fields"]
    assert "accounts" in pair["identical_fields"]
    assert pair["disclosed_differences"]["policy_id"] == [
        "risk_budget_linear_v1",
        "risk_budget_threshold_v1",
    ]
    runs = written[0]["runs"]
    assert {run["arm"] for run in runs} == {"linear", "threshold"}
    assert all(run["terminated"] == "COMPLETED" for run in runs)
    assert len({run["events_sha256"] for run in runs}) == 2


def test_artifact_is_blind_to_analysis(tmp_path, assignments):
    """采样工件只锁定运行事实，不预支任何分析结论（分析是 T919 的事）。"""
    written = formal_ai.sample_ai_blocks(count=1, out_dir=tmp_path, assignments=assignments)
    blob = json.dumps(written[0], ensure_ascii=False)
    for field in ("severity", "effect", "p_value", "ci_low", "holm"):
        assert field not in blob


def test_protocol_hash_drift_is_fail_closed(tmp_path, assignments):
    drifted = dict(assignments)
    drifted["protocol_hash"] = "0" * 64
    with pytest.raises(ValueError, match="分配表协议哈希与冻结归档不一致"):
        formal_ai.sample_ai_blocks(count=2, out_dir=tmp_path, assignments=drifted)
    assert evidence_guard.partial_writes() == []
    assert formal_ai.completed_block_count(tmp_path) == 0
