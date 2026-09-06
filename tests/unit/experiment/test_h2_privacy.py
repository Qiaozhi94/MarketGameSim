"""AC-308：隐私边界、阶段可辨识与解盲规则。

T905 已实现，xfail 骨架相应摘除。

PII 扫描的负向用例逐类别地塞入直接标识符——只测邮箱不能证明手机号、支付卡号和证件号
也在被扫，而这类扫描一旦漏一类，漏的那类就会静默地进成果包。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import pytest

from market_game_sim.experiment.h2 import delivery, session

# --------------------------------------------------------------------------- #
# 阶段标识（UX-303）
# --------------------------------------------------------------------------- #


def test_training_and_formal_stages_are_distinguishable():
    assert session.stage_of(session.start_training()) == "training"
    assert session.stage_of(session.start_formal()) == "formal"


def test_owner_is_only_ever_a_pseudonym():
    """仓库不保存身份映射，所有者只以研究假名出现。"""
    assert session.OWNER_ID.startswith("owner-")
    assert delivery.build_owner_bundle().owner_id == session.OWNER_ID


# --------------------------------------------------------------------------- #
# 解盲规则
# --------------------------------------------------------------------------- #


def test_results_stay_blinded_until_all_formal_scenarios_finish():
    with pytest.raises(session.StillBlinded):
        session.read_results(session.owner_progress(completed=23))
    assert session.read_results(session.owner_progress(completed=24))["unblinded"] is True


def test_required_scenario_count_comes_from_the_contract():
    """24 这个数取自冻结合同，不在代码里另写一份。"""
    assert session.owner_progress(completed=0).required == 24


def test_blinding_has_no_peek_bypass():
    """差一个场景也不放行——"只看一眼"正是解盲规则要挡住的东西。"""
    for completed in range(0, 24):
        with pytest.raises(session.StillBlinded):
            session.read_results(session.owner_progress(completed=completed))


def test_negative_progress_is_rejected():
    with pytest.raises(session.SessionError):
        session.owner_progress(completed=-1)


# --------------------------------------------------------------------------- #
# 成果包与 PII 扫描
# --------------------------------------------------------------------------- #


def test_clean_bundle_has_no_pii():
    bundle = delivery.build_owner_bundle({"scenarios": 24, "note": "owner-1 完成全部正式场景"})
    assert delivery.scan_for_pii(bundle) == []


@pytest.mark.parametrize(
    "category, payload",
    [
        ("email", "联系人 owner@example.com"),
        ("phone", "+86 138 0013 8000"),
        ("payment", "4111 1111 1111 1111"),
        ("id_card", "110101199003072316"),
    ],
)
def test_every_pii_category_is_detected(category, payload):
    """逐类别变异：任一类直接标识符混进成果包都必须被扫出来。"""
    bundle = delivery.build_owner_bundle({"leak": payload})
    assert category in delivery.scan_for_pii(bundle)


def test_pii_scan_reaches_nested_contents():
    """扫描必须穿透嵌套结构，否则把泄漏塞进子对象就能绕过。"""
    bundle = delivery.build_owner_bundle({"a": {"b": ["ok", {"c": "x@y.zz"}]}})
    assert delivery.scan_for_pii(bundle) == ["email"]


# --------------------------------------------------------------------------- #
# 证据级别与研究声明资格
# --------------------------------------------------------------------------- #


def test_owner_bundle_is_experiment_preview_and_descriptive():
    bundle = delivery.build_owner_bundle()
    assert bundle.evidence_class == "experiment-preview"
    assert bundle.marked_descriptive is True
    assert bundle.research_claim_eligible is False


def test_formal_client_exposes_no_pause_step_or_reparameterisation():
    """正式态控制项是闭集：暂停会给所有者参照策略没有的无限思考时间。"""
    controls = session.formal_client_controls()
    for forbidden in ("pause", "step", "set_param", "reveal_future"):
        assert forbidden not in controls
    assert "submit_order" in controls and "abort_session" in controls
