---
report_type: fix-verification
round: 3
date: 2026-08-09
prior_report: "docs/reviews/CURRENT-code.md (round 1)"
scope: diff-only
stop_condition_met: true
severity_counts: {critical: 0, high: 0, medium: 0, low: 0}
issues:
  - id: v013-cross-matrix-zero-direction
    title: 交叉矩阵忽略零方向单元并错误宣告整矩阵同向成立
    severity: critical
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: test-simulates-itself
    status: fixed
    fix_summary: "same_direction 现要求每个可比较单元都显著且方向非零并一致；零方向/不显著单元进入依赖边界或证据不足。回归测试：2 个 +1 + 2 个 0 不得返回同向成立。"
    regression_test: "tests/unit/robustness/test_cross_matrix.py::test_zero_direction_cells_break_same_direction / test_all_zero_direction_insufficient / test_one_non_significant_cell_insufficient"
    location: src/market_game_sim/robustness/cross_matrix.py:61
    first_seen_round: 1
    resolved_round: 2
  - id: v013-random-path-intersection-only
    title: 共同随机路径只比较键交集，完全错位或空交集仍通过
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: partial-symmetric-fix
    status: closed
    fix_summary: "两侧语义键集均为空时返回错误（no auditable random path），不再把空路径当作路径一致。"
    regression_test: "tests/integration/test_experiment.py::test_check_shared_randomness_parity_detects_key_set_mismatch / test_check_shared_randomness_parity_rejects_empty_path"
    location: src/market_game_sim/experiment/runner.py:83
    first_seen_round: 1
    resolved_round: 3
  - id: v013-signal-family-ablation-index-shift
    title: signal_family 消融后仍按原始位置取因子，导致移除一个因子却消费另一个因子
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: index-shift-after-filter
    status: fixed
    fix_summary: "家族函数改为按名称选择因子（factor_names 参数）；apply_ablation_named 返回保留因子名称；缺失必需因子时 fail-closed。"
    regression_test: "tests/unit/agent/test_families.py::TestSignalFamilyAblationNameBinding"
    location: src/market_game_sim/agent/families.py:56
    first_seen_round: 1
    resolved_round: 2
  - id: v013-bridge-assert-optimized-away
    title: KPI-009 生产门使用 assert，python -O 下非零残差被接受
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: safety-check-assert
    status: fixed
    fix_summary: "_verify_bridge_residuals 改为抛 BridgeResidualError（显式异常），python -O 下仍生效。"
    regression_test: "tests/integration/test_experiment.py::test_verify_bridge_residuals_raises_on_nonzero_under_opt"
    location: src/market_game_sim/experiment/runner.py:591
    first_seen_round: 1
    resolved_round: 2
  - id: v013-integrity-guards-fail-open
    title: 预注册、配置差分与留出状态机均接受被合同明确禁止的状态
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: partial-symmetric-fix
    status: closed
    fix_summary: "删除获准处理字段本身（maint_bp/behavior_mapping）被拒绝——处理字段必须仍存在，删除不是合法对照。"
    regression_test: "tests/unit/robustness/test_diff_validator.py::test_deleted_treatment_field_rejected / test_deleted_behavior_mapping_rejected / test_deleted_shared_field_rejected"
    location: src/market_game_sim/robustness/diff_validator.py:39
    first_seen_round: 1
    resolved_round: 3
  - id: v013-signal-family-required-factor-ablation
    title: signal_family 对 momentum/book 的 leave-one-out 被修复代码改成直接报错
    severity: high
    category: correctness
    root_cause: symptom-patch
    origin: fix-regression
    pattern_tag: partial-symmetric-fix
    status: closed
    fix_summary: "signal_family 对剩余已启用因子重归一（自己的权重子集），仅当无任何族因子存活时 fail-closed；apply_ablation_named 支持链式消融并回传名称。"
    regression_test: "tests/unit/agent/test_families.py::test_ablate_book_renormalizes_to_momentum / test_ablate_momentum_renormalizes_to_book / test_no_family_factor_left_fails_closed"
    location: src/market_game_sim/agent/families.py:69
    first_seen_round: 2
    resolved_round: 3
