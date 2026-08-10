---
report_type: fix-verification
round: 5
date: 2026-08-10
prior_report: 445c281
scope: diff-only
stop_condition_met: true
severity_counts: {critical: 0, high: 0, medium: 0, low: 0}
issues:
  - id: STRUCT-C001
    title: 链接与文档所有权门禁未接入生产校验入口
    severity: high
    category: correctness
    root_cause: root-cause
    origin: process-gap
    pattern_tag: test-simulates-itself
    status: fixed
    fix_summary: 版本 README 扫描改为遍历 discover_versions（不再硬编码 0.1）；新增里程碑 design.md 重定义全局不变量（C1/C2）的跨层级真相源门禁
    regression_test: tests/unit/test_spec_lifecycle.py::test_ownership_drift_detected_for_future_version / test_milestone_design_redefines_invariant_fails / test_milestone_design_without_invariant_passes / test_ownership_status_drift_fails / test_ownership_index_*
    location: tools/spec_validation.py:489
    first_seen_round: 1
    resolved_round: 5
  - id: STRUCT-C002
    title: 版本级生命周期与 release 收口规则未执行
    severity: high
    category: correctness
    root_cause: root-cause
    origin: process-gap
    pattern_tag: marked-done-not-implemented
    status: fixed
    fix_summary: release 的 closed_at 改为结构化 frontmatter 解析，正文提及 closed_at 不再绕过；校验 version 一致
    regression_test: tests/unit/test_spec_lifecycle.py::test_version_done_prose_closed_at_bypass_fails / test_version_done_*
    location: tools/spec_validation.py:475
    first_seen_round: 1
    resolved_round: 3
  - id: prereq-cycle-false-positive
    title: prerequisites 环检测对菱形依赖误报
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: original-coding
    status: fixed
    fix_summary: 改用三色 DFS，只判当前路径回边
    regression_test: tests/unit/test_spec_lifecycle.py::test_prereq_diamond_not_flagged_as_cycle
    location: tools/spec_validation.py:249
    first_seen_round: 1
    resolved_round: 1
  - id: tasks-status-uniqueness-skipped
    title: check_status_uniqueness 仅在 design.md 存在时运行
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: original-coding
    status: fixed
    fix_summary: 独立检查 design 与 tasks，不再以 design 存在为前置
    regression_test: tests/unit/test_spec_lifecycle.py::test_tasks_status_uniqueness_without_design
    location: tools/spec_validation.py:568
    first_seen_round: 1
    resolved_round: 1
  - id: dup-id-info-lost
    title: collect_all_milestones 重复 ID 覆盖丢失首个信息
    severity: low
    category: quality
    root_cause: root-cause
    origin: original-coding
    status: fixed
    fix_summary: 保留首个条目并把重复目录追加到 __dups__ 列表
    regression_test: tests/unit/test_spec_lifecycle.py::test_dup_id_preserves_dups
    location: tools/spec_validation.py:206
    first_seen_round: 1
    resolved_round: 1
  - id: section-substring-match
    title: _check_sections 用子串匹配，可能误匹配
    severity: low
    category: quality
    root_cause: root-cause
    origin: original-coding
    status: fixed
    fix_summary: 改为精确匹配顶层标题
    regression_test: tests/unit/test_spec_lifecycle.py (现有 test_gate1_* 覆盖精确匹配)
    location: tools/spec_validation.py:382
    first_seen_round: 1
    resolved_round: 1
  - id: STRUCT-C003
    title: round-1 修复遗留死代码（validate_ids_unique 的 seen dict 在 __dups__ 方案下永不触发）
    severity: low
    category: quality
    root_cause: symptom-patch
    origin: fix-regression
    status: fixed
    fix_summary: 移除永不触发的 seen 逻辑，只靠 __dups__ 报告重复
    regression_test: tests/unit/test_spec_lifecycle.py::test_dup_id_preserves_dups（保持覆盖）
    location: tools/spec_validation.py:217
    first_seen_round: 2
    resolved_round: 2
  - id: STRUCT-C004
    title: 重复 ID 回归测试把临时 fixture 写入固定仓库路径
    severity: medium
    category: test-coverage
    root_cause: root-cause
    origin: fix-regression
    pattern_tag: test-writes-repo-state
    status: fixed
    fix_summary: 改用 pytest tmp_path fixture，测试不再写入仓库固定路径
    regression_test: tests/unit/test_spec_lifecycle.py::test_dup_id_preserves_dups
    location: tests/unit/test_spec_lifecycle.py:494
    first_seen_round: 3
    resolved_round: 3
