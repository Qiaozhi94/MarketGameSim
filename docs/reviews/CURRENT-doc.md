---
report_type: doc-review
round: 3
date: 2026-08-09
prior_report: "无独立文件——本文件此前以 code-review-report.md 形式覆盖式演进,
  历经 2026-08-08 首次审查 → 2026-08-09 第二轮 → 2026-08-09 本轮(最终复核),
  历史见 git log --follow -p 对应提交"
scope: full-scan
stop_condition_met: false
severity_counts: {critical: 0, high: 1, medium: 1, low: 0}
issues:
  - id: e1-behavior-mapping-family-cross-matrix
    severity: high
    category: correctness
    root_cause: root-cause
    status: open
    regression_test: "N/A(spec/tasks文档缺口,待T105/T207落地后配对测试)"
    first_seen_round: 3
  - id: lifecycle-metadata-stale
    severity: medium
    category: maintainability
    root_cause: root-cause
    status: open
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

**范围**: `specs/v0.1-belief-testing-laboratory/0.1.3-robustness/spec.md`、
`tasks.md`,及关联 PRD、方法论、0.1.2 退出证据、现有实验协议与统计接口
**性质**: 规格评审,判断是否可以从 T001 正式开工实现

## 0. 结论先行

`stop_condition_met: false`——还有 1 个 High + 1 个 Medium 未关闭,交叉矩阵缺口
关闭前不建议正式进入实现。第1、2轮共 8 个 High/Medium/Critical 已全部关闭
(见下表 `status: fixed`)。

> **待确认**:当前工作树对 `spec.md`/`tasks.md`/`README.md` 有未提交改动
> (`git status` 显示 83 行改动在 tasks.md),可能已经在处理下面第一条 High——
> 下一轮复核前需要先看这份 diff 是否已经覆盖 E1 交叉矩阵要求。

## 1. 未关闭发现

### 🟠 High — E1 没有要求行为映射 × 模型族交叉,两个稳健性维度仍可能相互混淆
`0.1.3-robustness/spec.md`:31; `tasks.md`:61-62,85-87,184-186

**Problem**: E1 要求"至少两种行为映射、至少两个预注册模型族",但 T105 只建立
行为映射对照,T207 只要求每个模型族独立参数扫描。没有任务要求每个模型族都运行
每种行为映射,也没有要求报告 mapping × family 交互。当前清单可以只用"模型族A的
linear/threshold对照"+"模型族A/B的linear对照"完成,若模型族B的threshold发生
方向反转仍会被漏掉,却可能被签收为"同时不依赖映射和模型族"。

**Suggested Fix**: T105 改为建立 `model_family_id × behavior_mapping_id` 交叉
对照矩阵,每个模型族运行每种映射,预先声明主效应/交互/方向反转的报告规则;T207
对每个交叉单元独立执行,不具可比语义的单元必须预注册原因并将 E1 降级为条件性
结论。

### 🟡 Medium — 0.1.2 已完成,但 0.1.3 生命周期元数据仍显示"待 0.1.2 退出"
`0.1.3-robustness/spec.md`:4-6; `tasks.md`:4; `README.md`:30

**Problem**: 0.1.2 的 E1—E7 + 附加门槛已在机器证据中全部 `met`,但 spec/tasks/
README 仍写 `Ready after 0.1.2` / "待 0.1.2 退出"。实现者或自动化读到这些字段
会得到与机器退出证据相反的状态。

**Suggested Fix**: 状态改为 `Ready(0.1.2 退出证据已达成;实现从 T001 自动复核
准入证据开始)`,同步 README;T001 仍保留 fail-closed 复核,不等于跳过它。

## 2. 已关闭发现(压缩记录,细节见 git 历史)

第1轮(2026-08-08)关闭 5 项:0.1.2 启动门未满足(Critical)、留出验证失败阻断
退出、`BehaviorMapping` 双重输出破坏单变量对照、`cell_id+seed` 无法同时标识
参数单元与配对、KPI-008 无验证任务 owner。

第2轮(2026-08-09 首次)关闭 5 项:配对 bootstrap 丢失配对结构、`cell_id` 双重
身份冲突、最低有效配对样本量未冻结、模型族定义缺失、四区与既有三区协议冲突。

## Positive Observations

前两轮十项修复均已形成可直接实现的合同;本轮文档链接检查、`git diff --check`、
`ruff check .`、`ruff format --check .` 均通过,相关合同/协议/统计测试 58 项通过。
