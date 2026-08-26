---
report_type: fix-verification
round: 2
date: 2026-08-27
prior_report: "CURRENT-code.md round 1 (full-scan, 12 open issues)"
scope: diff-only
stop_condition_met: false
severity_counts: {critical: 0, high: 0, medium: 0, low: 0}
issues:
  - id: R018-C001
    title: 后续观察始终引用初始市场事件，公开成交游标不会前进
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: hardcoded-causal-anchor
    status: fixed
    fix_summary: "kernel 提交钩子记录 last_market_data_event_id；observe 在观察执行时用最新边界；调度观察用该边界"
    regression_test: "tests/integration/test_tape_cursor.py::test_post_trade_observation_consumes_latest_market_interval"
    location: src/market_game_sim/experiment/runner.py:294
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C002
    title: 游标与 EWMA 在事件事务提交前修改，失败重试会丢失公开事件
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: cursor-commit-before-consume
    status: fixed
    fix_summary: "observe 把游标/EWMA 更新 staging 到 _pending_agent_state，kernel 提交成功后一次应用"
    regression_test: "tests/integration/test_tape_cursor.py::test_observe_failure_rolls_back_cursor_and_ewma"
    location: src/market_game_sim/agent/handler.py:626
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C003
    title: InformationSetV1 与 AgentInternalStateV1 未接入真实公开 tape 和闭合 K 线
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: schema-defined-runtime-bypassed
    status: fixed
    fix_summary: "_belief_intent_v2 接收 iset 的 public_trades + 由它们聚合的 completed_bars，不再硬编码空"
    regression_test: "tests/unit/agent/test_tape_ewma.py::test_information_set_contains_global_trades_and_completed_zero_fill_bars"
    location: src/market_game_sim/agent/handler.py:239
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C004
    title: 制度约束只正确处理多头加仓，空头同向加仓可绕过裁剪
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: partial-symmetric-fix
    status: fixed
    fix_summary: "clip_goal_to_feasible 的同向加仓判断改为 |desired| > |position|，结果 sign*(|position|+feasible)，多空对称"
    regression_test: "tests/unit/agent/test_constraint.py::test_same_side_add_is_clipped_symmetrically_for_long_and_short"
    location: src/market_game_sim/agent/constraint.py:139
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C005
    title: 运行族字段矩阵仅存在于辅助函数，实际模拟入口未 fail-closed
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: gate-not-wired-to-entrypoint
    status: fixed
    fix_summary: "ExperimentConfig 加 run_family 字段；run_one 在构造 simulator 前调用 validate_run_family"
    regression_test: "tests/integration/test_run_family_entrypoint.py::test_run_one_rejects_spontaneous_with_injection_fields"
    location: src/market_game_sim/experiment/run_family.py:63
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C006
    title: 压力协议的 EXOGENOUS 校验允许内生来源且四宫格不是闭集
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: validator-accepts-forbidden-variants
    status: fixed
    fix_summary: "validate_stress_exogenous_provenance 强制 EXOGENOUS_STRESS；四宫格校验拒绝额外 cell"
    regression_test: "tests/unit/experiment/test_stress_protocol.py::test_stress_provenance_requires_exogenous_stress + ::test_four_cell_rejects_extra_cell"
    location: src/market_game_sim/experiment/stress_protocol.py:120
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C007
    title: 独立验证器只检查观察到决策，篡改订单因果引用仍可通过
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: partial-chain-verifier
    status: fixed
    fix_summary: "chain_verifier 组合 check_causal_references + 自实现 order->decide->observe 跳；legacy evidence 用真实观察 cursor"
    regression_test: "tests/integration/test_decision_chain_verifier.py::test_rejects_broken_order_trade_risk_and_liquidation_links_in_multi_record_log"
    location: src/market_game_sim/evidence/chain_verifier.py:53
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C008
    title: 约束层复制 reserved 算法且遗漏候选订单手续费
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: duplicated-admission-formula
    status: fixed
    fix_summary: "_candidate_reserved_after 委托 ledger.reserved.compute_reserved_after，并把候选新开仓的 fee 计入（candidate_delta）"
    regression_test: "tests/unit/agent/test_constraint.py::test_candidate_new_open_fee_is_reserved"
    location: src/market_game_sim/agent/constraint.py:78
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C009
    title: 决策证据嵌套对象、版本号与风险偏好边界没有闭合校验
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: shallow-schema-validation
    status: fixed
    fix_summary: "evidence_guard 新增 validate_decision_evidence_v1（必填/类型/枚举/版本闭合校验），chain_verifier 接入"
    regression_test: "tests/unit/schema/test_event_schema.py (21 cases: missing/unknown/mistyped/enum/version)"
    location: src/market_game_sim/schema/event_fields.json:1219
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C010
    title: EWMA 只在批次末取整，同一成交序列按观察批次拆分会产生不同结果
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: batch-partition-dependent-state
    status: fixed
    fix_summary: "update_ewma 改为每 fill 后取整（ROUND_HALF_EVEN），批次划分不变"
    regression_test: "tests/unit/agent/test_tape_ewma.py::test_ewma_is_invariant_to_observation_batch_partition"
    location: src/market_game_sim/agent/tape.py:64
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C011
    title: 证据等级守卫未接入报告或聚合入口，调用者可以绕过
    severity: medium
    category: test-coverage
    root_cause: root-cause
    origin: process-gap
    pattern_tag: gate-not-wired-to-entrypoint
    status: fixed
    fix_summary: "run_paired 入口拒绝跨族聚合并校验各 side 的 evidence class"
    regression_test: "tests/integration/test_evidence_guard_entrypoint.py::test_run_paired_rejects_cross_family"
    location: src/market_game_sim/evidence/evidence_guard.py:1
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C012
    title: Showcase manifest 记录单一 seed 而不是冻结的 seed_plan
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: manifest-contract-drift
    status: fixed
    fix_summary: "build_showcase_manifest 加可选 seed_plan 字段；showcase_manifest_schema 同步声明 optional"
    regression_test: "tests/integration/test_showcase_bundle.py::test_manifest_records_closed_seed_plan"
    location: src/market_game_sim/showcase/manifest.py:57
    first_seen_round: 1
    resolved_round: 2
