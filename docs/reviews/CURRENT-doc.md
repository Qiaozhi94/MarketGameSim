---
report_type: doc-review
round: 4
date: 2026-08-15
prior_report: "round 3（commit cf33e1e）"
scope: full-scan
stop_condition_met: false
severity_counts: {critical: 0, high: 4, medium: 1, low: 0}
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
    location: docs/features/0.1/0.1.5-goal-driven-flagship/design.md:74
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
    location: docs/features/0.1/0.1.5-goal-driven-flagship/tasks.md:29
    first_seen_round: 1
    resolved_round: ""
  - id: R017-D003
    title: 游标在消费前推进，异常重试会跳过尚未消费的公开事件
    severity: high
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: cursor-commit-before-consume
    status: fixed
    fix_summary: "design §5、FR-022、AC-002 与 T206 已统一为先消费、成功提交后原子推进，并要求失败回滚与幂等重试"
    regression_test: "待实现阶段补：T206 故障注入测试"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/design.md:98
    first_seen_round: 1
    resolved_round: 2
  - id: R017-D004
    title: T220 先推进 done/established，随后才执行 T221，必然违反 gate v1 的 done 门
    severity: high
    category: correctness
    root_cause: root-cause
    origin: process-gap
    pattern_tag: lifecycle-transition-before-final-task
    status: fixed
    fix_summary: "R5 成果门已移至 T220，状态回写改为最后一项 T221"
    regression_test: "tests/unit/test_spec_lifecycle.py::test_status_writeback_as_final_task_passes"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/tasks.md:79
    first_seen_round: 1
    resolved_round: 2
  - id: R017-D005
    title: R5 的 clean-checkout 链接已修，但单命令成果包要求仍无验收锁定
    severity: high
    category: test-coverage
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: partial-symmetric-fix
    status: open
    fix_summary: ""
    regression_test: "待补：R5 单命令同时生成成果包与仓库内交付入口的集成测试"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/spec.md:116
    first_seen_round: 1
    resolved_round: ""
  - id: R017-D006
    title: 状态回写门禁继续依赖自然语言正则，既可绕过也会误报
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: fix-regression
    pattern_tag: prose-inferred-lifecycle-gate
    status: open
    fix_summary: ""
    regression_test: "待补：显式状态门标记的存在性、唯一性、末项位置与措辞无关测试"
    location: tools/spec_validation.py:711
    first_seen_round: 2
    resolved_round: ""
  - id: R017-D007
    title: 新增制度约束合同重复扣除 reserved，并把减仓量错误纳入保证金裁剪
    severity: high
    category: correctness
    root_cause: root-cause
    origin: fix-regression
    pattern_tag: cross-contract-margin-double-count
    status: open
    fix_summary: ""
    regression_test: "待补：持仓/挂单/手续费总占用、纯减仓与翻仓边界 golden vectors"
    location: docs/contracts/agent-strategy.md:288
    first_seen_round: 4
    resolved_round: ""
---

# 0.1.5 进入开发前终检

**结论：仍不可进入产品代码开发。** round 4 由独立检视人复核 `4fae7c4..cf33e1e`。
修复覆盖 design 约 64%、tasks 约 31%，超过 30% 阈值，因此本轮按协议升级为一次
`full-scan`，范围只含 0.1.5 三件套、相邻 Contract/预注册模板和新增生命周期门禁。

