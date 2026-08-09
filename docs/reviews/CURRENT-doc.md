---
report_type: doc-review
round: 5
date: 2026-08-09
prior_report: "CURRENT-doc.md round 4（同文件覆盖演进）"
scope: diff-only
stop_condition_met: false
severity_counts: {critical: 0, high: 0, medium: 0, low: 0}
issues:
  - id: model-family-config-diff-unvalidated
    severity: high
    category: correctness
    root_cause: root-cause
    status: fixed
    regression_test: "T403 文档合同：合法差分通过、额外字段拒绝、仅改 ID 拒绝"
    first_seen_round: 4
  - id: e1-behavior-mapping-family-cross-matrix
    severity: high
    category: correctness
    root_cause: root-cause
    status: fixed
    regression_test: "N/A(spec/tasks文档缺口,待T105/T207落地后配对测试)"
    first_seen_round: 3
  - id: lifecycle-metadata-stale
    severity: medium
    category: maintainability
    root_cause: root-cause
    status: fixed
    regression_test: "N/A(文档状态字段,非代码)"
    first_seen_round: 3
  - id: 0.1.2-gate-not-satisfied
    severity: critical
    category: correctness
    root_cause: root-cause
    status: fixed
    regression_test: "docs/experiments/0.1.2-exit-evidence-index.json"
    first_seen_round: 1
  - id: holdout-failure-blocks-exit
    severity: high
    category: correctness
    root_cause: root-cause
    status: fixed
    first_seen_round: 1
  - id: behaviormapping-dual-output
    severity: high
    category: maintainability
    root_cause: root-cause
    status: fixed
    first_seen_round: 1
  - id: cell-id-seed-pairing-collision
    severity: high
    category: maintainability
    root_cause: root-cause
    status: fixed
    first_seen_round: 1
  - id: kpi-008-no-owner
    severity: high
    category: test-coverage
    root_cause: root-cause
    status: fixed
    first_seen_round: 1
  - id: paired-bootstrap-loses-pairing
    severity: high
    category: correctness
    root_cause: root-cause
    status: fixed
    first_seen_round: 2
  - id: cell-id-dual-identity
    severity: medium
    category: maintainability
    root_cause: root-cause
    status: fixed
    first_seen_round: 2
  - id: min-pair-sample-unfrozen
    severity: medium
    category: correctness
    root_cause: root-cause
    status: fixed
    first_seen_round: 2
  - id: model-family-undefined
    severity: high
    category: maintainability
    root_cause: root-cause
    status: fixed
    first_seen_round: 2
  - id: four-region-conflicts-three-zone
    severity: high
    category: maintainability
    root_cause: root-cause
    status: fixed
    first_seen_round: 2
---

# 0.1.3-robustness 规格/任务清单检视

**范围**：仅复核 round 3 后的 `spec.md`、`tasks.md`、`README.md` diff。
**性质**：规格修复验证，判断是否可以从 T001 正式开工。

## 0. 结论先行

正确性与质量通道的 Critical/High/Medium 已清零。T403 已把模型族视为 T006 预注册的
复合处理，冻结允许变化字段与共享字段逐字节一致规则，并加入合法差分通过、额外字段漂移
拒绝、仅改 ID 拒绝三类 TDD 合同。**0.1.3 需求设计文档已达到本地 Go，可从 T001 开工。**

本地门禁已通过：`pytest` 1135 项、`ruff check .`、`ruff format --check .`、任务 ID
唯一性与 `git diff --check` 全绿。当前改动尚未提交/推送，因此没有覆盖本 diff 的远端
CI run；按项目规则，`stop_condition_met` 在对应提交的 CI 四个 job 全绿前仍保持 false。

## 1. 本轮修复验证

| ID | 严重度 | 分类 | 根因/症状 | 状态 | 回归测试 | 首次出现轮次 |
|---|---|---|---|---|---|---|
| model-family-config-diff-unvalidated | High | correctness | root-cause | fixed | T403 三类正反 TDD 文档合同 | 4 |

T403 现明确：跨模型族比较的实际差分必须非空且只能落在 T006 的 family-defining 字段
集合内，共享字段逐字节一致；额外字段和仅修改 ID/版本但无结构变化均 fail-closed。

## 2. 修复验证

| ID | 严重度 | 分类 | 根因/症状 | 状态 | 回归测试/证据 | 首次出现轮次 |
|---|---|---|---|---|---|---|
| e1-behavior-mapping-family-cross-matrix | High | correctness | root-cause | fixed | T105/T207/T604/E1 文档闭合 | 3 |
| lifecycle-metadata-stale | Medium | maintainability | root-cause | fixed | spec/tasks/README 状态一致 | 3 |

## 3. 既往关闭摘要

round 1—2 的 10 项、round 3 的 2 项和 round 4 的 1 项发现全部保持关闭：累计
1 Critical、9 High、3 Medium。所有修复均为文档合同变更；对应代码正反回归测试已写入
各 TDD 任务，随实现进入仓库测试套件。
