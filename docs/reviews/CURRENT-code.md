---
report_type: fix-verification
round: 5
date: 2026-08-27
prior_report: "fd84c26:docs/reviews/CURRENT-code.md (Round 4, subsequently deleted by 7162f17)"
scope: diff-only
stop_condition_met: false
severity_counts: {critical: 0, high: 5, medium: 4, low: 0}
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
    location: src/market_game_sim/kernel/runner.py:315
    first_seen_round: 1
    resolved_round: 2
  - id: R018-C002
    title: 失败事务仍会提前消耗决策序号和游标下界状态
    severity: high
    category: correctness
    root_cause: symptom-patch
    origin: original-coding
    pattern_tag: cursor-commit-before-consume
    status: carried-forward
    fix_summary: "仅 agent_cursors/agent_ewma 改为事务后提交；agent_cursor_from/agent_decision_index 仍在 handler 内直接写 world"
    regression_test: "tests/integration/test_tape_cursor.py::test_failure_after_staging_does_not_leak_into_next_transaction（断言不完整）"
    location: src/market_game_sim/agent/handler.py:750
    first_seen_round: 1
    resolved_round:
  - id: R018-C003
    title: 观察快照与已完成全局 K 线仍未正确接入 InformationSetV1
    severity: high
    category: correctness
    root_cause: symptom-patch
    origin: original-coding
    pattern_tag: test-simulates-itself
    status: carried-forward
    fix_summary: "仅把本观察区间成交附到 decide；book/account 仍在 decide 时重建，K 线也只从区间成交临时聚合"
    regression_test: "tests/unit/agent/test_tape_ewma.py::test_completed_bars_with_zero_fill_pads_empty_bars（未覆盖同 bar 与跨空区间）"
    location: src/market_game_sim/agent/handler.py:429
    first_seen_round: 1
    resolved_round:
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
    title: 运行族字段在多种子入口丢失，闭合配置门禁可被绕过
    severity: high
    category: correctness
    root_cause: symptom-patch
    origin: original-coding
    pattern_tag: gate-not-wired-to-entrypoint
    status: carried-forward
    fix_summary: "字段加入 ExperimentConfig，但 run_multi_seed 重建配置时未复制；dataclass 未启用 slots，动态未知字段也被映射器忽略"
    regression_test: "tests/integration/test_run_family_entrypoint.py::test_unknown_field_rejected_by_constructor（只覆盖构造器关键字）"
    location: src/market_game_sim/experiment/runner.py:496
    first_seen_round: 1
    resolved_round:
  - id: R018-C006
    title: StressProtocolV1 仍接受非法载荷且运行器完全不执行协议
    severity: high
    category: correctness
    root_cause: symptom-patch
    origin: original-coding
    pattern_tag: validator-accepts-forbidden-variants
    status: carried-forward
    fix_summary: "仅校验版本值、事件名和未知参数键；未校验精确类型、必填参数、枚举/数值范围，也未调度 stress_protocol.events"
    regression_test: "tests/unit/experiment/test_stress_protocol.py::test_protocol_rejects_wrong_schema_version（负例覆盖不足）"
    location: src/market_game_sim/experiment/stress_protocol.py:70
    first_seen_round: 1
    resolved_round:
  - id: R018-C007
    title: 重叠观察时决策证据的 cursor_to 读取了未来游标
    severity: high
    category: correctness
    root_cause: symptom-patch
    origin: original-coding
    pattern_tag: partial-chain-verifier
    status: carried-forward
    fix_summary: "cursor_from 改读观察快照，但 cursor_to 仍读 decide 执行时的 live world；事件中的 _observed_cursor_to 未使用"
    regression_test: "tests/integration/test_decision_chain_verifier.py::test_multi_interval_goal_chain_passes_and_all_trade_hops_resolve（latency 小于观察周期）"
    location: src/market_game_sim/agent/handler.py:572
    first_seen_round: 1
    resolved_round:
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
    root_cause: symptom-patch
    origin: original-coding
    pattern_tag: shallow-schema-validation
    status: carried-forward
    fix_summary: "版本与偏好边界已校验；游标、嵌套条目、EWMA 类型/范围仍可传入任意错误值"
    regression_test: "tests/unit/schema/test_event_schema.py::test_information_set_and_internal_state_reject_unknown_versions（只覆盖版本）"
    location: src/market_game_sim/agent/goal.py:116
    first_seen_round: 1
    resolved_round:
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
    root_cause: symptom-patch
    origin: process-gap
    pattern_tag: gate-not-wired-to-entrypoint
    status: carried-forward
    fix_summary: "run_paired 只调用 guard_evidence_class；未调用 guard_formal_research，返回报告也不记录 evidence_class"
    regression_test: "tests/integration/test_evidence_guard_entrypoint.py（缺少未预注册 formal-research 负例）"
    location: src/market_game_sim/experiment/runner.py:185
    first_seen_round: 1
    resolved_round:
  - id: R018-C012
    title: manifest 的 seed_plan 仍非闭合有效结构
    severity: medium
    category: correctness
    root_cause: symptom-patch
    origin: spec-drift
    pattern_tag: manifest-contract-drift
    status: carried-forward
    fix_summary: "已要求 n_seeds 存在且为 int，但仍接受额外字段、n_seeds<=0、缺失/不匹配 seeds"
    regression_test: "tests/integration/test_showcase_bundle.py::test_manifest_records_closed_seed_plan（其 cells 字段反而超出 schema）"
    location: src/market_game_sim/showcase/manifest.py:150
    first_seen_round: 1
    resolved_round:
  - id: R018-C013
    title: Round 4 再次由修复方自证关闭并删除检视报告
    severity: medium
    category: test-coverage
    root_cause: root-cause
    origin: process-gap
    pattern_tag: self-approved-closure
    status: fixed
    fix_summary: "Round 5 由独立检视重新取回报告、逐项复现并恢复 CURRENT-code.md"
    regression_test: "本 Round 5 检视记录与最小复现证据"
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
    status: open
    fix_summary: ""
    regression_test: "待补：正式日志不得包含 _decision_index/_observed_* 等内部字段"
    location: src/market_game_sim/kernel/runner.py:354
    first_seen_round: 5
    resolved_round:
