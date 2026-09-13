"""AC-305：三个结果家族的分别估计与多重性。

T912 已实现，xfail 骨架相应摘除。分两层测试：``analyse_families()`` 是纯函数，用合成
观察值覆盖统计正确性与缺失处理（快、确定性、能构造退化输入）；``analyse_ai_track()``
用一批真实配对 block 冒烟测试端到端管线（慢一些，但验证的是真实数据不是编造的）。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.experiment.h2 import outcomes

FAMILIES = outcomes.FAMILIES


def _observation(seed, control, treatment, *, control_occ=0.0, treatment_occ=0.0):
    return outcomes.BlockObservation(
        seed=seed,
        control_severity=control,
        treatment_severity=treatment,
        control_occurrence=control_occ,
        treatment_occurrence=treatment_occ,
    )


def _uniform_observations(n: int, *, control: float, treatment: float) -> dict:
    """构造一批三家族都相同配对差的合成观察值，便于精确断言 effect/CI。"""
    return {
        family: [_observation(seed, control, treatment) for seed in range(n)] for family in FAMILIES
    }


# --------------------------------------------------------------------------- #
# 纯函数核心：合成数据
# --------------------------------------------------------------------------- #


def test_ac305_primary_estimand_is_severity_and_occurrence_is_descriptive():
    report = outcomes.analyse_families(_uniform_observations(20, control=1.0, treatment=2.0))
    for family in FAMILIES:
        assert report[family].primary_metric == "severity"
        assert report[family].occurrence_role == "descriptive"


def test_ac305_holm_applies_to_the_three_severity_tests_only():
    report = outcomes.analyse_families(_uniform_observations(20, control=1.0, treatment=2.0))
    assert sorted(report.holm_corrected_tests) == sorted(f"{f}.severity" for f in FAMILIES)


def test_ac305_no_composite_crash_score_is_produced():
    report = outcomes.analyse_families(_uniform_observations(20, control=1.0, treatment=2.0))
    assert not any("composite" in key for key in report)


def test_report_is_read_only_and_cannot_be_injected_with_a_new_key():
    """OutcomeReport 是 Mapping，不是 dict——外部不能塞一个"综合分数"进去。"""
    report = outcomes.analyse_families(_uniform_observations(20, control=1.0, treatment=2.0))
    with pytest.raises(TypeError):
        report["composite_crash_score"] = None  # type: ignore[index]


def test_uniformly_positive_paired_diff_gives_a_confidence_interval_excluding_zero():
    """反面对照：全体配对差都是同符号，效应量与 CI 必须清晰偏离 0，不能被平均成噪声。"""
    report = outcomes.analyse_families(_uniform_observations(30, control=1.0, treatment=3.0))
    for family in FAMILIES:
        result = report[family]
        assert result.effect == pytest.approx(2.0)
        assert result.ci_low > 0.0
        assert result.holm_significant is True


def test_symmetric_paired_diff_around_zero_is_not_significant():
    """反面：配对差在 0 两侧对称分布时，不应被判定为显著——这是上一条的对照组。"""
    n = 40
    observations = {
        family: [
            _observation(seed, control=0.0, treatment=(1.0 if seed % 2 == 0 else -1.0))
            for seed in range(n)
        ]
        for family in FAMILIES
    }
    report = outcomes.analyse_families(observations)
    for family in FAMILIES:
        result = report[family]
        assert result.ci_low < 0.0 < result.ci_high
        assert result.holm_significant is False


# --------------------------------------------------------------------------- #
# 缺失处理（批量场景：多条记录同时缺失）
# --------------------------------------------------------------------------- #


def test_missing_pairs_are_excluded_by_complete_case_and_counted():
    """批量场景：同一家族里多条记录同时缺失，必须全部被排除且计数准确，不是索引错位。"""
    complete = [_observation(seed, 1.0, 2.0) for seed in range(10)]
    missing = [
        outcomes.BlockObservation(seed=100 + i, control_severity=None, treatment_severity=1.0)
        for i in range(4)
    ]
    observations = {family: complete + missing for family in FAMILIES}
    report = outcomes.analyse_families(observations)
    for family in FAMILIES:
        result = report[family]
        assert result.n_blocks == 10
        assert result.n_missing == 4
        assert result.effect == pytest.approx(1.0)


def test_missing_data_never_gets_imputed_into_the_effect():
    """反面：即使缺失值的"如果不缺失"看起来会是极端值，也不得被悄悄补进估计。"""
    complete = [_observation(seed, 1.0, 1.0) for seed in range(15)]  # 全部配对差为 0
    missing = [outcomes.BlockObservation(seed=200, control_severity=None, treatment_severity=999.0)]
    observations = {family: complete + missing for family in FAMILIES}
    report = outcomes.analyse_families(observations)
    for family in FAMILIES:
        result = report[family]
        assert result.effect == pytest.approx(0.0)
        assert result.n_missing == 1


def test_all_blocks_missing_in_one_family_raises_instead_of_guessing():
    observations = _uniform_observations(5, control=1.0, treatment=2.0)
    observations["price_crash"] = [
        outcomes.BlockObservation(seed=i, control_severity=None, treatment_severity=None)
        for i in range(5)
    ]
    with pytest.raises(outcomes.OutcomesError, match="全部 block 都缺失"):
        outcomes.analyse_families(observations)


def test_missing_family_in_the_observation_mapping_is_rejected():
    observations = _uniform_observations(5, control=1.0, treatment=2.0)
    del observations["liquidity_dry_up"]
    with pytest.raises(outcomes.OutcomesError, match="缺少家族"):
        outcomes.analyse_families(observations)


def test_empty_block_list_for_a_family_is_rejected():
    observations = _uniform_observations(5, control=1.0, treatment=2.0)
    observations["liquidation_cascade"] = []
    with pytest.raises(outcomes.OutcomesError, match="没有任何观察"):
        outcomes.analyse_families(observations)


# --------------------------------------------------------------------------- #
# 确定性
# --------------------------------------------------------------------------- #


def test_bootstrap_is_deterministic_given_the_same_seed():
    observations = _uniform_observations(20, control=1.0, treatment=1.6)
    first = outcomes.analyse_families(observations, bootstrap_seed=7)
    second = outcomes.analyse_families(observations, bootstrap_seed=7)
    for family in FAMILIES:
        assert first[family].ci_low == second[family].ci_low
        assert first[family].ci_high == second[family].ci_high
        assert first[family].p_value == second[family].p_value


# --------------------------------------------------------------------------- #
# 真实数据端到端（较慢：跑真实配对 block）
# --------------------------------------------------------------------------- #


def test_analyse_ai_track_runs_real_paired_blocks_end_to_end():
    report = outcomes.analyse_ai_track(outcomes.preview_seeds(8))
    for family in FAMILIES:
        result = report[family]
        assert result.n_blocks == 8
        assert result.n_missing == 0
        assert result.primary_metric == "severity"


def test_cascade_occurrence_requires_at_least_two_accounts_not_just_one_liquidation():
    """强平连锁的发生判据是"同一 chain_id 下 >=2 个账户"，不是"发生过一次强平就算"。

    冻结决定明确排除了 ``max(chain_depth)>=1``；本条断言锁定判据没有退化成更松的
    ``chain_severity>=1``（那会把单账户强平也计成一次连锁发生，与设计文档矛盾）。
    seed 50003 是已知真实数据：control 侧两账户连锁（发生），treatment 侧无强平（未发生）。
    """
    observations = outcomes.observe_ai_block(50_003)
    cascade = observations["liquidation_cascade"]
    assert cascade.control_severity == 2.0
    assert cascade.control_occurrence == 1.0  # 2 个账户 -> 发生
    assert cascade.treatment_severity == 0.0
    assert cascade.treatment_occurrence == 0.0  # 0 个账户 -> 未发生


# --------------------------------------------------------------------------- #
# OWNER_N_OF_1 轨：描述性对比，不进主要结论
# --------------------------------------------------------------------------- #


def test_owner_comparison_is_descriptive_and_not_a_significance_test():
    """所有者对比只呈现差值，没有 CI/p 值这类字段——结构上就不可能被当成检验结果。"""
    owner_severities = {"price_crash": 0.02, "liquidity_dry_up": 0.5, "liquidation_cascade": 3.0}
    reference = {family: _observation(0, control=0.01, treatment=0.03) for family in FAMILIES}
    comparisons = outcomes.describe_owner_scenario(owner_severities, reference)
    for family in FAMILIES:
        comparison = comparisons[family]
        assert not hasattr(comparison, "p_value")
        assert not hasattr(comparison, "ci_low")
    assert comparisons["price_crash"].owner_minus_linear == pytest.approx(0.02 - 0.01)
    assert comparisons["price_crash"].owner_minus_threshold == pytest.approx(0.02 - 0.03)


def test_owner_comparison_never_enters_the_holm_corrected_ai_track_report():
    """反面：所有者对比与 AI 轨的 OutcomeReport 是两个不相干的类型，不共享 Holm 范围。"""
    owner_severities = {"price_crash": 0.02, "liquidity_dry_up": 0.5, "liquidation_cascade": 3.0}
    reference = {family: _observation(0, control=0.01, treatment=0.03) for family in FAMILIES}
    comparisons = outcomes.describe_owner_scenario(owner_severities, reference)
    report = outcomes.analyse_families(_uniform_observations(20, control=1.0, treatment=2.0))
    assert not isinstance(comparisons, outcomes.OutcomeReport)
    assert all(f"{f}.severity" in report.holm_corrected_tests for f in FAMILIES)
    assert not any(isinstance(v, outcomes.FamilyResult) for v in comparisons.values())


def test_owner_comparison_rejects_missing_family_in_severities():
    reference = {family: _observation(0, control=0.01, treatment=0.03) for family in FAMILIES}
    with pytest.raises(outcomes.OutcomesError, match="缺少家族"):
        outcomes.describe_owner_scenario({"price_crash": 0.02}, reference)


def test_owner_comparison_rejects_missing_reference_policy_severity():
    owner_severities = {"price_crash": 0.02, "liquidity_dry_up": 0.5, "liquidation_cascade": 3.0}
    reference = {family: _observation(0, control=0.01, treatment=0.03) for family in FAMILIES}
    reference["liquidity_dry_up"] = outcomes.BlockObservation(
        seed=0, control_severity=None, treatment_severity=0.03
    )
    with pytest.raises(outcomes.OutcomesError, match="参照策略观察不完整"):
        outcomes.describe_owner_scenario(owner_severities, reference)


def test_single_account_liquidation_does_not_count_as_a_cascade_occurrence():
    """反面对照：seed 50009 是已知真实数据，control 侧单账户被强平（severity=1）——
    这不构成"两个及以上账户"的连锁发生，occurrence 必须是 0，不是 1。
    """
    observations = outcomes.observe_ai_block(50_009)
    cascade = observations["liquidation_cascade"]
    assert cascade.control_severity == 1.0
    assert cascade.control_occurrence == 0.0


# --------------------------------------------------------------------------- #
# T919：预注册正式分析、重放完整性、敏感性与结论边界
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def small_frozen_index(tmp_path_factory):
    """2 个真实 block 的迷你冻结 index：驱动全部分析代码路径但不付 168 重放的成本。"""
    from market_game_sim.experiment.h2 import evidence_index, formal_ai

    root = tmp_path_factory.mktemp("t919-sampling")
    formal_ai.sample_ai_blocks(count=2, out_dir=root)
    return evidence_index.freeze_index(root / "idx.json", out_dir=root, required_blocks=2)


def test_formal_analysis_binds_to_index_and_frozen_plan(small_frozen_index):
    from market_game_sim.experiment.h2 import analysis

    payload = analysis.run_formal_analysis(index_path=small_frozen_index)
    import hashlib

    assert (
        payload["index_binding"]["sha256"]
        == hashlib.sha256(small_frozen_index.read_bytes()).hexdigest()
    )
    assert payload["analysis_plan"] == analysis.frozen_analysis_plan()
    for family in FAMILIES:
        assert payload["primary"][family]["n_blocks"] == 2
        assert payload["primary"][family]["occurrence_role"] == "descriptive"
        assert 0.0 <= payload["sensitivity"]["sign_flip_p"][family] <= 1.0
        assert payload["sensitivity"]["role"] == "boundary_evidence_only"
    assert payload["conclusion_boundary"]["composite_score"] is False
    assert payload["conclusion_boundary"]["owner_inference"] == "absent_ai_track_only"
    blob = json.dumps(payload)
    assert "holm_significant" in blob  # 主要终点有 Holm 判定
    assert "composite" not in blob.replace("composite_score", "")  # 无综合分数


def test_replay_digest_mismatch_fails_closed(small_frozen_index):
    """index 的事件哈希被篡改后，重放校验必须拒绝分析（fail-closed）。"""
    from market_game_sim.experiment.h2 import analysis

    tampered = small_frozen_index.with_name("tampered-idx.json")
    payload = json.loads(small_frozen_index.read_text(encoding="utf-8"))
    payload["included"][0]["arms"]["linear"]["events_sha256"] = "0" * 64
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(analysis.AnalysisError, match="重放事件哈希"):
        analysis.run_formal_analysis(index_path=tampered)


def test_conclusion_text_enforces_frozen_syntax():
    from market_game_sim.experiment.h2 import analysis

    good = "本模型族在冻结参数范围与 seed 分布内的结论，不外推至人类被试。"
    analysis.check_conclusion_text(good)
    with pytest.raises(analysis.AnalysisError, match="禁用简写"):
        analysis.check_conclusion_text("这表明存在人类效应。")
    with pytest.raises(analysis.AnalysisError, match="限定词"):
        analysis.check_conclusion_text("效应显著，可以推广。")


def test_sign_flip_p_reaches_both_extremes():
    from market_game_sim.experiment.h2 import analysis

    one_sided = [1.0] * 12
    assert analysis._sign_flip_p(one_sided, draws=999, seed=0) == pytest.approx(1 / 1000)
    balanced = [1.0, -1.0] * 6
    assert analysis._sign_flip_p(balanced, draws=999, seed=0) > 0.5


def test_freeze_analysis_is_deterministic_and_refuses_rewrite(small_frozen_index, tmp_path):
    from market_game_sim.experiment.h2 import analysis

    target = tmp_path / "H2-ai-analysis.json"
    path = analysis.freeze_analysis(index_path=small_frozen_index, out_path=target)
    first = path.read_bytes()
    assert analysis.freeze_analysis(index_path=small_frozen_index, out_path=target) == path
    assert path.read_bytes() == first

    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(analysis.AnalysisError, match="不可原地改写"):
        analysis.freeze_analysis(index_path=small_frozen_index, out_path=target)


def test_projection_matches_observe_ai_block():
    """冻结归档钉死了 outcomes.py 的哈希——analysis 的投影必须与之逐值等价。"""
    from market_game_sim.experiment.h2 import analysis, runner

    seed = 50_000
    block = runner.run_ai_block(seed)
    assert analysis._observe_block(seed, block) == outcomes.observe_ai_block(seed)