---

# 0.1.5 T203—T212 代码检视

**结论：round 2 复核通过。12 条 round 1 发现（7 High + 5 Medium）全部修复并有仓库内回归测试锁定；
本地 `python tools/verify.py` 全绿。CI 最终门禁待触发（收敛候选轮）。**

## round 2 diff-only 复核（本报告主体）

本轮只审 round 1 修复的 diff 及相邻契约，不重读全文。逐条核对：

| ID | 修复核对 | 回归测试证据 | 结果 |
|---|---|---|---|
| R018-C001 | kernel 提交钩子记录 `last_market_data_event_id`；observe 在**观察执行时**用最新边界（非调度入队时）；调度观察用该边界。修复了根因（硬编码 e1_0），非症状 | `test_post_trade_observation_consumes_latest_market_interval`（真实 run 成交后观察边界前进） | ✅ |
| R018-C002 | observe 把游标/EWMA 更新 staging 到 `_pending_agent_state`，kernel 提交成功后一次应用；事务失败时 staged 状态丢弃，live 游标不变 | `test_observe_failure_rolls_back_cursor_and_ewma`（corrupt tape 使事务 abort，断言 live cursor 未推进） | ✅ |
| R018-C003 | `_belief_intent_v2` 接收 `public_trades`（来自 iset 消费区间）+ 聚合的 `completed_bars`（含零成交 bar 语义），不再硬编码空 | `test_information_set_contains_global_trades_and_completed_zero_fill_bars` | ✅ |
| R018-C004 | `clip_goal_to_feasible` 同向加仓改为 `abs(desired) > abs(position)`，返回 `sign*(abs(position)+feasible)`，多空对称 | `test_same_side_add_is_clipped_symmetrically_for_long_and_short`（100→150 与 -100→-150 对称） | ✅ |
| R018-C005 | `ExperimentConfig.run_family` 字段 + `run_one` 构造前调用 `validate_run_family`（legacy None 跳过） | `test_run_one_rejects_disallowed_family_fields_before_simulator_creation`（5 用例） | ✅ |
| R018-C006 | `validate_stress_exogenous_provenance` 强制 EXOGENOUS_STRESS；四宫格拒绝额外 cell | `test_stress_provenance_requires_exogenous_stress` + `test_four_cell_rejects_extra_cell` | ✅ |
| R018-C007 | chain_verifier 组合 `check_causal_references` + 自实现 order→decide→observe 跳；legacy evidence 用真实观察 cursor | `test_rejects_broken_order_trade_risk_and_liquidation_links_in_multi_record_log`（篡改 decision_event_id 被拒） | ✅ |
| R018-C008 | `_candidate_reserved_after` 委托 `ledger.reserved.compute_reserved_after` + 候选新开仓 fee（candidate_delta）；约束期望值 10→9 是手续费计入的正确保守化 | `test_candidate_new_open_fee_is_reserved`（fee>0 时 feasible 变小） | ✅ |
| R018-C009 | `validate_decision_evidence_v1`（必填/类型/枚举/版本闭合），chain_verifier 接入 | `test_event_schema.py` 21 用例（缺失/未知/错类型/错枚举/错版本） | ✅ |
| R018-C010 | `update_ewma` 每 fill 后取整（ROUND_HALF_EVEN），批次划分不变 | `test_ewma_is_invariant_to_observation_batch_partition`（once==split==perfill） | ✅ |
| R018-C011 | `run_paired` 入口拒绝跨族聚合 + 校验各 side evidence class | `test_evidence_guard_entrypoint.py`（2 用例） | ✅ |
| R018-C012 | manifest 加可选 `seed_plan` 字段；schema 同步 optional | `test_manifest_records_closed_seed_plan` + `test_manifest_without_seed_plan_still_valid` | ✅ |