---

# 0.1.5 T203—T212 修复复核（Round 5）

**结论：不能闭环，当前 5 High + 4 Medium。** 修复相关的 105 条现有测试全部通过，HEAD
及修复提交 CI 均为绿色；但独立最小复现证明多项测试只锁住了局部补丁，没有覆盖真实入口、
失败回滚边界或重叠观察时序。

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R018-C001 | 后续观察始终引用初始市场事件，公开成交游标不会前进 | High | 正确性 | 根因 | 原始编码 | 已修复 | kernel 记录最后提交的市场数据边界 | `test_post_trade_observation_consumes_latest_market_interval` | 1 | 2 | `hardcoded-causal-anchor` |
| R018-C002 | 失败事务仍会提前消耗决策序号和游标下界状态 | High | 正确性 | 症状补丁 | 原始编码 | 延续 | 将 cursor_from、decision_index 与 cursor/EWMA 一并事务化提交 | 补充失败后两字段不变、重试 intent ID 不跳号 | 1 | — | `cursor-commit-before-consume` |
| R018-C003 | 观察快照与已完成全局 K 线仍未正确接入 | High | 正确性 | 症状补丁 | 原始编码 | 延续 | 观察时冻结完整 InformationSet；维护持久全局已完成 bars，不从单个区间临时推导 | 补同 bar 未闭合、连续空 bar、观察后 book/account 改变用例 | 1 | — | `test-simulates-itself` |
| R018-C004 | 空头同向加仓绕过裁剪 | High | 正确性 | 根因 | 原始编码 | 已修复 | 多空对称裁剪 | `test_same_side_add_is_clipped_symmetrically_for_long_and_short` | 1 | 2 | `partial-symmetric-fix` |
| R018-C005 | 运行族字段在多种子入口丢失，闭合门禁可绕过 | High | 正确性 | 症状补丁 | 原始编码 | 延续 | 用 `dataclasses.replace`/统一复制保留全部字段；配置启用 slots 或按 dataclass fields 检查未知属性 | 补 run_paired 后每个 run 仍保留族字段、动态未知字段被拒绝 | 1 | — | `gate-not-wired-to-entrypoint` |
| R018-C006 | StressProtocolV1 接受非法载荷且运行器不执行协议 | High | 正确性 | 症状补丁 | 原始编码 | 延续 | 精确类型/必填/枚举/范围校验，并把有限事件序列接入统一调度及 EXOGENOUS_STRESS 证据 | 补非法 payload 负例与真实四 cell 执行路径 | 1 | — | `validator-accepts-forbidden-variants` |
| R018-C007 | 重叠观察时 cursor_to 读取未来游标 | High | 正确性 | 症状补丁 | 原始编码 | 延续 | 使用事件的 `_observed_cursor_to`，不可读取 live cursor | 补 `latency_ns > observe_interval_ns` 全链用例 | 1 | — | `partial-chain-verifier` |
| R018-C008 | reserved 重复且遗漏候选手续费 | Medium | 正确性 | 根因 | 原始编码 | 已修复 | 委托 ledger 并计入候选费用 | `test_candidate_new_open_fee_is_reserved` | 1 | 2 | `duplicated-admission-formula` |
| R018-C009 | V1 信息集/内部状态仍是浅层校验 | Medium | 正确性 | 症状补丁 | 原始编码 | 延续 | 校验全部标量类型/范围和嵌套对象类型 | 补游标、PublicTrade/CompletedBar、EWMA 负例 | 1 | — | `shallow-schema-validation` |
| R018-C010 | EWMA 依赖观察批次划分 | Medium | 正确性 | 根因 | 原始编码 | 已修复 | 每 fill 取整 | `test_ewma_is_invariant_to_observation_batch_partition` | 1 | 2 | `batch-partition-dependent-state` |
| R018-C011 | 未预注册 formal-research 可生成结论 | Medium | 正确性 | 症状补丁 | 流程缺口 | 延续 | report 入口接 `guard_formal_research`，要求可追溯 preregistration，并写入 evidence_class | 补未预注册拒绝/已预注册接受正反例 | 1 | — | `gate-not-wired-to-entrypoint` |
| R018-C012 | seed_plan 仍非闭合有效结构 | Medium | 正确性 | 症状补丁 | 契约漂移 | 延续 | 按 schema 精确校验键、正数种子数、种子数组类型和数量一致性 | 补额外键、零/负数、数量不匹配负例 | 1 | — | `manifest-contract-drift` |
| R018-C013 | Round 4 再次由修复方自证关闭 | Medium | 测试覆盖 | 根因 | 流程缺口 | 已修复 | Round 5 独立复核并恢复 CURRENT 报告 | 本报告及复现证据 | 3 | 5 | `self-approved-closure` |
| R018-C014 | 内部快照字段泄漏到正式日志 | Medium | 正确性 | 根因 | 修复引入 | 新增 | `_build_record` 统一剥离事务内部字段，或改用不参与 record 的 side channel | 补 AGENT_DECIDE 闭合字段断言 | 5 | — | `transaction-internal-field-leaked-to-log` |