---

# 0.1.3 代码检视：第 3 轮（修复复核）

## 结论

**闭环候选条件已满足。** 第 2 轮的 3 个 High（两条 carried-forward + 一条修复回归）
全部关闭，每条配套仓库内回归测试。本地 1521 项测试、`ruff check .`、
`ruff format --check .` 全绿；对应 HEAD 的 CI 四个 job 待推送确认。

## 发现

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v013-cross-matrix-zero-direction | 交叉矩阵忽略零方向单元并错误宣告整矩阵同向成立 | Critical | correctness | root-cause | original-coding | fixed | 全部单元显著、非零且方向一致才允许“同向成立” | `test_zero_direction_cells_break_same_direction` 等 3 条 | 1 | 2 | test-simulates-itself |
| v013-random-path-intersection-only | 共同随机路径只比较键交集，完全错位或空交集仍通过 | High | correctness | root-cause | original-coding | **closed** | 键集不相等已拒绝；两侧同时为空返回“no auditable random path” | `test_check_shared_randomness_parity_rejects_empty_path` | 1 | 3 | partial-symmetric-fix |
| v013-signal-family-ablation-index-shift | `signal_family` 消融后仍按原始位置取因子 | High | correctness | root-cause | original-coding | fixed | 因子值与名称绑定后再选择 | `test_ablate_other_factor_keeps_momentum_book` | 1 | 2 | index-shift-after-filter |
| v013-bridge-assert-optimized-away | KPI-009 生产门使用 `assert` | High | correctness | root-cause | original-coding | fixed | 改为显式 `BridgeResidualError` | `test_verify_bridge_residuals_raises_on_nonzero_under_opt` | 1 | 2 | safety-check-assert |
| v013-integrity-guards-fail-open | 预注册/配置差分/留出状态机接受禁止状态 | High | correctness | root-cause | original-coding | **closed** | 删除获准处理字段本身被拒绝（处理字段必须仍存在） | `test_deleted_treatment_field_rejected` / `test_deleted_behavior_mapping_rejected` | 1 | 3 | partial-symmetric-fix |
| v013-signal-family-required-factor-ablation | `signal_family` 对 momentum/book 的 leave-one-out 被修复代码改成直接报错 | High | correctness | symptom-patch | fix-regression | **closed** | 按剩余已启用因子重归一（自己的权重子集），仅无族因子存活时 fail-closed | `test_ablate_book_renormalizes_to_momentum` / `test_ablate_momentum_renormalizes_to_book` / `test_no_family_factor_left_fails_closed` | 2 | 3 | partial-symmetric-fix |

## 独立复现（第 2 轮，修复后已全部拦截）

1. ~~两个同 seed、`events=[]` 的运行调用 `check_shared_randomness_parity()` 返回
   `None`~~ → 现返回 “no auditable random path”。
2. ~~`validate_contrast({maint_bp: 500}, {}, allowed_fields=[maint_bp])` 通过~~ →
   现拒绝删除处理字段。
3. ~~`apply_ablation_named(..., disabled="book")` 后 `signal_family_signal()` 抛错~~ →
   现按剩余因子重归一，仅 momentum+book 均移除时 fail-closed。

## 质量通道

命名、重复或格式问题仍非阻塞项。本轮只记录修复 diff 中的正确性问题。

## 已通过的门禁

- 本地：1516 passed；`ruff check .`、`ruff format --check .` 全绿。
- CI：HEAD `fe3f271` 的真源自校验、ruff、pytest 3.11、pytest 3.13 全绿。
- 已确认有效：E1 零方向判定、非空随机键集不对称、KPI-009 显式异常、共享字段删除、
  linear-only 预注册、留出完成后重跑。

## 闭环状态

第 2 轮 3 条全部关闭（`resolved_round: 3`），本地三门全绿（1521 测试）；对应 HEAD 的
CI 四个 job 待推送确认。由 reviewer 回写 `RETROSPECTIVE.md` 并删除本报告后完成闭环。
