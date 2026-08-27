---
report_type: fix-verification
round: 4
date: 2026-08-27
prior_report: "Round 3 (5 High + 4 Medium carried-forward/open); CURRENT-code.md recreated by reviewer"
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
    fix_summary: "kernel 记录最后提交 MARKET_DATA_PUBLISH；observe 执行时快照最新边界"
    regression_test: "tests/integration/test_tape_cursor.py::test_post_trade_observation_consumes_latest_market_interval"
    location: src/market_game_sim/experiment/runner.py:283
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C002
    title: 失败事务的 staged 游标泄漏到下一次提交
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: cursor-commit-before-consume
    status: fixed
    fix_summary: "Round 3 修复：staging 从共享 world dict 移到事件 r0，随事务 buffer 提交/丢弃；失败后复用 world 不泄漏"
    regression_test: "tests/integration/test_tape_cursor.py::test_failure_after_staging_does_not_leak_into_next_transaction"
    location: src/market_game_sim/agent/handler.py:679
    first_seen_round: 1
    resolved_round: 4
  - id: R018-C003
    title: V1 信息集仍未消费真实 tape/闭合 K 线
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: test-simulates-itself
    status: fixed
    fix_summary: "observe 把 public_trades/cursor 快照附到 decide 事件；decide 从事件读取真实 tape；新增零成交 bar 填充"
    regression_test: "tests/unit/agent/test_tape_ewma.py::test_completed_bars_with_zero_fill_pads_empty_bars"
    location: src/market_game_sim/agent/handler.py:502
    first_seen_round: 1
    resolved_round: 4
  - id: R018-C004
    title: 空头同向加仓绕过裁剪
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: partial-symmetric-fix
    status: fixed
    fix_summary: "绝对仓位比较并保持符号，多空对称"
    regression_test: "tests/unit/agent/test_constraint.py::test_same_side_add_is_clipped_symmetrically_for_long_and_short"
    location: src/market_game_sim/agent/constraint.py:142
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C005
    title: 运行族配置仍非闭合可构造入口
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: gate-not-wired-to-entrypoint
    status: fixed
    fix_summary: "seed_plan/l_level/m_level/stress_protocol 成为 ExperimentConfig 一等字段；未知字段被 dataclass 构造器拒绝"
    regression_test: "tests/integration/test_run_family_entrypoint.py::test_unknown_field_rejected_by_constructor"
    location: src/market_game_sim/experiment/config.py:55
    first_seen_round: 1
    resolved_round: 4
  - id: R018-C006
    title: StressProtocolV1 仍接受非法版本和事件
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: validator-accepts-forbidden-variants
    status: fixed
    fix_summary: "schema_version 恒 1；event_type 闭集 MARKET_ORDER；params 闭集 {side, quantity_units}"
    regression_test: "tests/unit/experiment/test_stress_protocol.py::test_protocol_rejects_wrong_schema_version"
    location: src/market_game_sim/experiment/stress_protocol.py:30
    first_seen_round: 1
    resolved_round: 4
  - id: R018-C007
    title: 多观察区间决策证据仍写错 cursor_from
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: partial-chain-verifier
    status: fixed
    fix_summary: "decide 从观察快照读 cursor_from（删除 e1_0 硬编码）；240 事务多区间全链验证通过"
    regression_test: "tests/integration/test_decision_chain_verifier.py::test_multi_interval_goal_chain_passes_and_all_trade_hops_resolve"
    location: src/market_game_sim/agent/handler.py:553
    first_seen_round: 1
    resolved_round: 4
  - id: R018-C008
    title: reserved 重复且遗漏候选手续费
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: duplicated-admission-formula
    status: fixed
    fix_summary: "委托 ledger 并计入候选费用"
    regression_test: "tests/unit/agent/test_constraint.py::test_candidate_new_open_fee_is_reserved"
    location: src/market_game_sim/agent/constraint.py:186
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C009
    title: V1 类型、版本和偏好边界未完全闭合
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: shallow-schema-validation
    status: fixed
    fix_summary: "int 字段用 type is int 排除 bool；InformationSetV1/AgentInternalStateV1 校验版本=1；risk_appetite 边界 [500,20000]"
    regression_test: "tests/unit/schema/test_event_schema.py::test_integer_fields_reject_bool"
    location: src/market_game_sim/evidence/evidence_guard.py:126
    first_seen_round: 1
    resolved_round: 4
  - id: R018-C010
    title: EWMA 依赖观察批次划分
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: batch-partition-dependent-state
    status: fixed
    fix_summary: "每 fill 取整"
    regression_test: "tests/unit/agent/test_tape_ewma.py::test_ewma_is_invariant_to_observation_batch_partition"
    location: src/market_game_sim/agent/tape.py:64
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C011
    title: 报告入口没有授权实际 evidence class/结论模板
    severity: medium
    category: test-coverage
    root_cause: root-cause
    origin: process-gap
    pattern_tag: gate-not-wired-to-entrypoint
    status: fixed
    fix_summary: "run_paired 加 evidence_class 参数；legacy(None) 为独立族；声明族未提供 evidence_class 拒绝"
    regression_test: "tests/integration/test_evidence_guard_entrypoint.py::test_run_paired_requires_evidence_class_for_declared_family"
    location: src/market_game_sim/experiment/runner.py:184
    first_seen_round: 1
    resolved_round: 4
  - id: R018-C012
    title: manifest 仍允许 seed_plan 缺失
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: manifest-contract-drift
    status: fixed
    fix_summary: "seed_plan 改为必填闭合结构（FR-027）；单种子用 {n_seeds:1, seeds:[seed]}；schema 移除 optional"
    regression_test: "tests/integration/test_showcase_bundle.py::test_manifest_requires_seed_plan_even_for_single_seed"
    location: src/market_game_sim/showcase/manifest.py:50
    first_seen_round: 1
    resolved_round: 4
  - id: R018-C013
    title: Round 2 使用自证测试错误关闭报告
    severity: medium
    category: test-coverage
    root_cause: root-cause
    origin: process-gap
    pattern_tag: self-approved-closure
    status: fixed
    fix_summary: "Round 3 逐条用真实路径复现（长运行/故障注入/构造器负例），Round 4 独立复核每条回归测试的断言质量"
    regression_test: "Round 3 的 8 条真实路径测试（见各 issue regression_test）"
    location: docs/reviews/RETROSPECTIVE.md:644
    first_seen_round: 3
    resolved_round: 4
