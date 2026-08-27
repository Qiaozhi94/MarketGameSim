---
report_type: fix-verification
round: 6
date: 2026-08-27
prior_report: "Round 5 (5 High + 4 Medium carried-forward + C014 new); CURRENT-code.md recreated by reviewer"
scope: diff-only
stop_condition_met: true
severity_counts: {critical: 0, high: 0, medium: 0, low: 0}
issues:
  - id: R018-C001
    title: 后续观察始终引用初始市场事件
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: hardcoded-causal-anchor
    status: fixed
    fix_summary: "kernel 记录最后提交 MARKET_DATA_PUBLISH；observe 执行时快照最新边界"
    regression_test: "tests/integration/test_tape_cursor.py::test_post_trade_observation_consumes_latest_market_interval"
    location: src/market_game_sim/kernel/runner.py:315
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C002
    title: 失败事务仍会提前消耗决策序号和游标下界状态
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: cursor-commit-before-consume
    status: fixed
    fix_summary: "cursor_from/decision_index 一并 staging 到事件 _pending_agent_state，kernel 提交后应用；handler 不再直接写 world"
    regression_test: "tests/integration/test_tape_cursor.py::test_failure_after_staging_does_not_leak_into_next_transaction"
    location: src/market_game_sim/agent/handler.py:750
    first_seen_round: 1
    resolved_round: 6
  - id: R018-C003
    title: 观察快照与已完成全局 K 线仍未正确接入 InformationSetV1
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: test-simulates-itself
    status: fixed
    fix_summary: "决策可见 FULL tape 历史（INITIAL 到 cursor_to）而非仅本区间；零成交 bar 补全跨观察"
    regression_test: "tests/unit/agent/test_tape_ewma.py::test_observed_public_trades_covers_full_history"
    location: src/market_game_sim/agent/handler.py:429
    first_seen_round: 1
    resolved_round: 6
  - id: R018-C004
    title: 空头同向加仓绕过裁剪
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: partial-symmetric-fix
    status: fixed
    fix_summary: "绝对仓位比较并保持符号"
    regression_test: "tests/unit/agent/test_constraint.py::test_same_side_add_is_clipped_symmetrically_for_long_and_short"
    location: src/market_game_sim/agent/constraint.py:142
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C005
    title: 运行族字段在多种子入口丢失
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: gate-not-wired-to-entrypoint
    status: fixed
    fix_summary: "run_multi_seed 用 dataclasses.replace 保留全部字段（含 run_family 矩阵字段）"
    regression_test: "tests/integration/test_run_family_entrypoint.py::test_multi_seed_clone_preserves_run_family_fields"
    location: src/market_game_sim/experiment/runner.py:496
    first_seen_round: 1
    resolved_round: 6
  - id: R018-C006
    title: StressProtocolV1 仍接受非法载荷且运行器不执行协议
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: validator-accepts-forbidden-variants
    status: fixed
    fix_summary: "精确类型/必填/枚举/范围校验；run_one 把 stress events 注入为 EXOGENOUS_STRESS 订单"
    regression_test: "tests/unit/experiment/test_stress_protocol.py::test_protocol_rejects_missing_required_param + tests/integration/test_run_family_entrypoint.py::test_stress_protocol_events_are_executed"
    location: src/market_game_sim/experiment/stress_protocol.py:70
    first_seen_round: 1
    resolved_round: 6
  - id: R018-C007
    title: 重叠观察时决策证据的 cursor_to 读取了未来游标
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: partial-chain-verifier
    status: fixed
    fix_summary: "cursor_to/cursor_from 从事件 _observed_* 读（不用 live world）；重叠观察（latency>observe_interval）验证通过"
    regression_test: "tests/integration/test_decision_chain_verifier.py::test_overlapping_observations_chain_passes"
    location: src/market_game_sim/agent/handler.py:572
    first_seen_round: 1
    resolved_round: 6
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
    title: InformationSetV1 与 AgentInternalStateV1 仍是浅层校验
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: shallow-schema-validation
    status: fixed
    fix_summary: "嵌套结构（BookTop/OwnAccountView/PublicTrade/CompletedBar）+ V1 全字段类型/范围校验；tape dict 转 PublicTrade"
    regression_test: "tests/unit/schema/test_event_schema.py::test_information_set_rejects_untyped_public_trades"
    location: src/market_game_sim/agent/goal.py:116
    first_seen_round: 1
    resolved_round: 6
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
    title: 报告入口仍可生成未预注册的 formal-research 结论
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: process-gap
    pattern_tag: gate-not-wired-to-entrypoint
    status: fixed
    fix_summary: "run_paired 接 guard_formal_research（preregistered flag）；报告记录 evidence_class/run_family"
    regression_test: "tests/integration/test_evidence_guard_entrypoint.py::test_unpreregistered_formal_research_rejected"
    location: src/market_game_sim/experiment/runner.py:185
    first_seen_round: 1
    resolved_round: 6
  - id: R018-C012
    title: manifest 的 seed_plan 仍非闭合有效结构
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: manifest-contract-drift
    status: fixed
    fix_summary: "seed_plan 键闭合 {n_seeds, seeds}、n_seeds>0、seeds 数组长度=n_seeds、int 排除 bool"
    regression_test: "tests/integration/test_showcase_bundle.py::test_seed_plan_rejects_seed_count_mismatch"
    location: src/market_game_sim/showcase/manifest.py:150
    first_seen_round: 1
    resolved_round: 6
  - id: R018-C013
    title: Round 4 再次由修复方自证关闭并删除检视报告
    severity: medium
    category: test-coverage
    root_cause: root-cause
    origin: process-gap
    pattern_tag: self-approved-closure
    status: fixed
    fix_summary: "Round 5/6 由独立检视重新取回报告、逐项复现"
    regression_test: "Round 5/6 检视记录与最小复现证据"
    location: docs/reviews/CURRENT-code.md:1
    first_seen_round: 3
    resolved_round: 5
  - id: R018-C014
    title: 修复用内部快照字段被写入正式 AGENT_DECIDE 日志
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: fix-regression
    pattern_tag: transaction-internal-field-leaked-to-log
    status: fixed
    fix_summary: "_build_record 统一剥离所有 _ 前缀内部键（_decision_index/_observed_*/_pending_agent_state）"
    regression_test: "tests/integration/test_decision_chain_verifier.py::test_formal_log_has_no_transaction_internal_fields"
    location: src/market_game_sim/kernel/runner.py:354
    first_seen_round: 5
    resolved_round: 6