## 发现

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R017-D001 | T201 的目标/约束数学合同、V1 Schema 与运行族字段矩阵尚未冻结 | High | correctness | root-cause | process-gap | open | 完成真实 T201 产物：补 risk_appetite 分布/上界、可执行目标算法、四个 V1 逐字段 Schema、三运行族白名单矩阵和 golden vectors；完成后勾选 T201 | 待补：数学 golden vectors、闭集 Schema 与三族允许/拒绝矩阵参数化测试 | 1 | — | contract-name-without-semantics |
| R017-D002 | T202 预注册不存在，2 × 2 的估计量、样本量与停止规则尚未冻结 | High | test-coverage | root-cause | process-gap | open | 从模板生成真实 0.1.5 预注册，填满八项、评审并冻结后勾选 T202；模板新增清单不能替代该产物 | 待补：0.1.5 预注册结构与冻结字段校验 | 1 | — | implementation-before-preregistration |
| R017-D003 | 游标在消费前推进，异常重试会跳过尚未消费的公开事件 | High | correctness | root-cause | spec-drift | fixed | design/spec/tasks 已统一为消费与证据成功提交后才原子推进，失败保持旧游标并幂等重试 | 待实现阶段补：T206 故障注入测试 | 1 | 2 | cursor-commit-before-consume |
| R017-D004 | T220 先推进 done/established，随后才执行 T221 | High | correctness | root-cause | process-gap | fixed | R5 成果门移至 T220，状态回写改为最后一项 T221 | `test_status_writeback_as_final_task_passes` | 1 | 2 | lifecycle-transition-before-final-task |
| R017-D005 | R5 的 clean-checkout 链接已修，但单命令成果包要求仍无验收锁定 | High | test-coverage | root-cause | spec-drift | open | AC-012、design §8 与 T220 增加：一条命令必须同时生成 R5 四件套和仓库内交付入口；集成测试从 clean checkout 执行该命令再验链接 | 待补：R5 单命令生成与链接集成测试 | 1 | — | partial-symmetric-fix |
| R017-D006 | 状态回写门禁继续依赖自然语言正则，既可绕过也会误报 | Medium | correctness | root-cause | fix-regression | open | 改用显式 `[状态门]`（或等价结构化标记），校验唯一且必须是全文件最后一项，不再猜散文语义 | 待补：显式标记的存在性、唯一性、末项位置测试 | 2 | — | prose-inferred-lifecycle-gate |
| R017-D007 | 新增制度约束合同重复扣除 reserved，并把减仓量错误纳入保证金裁剪 | High | correctness | root-cause | fix-regression | open | 与 margin-and-account §3.3 对齐：按加入目标/意图后的 `reserved_after <= risk_equity` 判定，不写 `equity - reserved`；纯减仓永不因保证金被裁剪，翻仓只约束过零后的新开仓部分 | 待补：持仓/挂单/手续费总占用、纯减仓与翻仓 golden vectors | 4 | — | cross-contract-margin-double-count |

## 正确性通道

- D001/D002 的原问题是“冻结产物不存在”；当前只新增了待办清单，且 T201/T202 仍未勾选、
  `docs/experiments/` 没有 0.1.5 预注册，因此不能标为 fixed。
- D007 与 `margin-and-account.md §3.3` 的唯一准入口径直接冲突：后者明确禁止
  `equity − reserved_units`，因为 `reserved` 已含持仓与全部挂单。
- D006 变异探测：`更新为 done`、`设为 done` 均可绕过；仅写“核对
  `done / established` 前置证据”又会被误报。根因是从自由文本猜状态转换。

## 质量通道

报告的旧 `resolved_round: 1` 与实际修复发生在 round 2/3 不符，本轮已按真实轮次更正；
循环未闭环前，`RETROSPECTIVE.md` 的循环 11 记录只能视为历史错误快照，闭环时需覆盖修正。

## 验证证据

- `python tools/verify.py`：通过，1876 tests passed；ruff check/format、真源与生命周期全绿。
- `detect_changes_tool(4fae7c4..cf33e1e)`：风险 0.55，0 个受影响流程；提示状态回写校验器
  存在测试映射缺口。本轮用三条变异输入独立复现了两次绕过与一次误报。
- `gh run list --commit cf33e1e...`：未返回可核验的远程 CI run；当前有 High 未清零，
  因此不进入收敛候选的最终 CI/删除阶段。
