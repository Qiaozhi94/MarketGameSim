---
report_type: code-review
round: 1
date: 2026-08-10
prior_report: null
scope: full-scan
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
    fix_summary: validate_spec_lifecycle 现在调用 check_docs_links 与 check_ownership_index，遍历维护中文档校验链接/仓库边界与所有权索引
    regression_test: tests/unit/test_spec_lifecycle.py::test_entry_level_dead_link_rejected / test_entry_level_dir_as_file_rejected / test_ownership_index_missing_fails / test_ownership_index_broken_link_fails
    location: tools/spec_validation.py:270
    first_seen_round: 1
    resolved_round: 1
  - id: STRUCT-C002
    title: 版本级生命周期与 release 收口规则未执行
    severity: high
    category: correctness
    root_cause: root-cause
    origin: process-gap
    pattern_tag: marked-done-not-implemented
    status: fixed
    fix_summary: 新增 validate_versions：校验 version-spec 元数据与状态转换；版本 done 强制关联 release/closed_at/全部里程碑 done
    regression_test: tests/unit/test_spec_lifecycle.py::test_version_done_without_release_fails / test_version_done_release_without_closed_at_fails / test_version_done_with_pending_milestone_fails / test_version_done_valid_closes_clean
    location: tools/spec_validation.py:453
    first_seen_round: 1
    resolved_round: 1
  - id: prereq-cycle-false-positive
    title: prerequisites 环检测对菱形依赖误报
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: original-coding
    status: fixed
    fix_summary: 改用三色 DFS，只判当前路径回边
    regression_test: tests/unit/test_spec_lifecycle.py::test_prereq_diamond_not_flagged_as_cycle
    location: tools/spec_validation.py:251
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
---

# 目录结构改造代码检视

结论：**未通过，两个 High 阻塞结构改造闭环。** 产品测试和现有 CI 全绿，但统一校验
入口没有实际执行方案承诺的全部结构门禁，因此不能用当前绿灯证明链接、文档所有权和
版本收口规则成立。

## 有限检查清单

- 生产入口是否实际调用已声明的链接与所有权规则；
- 版本根和 milestone 是否都进入生命周期校验；
- 版本 `done` 是否强制关联 release 文件与 `closed_at`；
- 测试是否覆盖函数接线，而非只覆盖孤立纯函数；
- prerequisites 环检测是否只判真实环（不误报菱形依赖）；
- design/tasks 状态唯一性是否对 gate-0（无 design）里程碑也生效。

## 发现

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| STRUCT-C001 | 链接与文档所有权门禁未接入生产校验入口 | High | 正确性 | 根因 | 流程缺陷 | 已修复 | validate_spec_lifecycle 调用 check_docs_links 与 check_ownership_index | test_entry_level_dead_link_rejected / test_ownership_index_* | 1 | 1 | test-simulates-itself |
| STRUCT-C002 | 版本级生命周期与 release 收口规则未执行 | High | 正确性 | 根因 | 流程缺陷 | 已修复 | 新增 validate_versions：版本 done 强制关联 release/closed_at/全部里程碑 done | test_version_done_* | 1 | 1 | marked-done-not-implemented |
| prereq-cycle-false-positive | 环检测对菱形依赖误报 | 中 | 正确性 | 根因 | 原始编码 | 已修复 | 三色 DFS 只判当前路径回边 | test_prereq_diamond_not_flagged_as_cycle | 1 | 1 | — |
| tasks-status-uniqueness-skipped | gate-0 里程碑 tasks 状态不被检查 | 中 | 正确性 | 根因 | 原始编码 | 已修复 | 独立检查 design 与 tasks | test_tasks_status_uniqueness_without_design | 1 | 1 | — |
| dup-id-info-lost | 重复 ID 覆盖丢失首个信息 | 低 | 质量 | 根因 | 原始编码 | 已修复 | 保留首个条目，重复追加 __dups__ | test_dup_id_preserves_dups | 1 | 1 | — |
| section-substring-match | 章节子串匹配误匹配 | 低 | 质量 | 根因 | 原始编码 | 已修复 | 精确匹配顶层标题 | test_gate1_* | 1 | 1 | — |

## 证据与停止条件

- 修复后 `validate_spec_lifecycle()` 遍历维护中文档执行链接/仓库边界/所有权索引校验，且只报告实际执行的门禁；
- 新增 `validate_versions()` 校验版本根元数据与状态转换（done ↔ release/closed_at/里程碑完成）；
- 全部 6 条发现已修复并有对应回归测试；本地 1562 测试全绿，`validate_spec_lifecycle` 通过。
- 第二轮（diff-only）复核本修复 diff 与新增测试后关闭。
