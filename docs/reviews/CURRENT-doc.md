---
report_type: doc-review
round: 1
date: 2026-08-15
prior_report: "docs/reviews/RETROSPECTIVE.md (cycle 10)"
scope: full-scan
stop_condition_met: false
severity_counts: {critical: 0, high: 5, medium: 0, low: 0}
issues:
  - id: R017-D001
    title: T201 的目标/约束数学合同、V1 Schema 与运行族字段矩阵尚未冻结
    severity: high
    category: correctness
    root_cause: root-cause
    origin: process-gap
    pattern_tag: contract-name-without-semantics
    status: open
    fix_summary: ""
    regression_test: "待补：数学 golden vectors、闭集 Schema 与三族允许/拒绝矩阵参数化测试"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/design.md:58
    first_seen_round: 1
    resolved_round: ""
  - id: R017-D002
    title: T202 预注册不存在，2 × 2 的估计量、样本量与停止规则尚未冻结
    severity: high
    category: test-coverage
    root_cause: root-cause
    origin: process-gap
    pattern_tag: implementation-before-preregistration
    status: open
    fix_summary: ""
    regression_test: "待补：0.1.5 预注册结构与冻结字段校验"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/tasks.md:26
    first_seen_round: 1
    resolved_round: ""
  - id: R017-D003
    title: 游标在消费前推进，异常重试会跳过尚未消费的公开事件
    severity: high
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: cursor-commit-before-consume
    status: open
    fix_summary: ""
    regression_test: "待补：消费中途失败后重试不丢事件、成功后游标原子推进的故障注入测试"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/design.md:71
    first_seen_round: 1
    resolved_round: ""
  - id: R017-D004
    title: T220 先推进 done/established，随后才执行 T221，必然违反 gate v1 的 done 门
    severity: high
    category: correctness
    root_cause: root-cause
    origin: process-gap
    pattern_tag: lifecycle-transition-before-final-task
    status: open
    fix_summary: ""
    regression_test: "待补：真实 0.1.5 tasks 的最终状态转换顺序断言"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/tasks.md:70
    first_seen_round: 1
    resolved_round: ""
  - id: R017-D005
    title: R5 要求 README 链接代表性回放，但回放只落被忽略目录且单命令要求没有验收锁定
    severity: high
    category: test-coverage
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: delivery-artifact-not-ci-reachable
    status: open
    fix_summary: ""
    regression_test: "待补：clean checkout 中生成 R5、README 两跳可达、全部链接有效的集成测试"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/design.md:83
    first_seen_round: 1
    resolved_round: ""
---

# 0.1.5 进入开发前终检

**结论：暂不进入产品代码开发。** 当前结构门全绿，但 5 条 High 会让实现者必须自行发明
合同、在失败恢复时丢事件，或在最终收口时撞上必然失败的生命周期/链接门。先完成下面
五条根因修复，再做 round 2 diff-only 复核。

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R017-D001 | T201 的目标/约束数学合同、V1 Schema 与运行族字段矩阵尚未冻结 | High | correctness | root-cause | process-gap | open | 在 Contract 冻结输入单位、risk budget 来源、linear/threshold 方程、阈值、舍入/饱和、冷启动/负权益/无 mark、含挂单和费用时的约束边界；为四个 V1 Schema 写字段类型/可空性/版本/序列化，并列出三族逐字段 allow/deny 矩阵 | 待补：数学 golden vectors、闭集 Schema 与三族允许/拒绝矩阵参数化测试 | 1 | — | contract-name-without-semantics |
| R017-D002 | T202 预注册不存在，2 × 2 的估计量、样本量与停止规则尚未冻结 | High | test-coverage | root-cause | process-gap | open | 在实现统计与正式运行前提交 0.1.5 预注册：冻结 L/M 水平、主/交互估计量、三家族指标、样本量/功效、seed plan、排除/停止规则、BH 集合及校准/验证/实验区 | 待补：0.1.5 预注册结构与冻结字段校验 | 1 | — | implementation-before-preregistration |
| R017-D003 | 游标在消费前推进，异常重试会跳过尚未消费的公开事件 | High | correctness | root-cause | spec-drift | open | design §5 改为先读取旧游标并消费 `(old, current]`，在 EWMA、内部状态与证据事件成功提交后才原子推进；明确失败回滚/重试边界 | 待补：消费中途失败后重试不丢事件、成功后游标原子推进的故障注入测试 | 1 | — | cursor-commit-before-consume |
| R017-D004 | T220 先推进 done/established，随后才执行 T221，必然违反 gate v1 的 done 门 | High | correctness | root-cause | process-gap | open | 将 R5/T221 放到状态转换之前；T220 改为最后一步，并在同一变更中勾完全部任务/AC 后推进状态 | 待补：真实 0.1.5 tasks 的最终状态转换顺序断言 | 1 | — | lifecycle-transition-before-final-task |
| R017-D005 | R5 要求 README 链接代表性回放，但回放只落被忽略目录且单命令要求没有验收锁定 | High | test-coverage | root-cause | spec-drift | open | 冻结 R1—R5 的稳定目录与 `latest` 别名语义；明确 R5 代表性回放的可发布路径或 CI 重建方式；把 R5 单命令重建写入 AC-012/T221 与 clean-checkout 测试 | 待补：clean checkout 中生成 R5、README 两跳可达、全部链接有效的集成测试 | 1 | — | delivery-artifact-not-ci-reachable |

## 正确性通道

- R017-D001 说明 T201 仍是代码前置，不是可以边实现边决定的细节。
- R017-D002 说明 T202 必须先冻结；否则统计实现与样本计划会先看到模型行为再决定。
- R017-D003 与 agent-strategy Contract 的“消费完成后才原子推进”直接冲突。
- R017-D004 会在收口时形成不可满足顺序：`done` 要求 T221 已完成，但任务链要求先 `done`。

## 质量通道

未发现需要单独记录的非阻塞风格问题；本轮问题全部影响可实现性、恢复正确性或验收闭环。

## 验证证据

- `python tools/verify.py`：通过，1861 tests passed，ruff check/format、真源与生命周期全绿。
- 图谱影响面：Markdown 无代码节点，0 个直接/间接受影响节点；改用 spec/design/tasks、
  ADR-003、agent-strategy、event-schema、degenerate-states 与 methodology 人工交叉核对。
- 本轮只报告，不修改被审设计；因此尚未满足最低两轮闭环条件。