---

# 目录结构改造代码检视

结论：**封顶 diff-only 复核通过。** STRUCT-C001 的两个剩余缺口已补：版本 README 扫描
改为遍历 `discover_versions`（不再硬编码 0.1），并新增里程碑 design.md 重定义全局
不变量的跨层级真相源门禁。本地 1567 测试全绿，`validate_spec_lifecycle` 通过，ruff
0.16 下 check/format 全绿。High 清零。

## 有限检查清单

- 生产入口是否实际调用已声明的链接与所有权规则（已接线，含跨层级状态漂移与真相源）；
- 版本根和 milestone 是否都进入生命周期校验（已接线）；
- 版本 `done` 是否强制关联 release 文件与结构化 `closed_at`（已接线）；
- 版本 README 扫描是否遍历全部版本而非硬编码（已修复）；
- 里程碑 design.md 是否被阻止重新定义全局不变量（已接线）。

## 发现

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| STRUCT-C001 | 链接与文档所有权门禁未接入生产校验入口 | High | 正确性 | 根因 | 流程缺陷 | 已修复 | 版本 README 扫描遍历全部版本；里程碑 design 重定义全局不变量门禁 | test_ownership_drift_detected_for_future_version / test_milestone_design_redefines_invariant_fails | 1 | 5 | test-simulates-itself |
| STRUCT-C002 | 版本级生命周期与 release 收口规则未执行 | High | 正确性 | 根因 | 流程缺陷 | 已修复 | closed_at 结构化解析，正文子串不绕过 | test_version_done_prose_closed_at_bypass_fails | 1 | 3 | marked-done-not-implemented |
| prereq-cycle-false-positive | 环检测对菱形依赖误报 | 中 | 正确性 | 根因 | 原始编码 | 已修复 | 三色 DFS 只判当前路径回边 | test_prereq_diamond_not_flagged_as_cycle | 1 | 1 | — |
| tasks-status-uniqueness-skipped | gate-0 里程碑 tasks 状态不被检查 | 中 | 正确性 | 根因 | 原始编码 | 已修复 | 独立检查 design 与 tasks | test_tasks_status_uniqueness_without_design | 1 | 1 | — |
| dup-id-info-lost | 重复 ID 覆盖丢失首个信息 | 低 | 质量 | 根因 | 原始编码 | 已修复 | 保留首个条目，重复追加 __dups__ | test_dup_id_preserves_dups | 1 | 1 | — |
| section-substring-match | 章节子串匹配误匹配 | 低 | 质量 | 根因 | 原始编码 | 已修复 | 精确匹配顶层标题 | test_gate1_* | 1 | 1 | — |
| STRUCT-C003 | round-1 修复遗留死代码（seen dict 永不触发） | 低 | 质量 | 症状 | 修改引入 | 已修复 | 移除永不触发的 seen 逻辑 | test_dup_id_preserves_dups | 2 | 2 | — |
| STRUCT-C004 | 重复 ID 回归测试把临时 fixture 写入固定仓库路径 | Medium | 测试覆盖 | 根因 | 修改引入 | 已修复 | 改用 pytest tmp_path fixture | test_dup_id_preserves_dups | 3 | 3 | test-writes-repo-state |

## 证据与停止条件

- 版本 README 扫描遍历 `discover_versions`，新版本漂移被 `test_ownership_drift_detected_for_future_version` 锁定；
- 里程碑 design.md 重定义 C1/C2 被 `check_global_invariant_ownership` 拦截（正反用例）；
- `validate_versions()` 以结构化 frontmatter 解析 `closed_at`；
- 本地 1567 测试全绿，`validate_spec_lifecycle` 通过，ruff 0.16 下 check/format 全绿。