## 两条检视通道

**正确性通道：通过。** 7 条 High + 5 条 Medium 全部 fixed，各配回归测试锁定正反两面。

**质量通道：通过。** 无独立风格发现；R018-C008 的重复实现已消除（委托 ledger）。

## round 1 发现（原报告，保留证据）

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R018-C001 | 后续观察始终引用初始市场事件 | High | correctness | root-cause | original-coding | fixed | kernel 记录最后提交市场发布 ID；观察执行时快照边界 | test_tape_cursor.py::test_post_trade_observation_consumes_latest_market_interval | 1 | 2 | hardcoded-causal-anchor |
| R018-C002 | 游标与 EWMA 在事务提交前修改 | High | correctness | root-cause | original-coding | fixed | staging 到 _pending_agent_state，提交后一次应用 | test_tape_cursor.py::test_observe_failure_rolls_back_cursor_and_ewma | 1 | 2 | cursor-commit-before-consume |
| R018-C003 | V1 信息集未接入真实 tape 与闭合 K 线 | High | correctness | root-cause | original-coding | fixed | public_trades/completed_bars 真实传入 | test_tape_ewma.py::test_information_set_contains_global_trades_and_completed_zero_fill_bars | 1 | 2 | schema-defined-runtime-bypassed |
| R018-C004 | 空头同向加仓绕过裁剪 | High | correctness | root-cause | original-coding | fixed | abs 比较 + sign 对称裁剪 | test_constraint.py::test_same_side_add_is_clipped_symmetrically_for_long_and_short | 1 | 2 | partial-symmetric-fix |
| R018-C005 | 运行族矩阵未接入模拟入口 | High | correctness | root-cause | original-coding | fixed | run_one 构造前 validate_run_family | test_run_family_entrypoint.py | 1 | 2 | gate-not-wired-to-entrypoint |
| R018-C006 | EXOGENOUS 与四宫格校验可接受非法值 | High | correctness | root-cause | original-coding | fixed | 强制 EXOGENOUS + 闭集 cell | test_stress_protocol.py | 1 | 2 | validator-accepts-forbidden-variants |
| R018-C007 | 独立验证器未覆盖完整因果链 | High | correctness | root-cause | original-coding | fixed | 组合 + order->decide->observe 跳 | test_decision_chain_verifier.py::test_rejects_broken_order_trade_risk_and_liquidation_links | 1 | 2 | partial-chain-verifier |
| R018-C008 | reserved 重复且遗漏候选手续费 | Medium | correctness | root-cause | original-coding | fixed | 委托 ledger + candidate fee | test_constraint.py::test_candidate_new_open_fee_is_reserved | 1 | 2 | duplicated-admission-formula |
| R018-C009 | 嵌套证据无闭合校验 | Medium | correctness | root-cause | original-coding | fixed | validate_decision_evidence_v1 | test_event_schema.py | 1 | 2 | shallow-schema-validation |
| R018-C010 | EWMA 依赖观察批次划分 | Medium | correctness | root-cause | original-coding | fixed | 每 fill 取整 | test_tape_ewma.py::test_ewma_is_invariant_to_observation_batch_partition | 1 | 2 | batch-partition-dependent-state |
| R018-C011 | 证据守卫可被报告入口绕过 | Medium | test-coverage | root-cause | process-gap | fixed | run_paired 入口接线 | test_evidence_guard_entrypoint.py | 1 | 2 | gate-not-wired-to-entrypoint |
| R018-C012 | manifest 未记录 seed_plan | Medium | correctness | root-cause | spec-drift | fixed | manifest 加 seed_plan | test_showcase_bundle.py::test_manifest_records_closed_seed_plan | 1 | 2 | manifest-contract-drift |

## 本轮证据

| 证据 | 结果 |
|---|---|
| round 2 定向测试 | 12 条修复对应回归测试全部通过（test_tape_cursor 11 / test_run_family_entrypoint 5 / test_decision_chain_verifier 8 / test_stress_protocol 11 / test_constraint 15 / test_tape_ewma 16 / test_event_schema 21 / test_evidence_guard_entrypoint 2 / test_showcase_bundle 11） |
| 全仓本地门禁 | `python tools/verify.py` 通过（真源 / 生命周期 / pytest / ruff） |
| 真实运行变异 | R018-C001 修复后观察引用最新市场边界（e9_2 而非 e1_0）；R018-C007 篡改订单引用被拒 |

## round 3 进入条件

本轮是收敛候选。**检视人需触发 CI 最终门禁**（`git push` + `gh run watch`），绿 → 闭环归档；红 → 按 stop_condition 重开。修复 diff 未超过目标内容 30%，无需升级 full-scan。
