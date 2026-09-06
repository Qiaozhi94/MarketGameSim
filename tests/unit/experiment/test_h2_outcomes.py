"""AC-305：三个结果家族的分别估计与多重性。

骨架状态：本文件是 `ready-for-development` 前置要求的 strict-xfail 占位（tasks §0）。
每条测试写的是**实现后应当为真**的断言，现在因为 `experiment/h2/outcomes.py` 尚不存在而失败；
`strict=True` 保证一旦实现并通过，测试会 XPASS 报错，提醒删掉 xfail 标记。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import pytest

FAMILIES = ("price_crash", "liquidity_dry_up", "liquidation_cascade")


@pytest.mark.xfail(strict=True, reason="T912 未实现：experiment/h2/outcomes.py 尚不存在")
def test_ac305_primary_estimand_is_severity_for_every_family():
    """主要 estimand 是严重程度配对差；发生指标只作描述性（校准结论）。"""
    from market_game_sim.experiment.h2 import outcomes

    report = outcomes.analyse_ai_track(outcomes.load_frozen_index())
    for family in FAMILIES:
        assert report[family].primary_metric == "severity"
        assert report[family].occurrence_role == "descriptive"


@pytest.mark.xfail(strict=True, reason="T912 未实现：Holm 校正尚未落地")
def test_ac305_holm_applies_to_the_three_severity_tests_only():
    """Holm 只控三个严重程度主要终点（DQ-304）。"""
    from market_game_sim.experiment.h2 import outcomes

    report = outcomes.analyse_ai_track(outcomes.load_frozen_index())
    expected = sorted(family + ".severity" for family in FAMILIES)
    assert sorted(report.holm_corrected_tests) == expected


@pytest.mark.xfail(strict=True, reason="T912 未实现：综合分数禁令尚未落地")
def test_ac305_no_composite_crash_score_is_produced():
    """三家族分别报告，不生成综合崩盘得分。"""
    from market_game_sim.experiment.h2 import outcomes

    report = outcomes.analyse_ai_track(outcomes.load_frozen_index())
    assert not any("composite" in key for key in report)