---

# 0.1.5 T203—T212 代码修复复核（Round 4）

**结论：Round 4 复核通过。Round 3 的 8 条 carried-forward + C013 全部修复，每条配真实路径
正反回归测试；本地 `python tools/verify.py` 全绿（2107 测试）。CI 待触发作为最终门禁。**

## Round 4 复核（diff-only，含对 Round 3 每条发现的独立验证）

| ID | Round 3 断言 | 修复后验证 | 结果 |
|---|---|---|---|
| R018-C002 | staging 残留泄漏到下一事务 | staging 移到事件 r0；`test_failure_after_staging_does_not_leak_into_next_transaction` 模拟 staging 后抛错 + 复用 world，断言 cursor 未被失败观察推进 | ✅ |
| R018-C003 | decide 的 iset 无 public_trades | observe 把 public_trades/cursor 快照附到 decide；`_completed_bars_with_zero_fill` 补零成交 bar；240 事务验证 | ✅ |
| R018-C005 | seed_plan 等只能动态挂属性 | 字段成为一等构造参数；`ExperimentConfig(unknown_field=...)` 抛 TypeError | ✅ |
| R018-C006 | 接受 schema_version=99/ALIEN_EVENT | `__post_init__` 闭合版本/事件/params；4 个新负例测试 | ✅ |
| R018-C007 | evidence.cursor_from 硬编码 e1_0 | 从观察快照读 cursor_from；240 事务多区间全链验证通过 | ✅ |
| R018-C009 | bool 通过 int 校验 | `type is int` 排除 bool；V1 版本 + 偏好边界负例 | ✅ |
| R018-C011 | run_paired 硬编码 evidence class | `evidence_class` 参数 + legacy 独立族 + 6 个 entrypoint 测试 | ✅ |
| R018-C012 | seed_plan 可缺失 | 必填闭合结构；单种子自动表达；3 个负例测试 | ✅ |

## 停止条件

- High/Medium 清零（0/0/0）
- 本地 `python tools/verify.py` 全绿（2107 测试）
- CI 最终门禁：待触发（push 后 `gh run watch`）

CURRENT-code.md 在 CI 全绿且检视人独立复核后由检视人删除归档（R018-C013 教训：不重蹈自证关闭）。
