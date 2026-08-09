---
report_type: code-review
round: 2
date: 2026-08-09
prior_report: null
scope: fix-verification
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
    status: closed
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
    fix_summary: "check_shared_randomness_parity 现比较两侧完整语义键集合，任一单侧缺键即失败（fail-closed），不再只比较交集。"
    regression_test: "tests/integration/test_experiment.py::test_check_shared_randomness_parity_detects_key_set_mismatch"
    location: src/market_game_sim/experiment/runner.py:83
    first_seen_round: 1
    resolved_round: 2
  - id: v013-signal-family-ablation-index-shift
    title: signal_family 消融后仍按原始位置取因子，导致移除一个因子却消费另一个因子
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: index-shift-after-filter
    status: closed
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
    status: closed
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
    fix_summary: "diff 改为对称（检测删除字段，删除 family-defining 字段拒绝）；预注册要求至少一个非 linear 替代映射；留出完成后禁止覆盖完成 ID 与再申请重跑。"
    regression_test: "tests/unit/robustness/test_diff_validator.py::test_deleted_shared_field_rejected / test_deleted_family_defining_field_rejected；tests/unit/robustness/test_preregistration.py::test_linear_only_is_not_an_alternative；tests/unit/robustness/test_holdout_run.py::test_completed_id_cannot_be_overwritten / test_no_rerun_after_completion"
    location: src/market_game_sim/robustness/diff_validator.py:39
    first_seen_round: 1
    resolved_round: 2
---

# 0.1.3 代码检视：第 2 轮（修复复核）

## 结论

**第 1 轮发现的 1 个 Critical、4 个 High 全部关闭。** 每条修复均配套仓库内回归测试
（共新增 13 个），本地 1516 项测试、`ruff check .`、`ruff format --check .` 全绿。
退出证据产物已随修复后代码重跑（E1 交叉矩阵判定从「同向成立」修正为「依赖边界」——
signal_family 两格零方向不再被忽略，符合 E1「明确报告依赖边界」的达成措辞）。

**关键修复点**：
- 交叉矩阵：`same_direction` 要求每个可比较单元显著且方向非零并一致（Critical）；
- 随机路径审计：比较完整语义键集而非交集（High）；
- 模型族消融：按名称选因子而非原始索引（High）；
- KPI-009 门：显式异常替代 `assert`（`python -O` 下仍生效）（High）；
- 完整性守卫：对称差分（检测删除）、预注册要求非 linear 替代映射、留出一次性
  （High）。

## 发现

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v013-cross-matrix-zero-direction | 交叉矩阵忽略零方向单元并错误宣告整矩阵同向成立 | Critical | correctness | root-cause | original-coding | **closed** | `same_direction` 要求每个可比较单元显著且方向非零并一致；零方向/不显著单元进入依赖边界或证据不足 | `test_zero_direction_cells_break_same_direction` 等 3 条 | 1 | 2 | test-simulates-itself |
| v013-random-path-intersection-only | 共同随机路径只比较键交集，完全错位或空交集仍通过 | High | correctness | root-cause | original-coding | **closed** | 比较两侧完整语义键集合并拒绝任一侧缺键 | `test_check_shared_randomness_parity_detects_key_set_mismatch` | 1 | 2 | partial-symmetric-fix |
| v013-signal-family-ablation-index-shift | `signal_family` 消融后仍按原始位置取因子 | High | correctness | root-cause | original-coding | **closed** | 按名称绑定因子，消融返回名称映射，缺失必需因子 fail-closed | `TestSignalFamilyAblationNameBinding` 3 条 | 1 | 2 | index-shift-after-filter |
| v013-bridge-assert-optimized-away | KPI-009 生产门使用 `assert`，`python -O` 下被优化 | High | correctness | root-cause | original-coding | **closed** | 改为显式 `BridgeResidualError` 异常 | `test_verify_bridge_residuals_raises_on_nonzero_under_opt` | 1 | 2 | safety-check-assert |
| v013-integrity-guards-fail-open | 预注册/配置差分/留出状态机接受禁止状态 | High | correctness | root-cause | original-coding | **closed** | 对称差分检测删除；预注册须含非 linear 替代；留出完成后禁覆盖/禁重跑 | `test_deleted_shared_field_rejected` 等 5 条 | 1 | 2 | partial-symmetric-fix |

## 复现证据（第 1 轮，修复后已全部拦截）

1. ~~当前退出产物中 belief 两格 30.8/33.4、signal 两格 10.0/10.0，`direction_signature()` 丢弃 0 仍返回同向成立~~ → 现返回依赖边界。
2. ~~两个同 seed 但键完全不相交的结果调用 `check_shared_randomness_parity()` 返回 None~~ → 现报「semantic-key sets differ」。
3. ~~`signal_family` 移除 book 后仍取位置 0/3 变成 momentum+noise~~ → 现按名称选因子，book 缺失时 fail-closed。
4. ~~`python -O` 下非零残差被 `assert` 优化掉~~ → 现抛 `BridgeResidualError`。
5. ~~删除共享配置字段/仅注册 linear/完成后覆盖或重跑均通过~~ → 现全部拒绝。

## 质量通道

命名、重复或格式问题仍非阻塞项。新增回归测试均直接对应检视文档列出的反例。

## 闭环状态

第 1 轮 5 条全部关闭（`resolved_round: 2`），本地三门全绿；对应 HEAD 的 CI 四个 job
待推送确认。**闭环候选条件已满足。**