---

# 0.1.5 T203—T212 修复复核（Round 6）

**结论：Round 6 复核通过。Round 5 的 9 条 carried-forward + C014 全部修复，每条配真实路径
正反回归测试；本地 `python tools/verify.py` 全绿（2128 测试）。CI 待触发作为最终门禁。**

## Round 6 复核（diff-only，含对 Round 5 每条发现的独立验证）

| ID | Round 5 断言 | 修复后验证 | 结果 |
|---|---|---|---|
| R018-C002 | cursor_from/decision_index 直接写 world | staging 到事件含全部字段；静态确认 handler 不直接写 world | ✅ |
| R018-C003 | K 线只从区间临时聚合 | 决策可见 FULL tape 历史（INITIAL→cursor_to）；跨观察零填充 | ✅ |
| R018-C005 | run_multi_seed 丢失族字段 | dataclasses.replace 保留全部字段；clone 校验通过 | ✅ |
| R018-C006 | 接受非法载荷 + 不执行 | 精确类型/必填/枚举/范围；stress events 注入为 EXOGENOUS_STRESS 订单 | ✅ |
| R018-C007 | cursor_to 读 live world | cursor_to/from 从事件 _observed_* 读；重叠观察（latency>interval）全链通过 | ✅ |
| R018-C009 | V1 浅层校验 | 嵌套结构 + 全字段类型/范围；tape dict 转 PublicTrade | ✅ |
| R018-C011 | 未预注册 formal-research | guard_formal_research(preregistered)；报告记录 evidence_class | ✅ |
| R018-C012 | seed_plan 非闭合 | 键/正数/长度/类型闭合；5 个新负例 | ✅ |
| R018-C014 | 内部字段泄漏日志 | _build_record 剥离所有 _ 前缀；日志 0 泄漏 | ✅ |

## 独立复核（反向变异，非自证）

- **C014**：模拟旧 bug（重新注入 `_observed_*`/`_decision_index`）→ 日志测试捕获。
- **C002**：静态确认 handler 不直接写 world 的 decision_index/cursor_from（全走事件 staging）。
- **C007**：真实运行确认 evidence.cursor_to 来自观察快照（decide 时 live cursor 已前进但仍用观察值）。

## 停止条件

- High/Medium 清零（0/0/0）
- 本地 `python tools/verify.py` 全绿（2128 测试）
- CI 最终门禁：待触发

CURRENT-code.md 在 CI 全绿且检视人独立复核后由检视人删除归档（R018-C013 教训）。