## 独立复现证据

1. **事务回滚**：observe staging 后抛错，`agent_cursors` 保持 `{}`，但
   `agent_decision_index={'agent-0': 1}`、`agent_cursor_from={'agent-0':'e1_0'}` 已泄漏。
2. **K 线边界**：唯一成交在 `t=0`，观察发生于 `t=30s` 时，60 秒 helper 返回 1 根
   “已完成”bar；空成交的后续区间返回 `[]`，无法继承上一根 close 补零。
3. **重叠观察**：`observe_interval=100ms, latency=250ms` 的真实运行被链验证器拒绝：
   `AGENT_DECIDE e22_0 cursor_to 'e14_1' != observation e2_0 cursor_to 'e1_0'`。
4. **运行族/报告**：`stress_protocol='not-a-protocol'` 的 STRESS run 返回 COMPLETED，压力
   事件为 0；未预注册 SPONTANEOUS + `formal-research` 直接生成 conditional conclusion。
5. **闭合契约**：非法 stress 版本/缺参/坏枚举与负数量、畸形 seed_plan、错误嵌套 V1
   对象均被接受；正式 AGENT_DECIDE 含 4 个 `_...` 内部字段。

## 验证与停止条件

- 修复相关测试：`105 passed in 2.40s`；这些测试没有覆盖上述反例。
- GitHub Actions：`3de200c`、`fd84c26`、`7162f17` 均绿色，仅说明现有门禁通过。
- 阻塞项未清零，`stop_condition_met=false`；本轮不触发新的收敛候选 CI，也不得删除本文件。
