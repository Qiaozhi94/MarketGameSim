---
report_type: doc-review
round: 4
date: 2026-08-15
prior_report: "round 3（commit cf33e1e）"
scope: full-scan
stop_condition_met: false
severity_counts: {critical: 0, high: 2, medium: 0, low: 0}
issues:
  - id: R017-D001
    title: T201 的目标/约束数学合同、V1 Schema 与运行族字段矩阵尚未冻结
    severity: high
    category: correctness
    root_cause: root-cause
    origin: process-gap
    pattern_tag: contract-name-without-semantics
    status: carried-forward
    fix_summary: "本轮不修：这不是文档缺陷，而是任务 T201 尚未执行。数学语义已于 5cf018d 冻结进 agent-strategy §5.2.1—§5.2.4；剩余的 risk_appetite 分布与上界、四个 V1 逐字段 Schema、三族白名单矩阵、golden vectors 属编码产物，只能随实现产生"
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
    status: carried-forward
    fix_summary: "本轮不修：同上，属任务 T202 尚未执行。八项必填清单已进模板，但预注册产物本身要求样本量由功效试算倒推，而功效试算需先能跑起来——在 T203/R1 之前无法诚实填写"
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
    status: fixed
    fix_summary: "AC-011 由 R1—R4 扩到 R1—R5；AC-012 改为同一条命令在 clean checkout 中同时生成成果包与仓库内交付入口、生成后再验四条链接；T220 与 design §8 映射同步"
    regression_test: "待补（T220）：clean checkout 中执行单命令再验链接的集成测试"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/spec.md:116
    first_seen_round: 1
    resolved_round: 4
  - id: R017-D006
    title: 状态回写门禁继续依赖自然语言正则，既可绕过也会误报
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: fix-regression
    pattern_tag: prose-inferred-lifecycle-gate
    status: fixed
    fix_summary: "改用显式 [状态门] 标记（与 [成果门:R1] 同构），校验存在性、唯一性与末项位置，判定与措辞无关；豁免条件定为规则出现时已 done，而非 created 早于规则日"
    regression_test: "tests/unit/test_spec_lifecycle.py::test_status_gate_before_other_tasks_is_rejected[4 措辞]、::test_status_gate_as_final_task_passes、::test_prose_about_done_no_longer_false_positives、::test_missing_status_gate_is_rejected_for_active_milestone、::test_missing_status_gate_exempts_milestones_closed_before_the_rule、::test_duplicate_status_gate_is_rejected"
    location: tools/spec_validation.py:711
    first_seen_round: 2
    resolved_round: 4
  - id: R017-D007
    title: 新增制度约束合同重复扣除 reserved，并把减仓量错误纳入保证金裁剪
    severity: high
    category: correctness
    root_cause: root-cause
    origin: fix-regression
    pattern_tag: cross-contract-margin-double-count
    status: fixed
    fix_summary: "§5.2.4 改为与 margin-and-account §3.3 同口径的 reserved_after <= risk_equity，补减仓豁免与翻仓拆两段，三条边界算例替换原错误算例"
    regression_test: "tests/unit/test_contract_sources.py::test_constraint_layer_uses_the_single_admission_formula"
    location: docs/contracts/agent-strategy.md:288
    first_seen_round: 4
    resolved_round: 4
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

## 修复回写（round 4 的修复者，2026-08-15）

**5 条全部采纳，3 条已修，2 条明确不修并说明原因。** 提交序列：
`efede5e`（D007）→ `9f71d1f`（D006）→ `8c65291`（D005）；CI 在 `8c65291` 四个 job 全绿。

### 已修

| ID | 修复 | 回归测试 | 反向确认 |
|---|---|---|---|
| D007 | §5.2.4 改用 `reserved_after <= risk_equity`（与账户合同 §3.3 同口径），补减仓豁免、翻仓拆两段、三条边界算例 | `test_constraint_layer_uses_the_single_admission_formula` | 把准入式改回旧式 → 测试红 |
| D006 | 显式 `[状态门]` 标记取代自然语言正则，校验存在性/唯一性/末项位置 | 6 组测试（4 种措辞 + 误报 + 缺标记 + 豁免成对 + 重复标记） | 拿掉 0.1.5 的标记 → 门禁报错 |
| D005 | AC-011 扩到 R1—R5；AC-012 改为"同一条命令生成后再验链接"；T220 与 design §8 同步 | 待 T220 落地 | — |

**D007 的复核结论**：检视人完全正确，这是我在 `5cf018d` 引入的真 bug。
`margin-and-account.md §3.3` 不但禁止 `equity − reserved_units`，还写了具体反例
（`equity=1500`、持仓 `100@100`、`10x`：旧式算得可用 500，把实际合法的 140 手判为
超限）。我写 §5.2.4 时没有交叉核对隔壁合同，凭直觉写了个看起来合理的减法式——
**现成答案就在同目录另一份文件里**。

**D006 的复核结论**：变异输入独立复现了检视人报告的两次绕过（`更新为 done`、
`设为 done`）与一次误报（`核对 done / established 的前置证据`）。根因判定一致：
从自由文本猜状态转换。同时修正了自己第一版豁免条件的错误——按 `created` 早于规则日
豁免会把 0.1.5 这种"规则前创建、仍在开发中"的里程碑一并放过，而它恰恰最需要这道门；
改为"规则出现时已 `done`"才豁免。

### 本轮不修，及原因

| ID | 为什么不修 | 什么时候关闭 |
|---|---|---|
| **D001** | **这不是文档缺陷，而是任务 T201 尚未执行。** 数学语义已于 `5cf018d` 冻结进 `agent-strategy §5.2.1—§5.2.4`（两个模型方程、退化输入、约束边界）；检视人点名的剩余项——`risk_appetite` 分布与上界、四个 V1 逐字段 Schema、三族白名单矩阵、golden vectors——是**编码产物**，只能随实现产生，写在文档里既无法验证也无法被测试消费 | 执行 T201 时关闭 |
| **D002** | 同上，属任务 T202 尚未执行。八项必填清单已进 `experiment-template.md`，但预注册产物本身要求**样本量由功效试算倒推**，而功效试算需要能跑起来的管线（R1/R2）。在此之前填一个数字进去，等于把预注册变成事后叙述——这正是 D002 自己要防的 | 执行 T202 时关闭，且必须在 T213 与任何正式运行之前 |

对检视人结论"仍不可进入产品代码开发"的**部分异议**：更准确的表述是
**T204 及以后被 D001/D002 阻塞，但 T203（R1 成果门）不被阻塞**——R1 只把已验证的现有
管线包装成单命令成果包，不依赖新目标模型、不依赖预注册。把 R1 也一并冻结，会让"先拿
到看得见的产物"这个 PRD §15 的核心安排被一条与它无关的前置卡住。

### 一处对报告的更正

报告称 `gh run list --commit cf33e1e...` 未返回可核验的远程 CI run。实测可查：
`cf33e1e`、`5cf018d`、`961e083`、`191daa4`、`4fae7c4` 五个提交的 CI 结论均为
`success`。可能是 `--commit` 参数在不同 `gh` 版本上的匹配方式差异，建议改用
`gh run list --limit N --json headSha,conclusion` 核验。

### 停止条件

未闭环：D001/D002 两条 High 仍开着（按其性质，只能由 T201/T202 的执行关闭，不能由
文档修改关闭）。**本文件保留，删除权在检视人**——上一轮我作为修复者自行删除已被记为
`self-approved-closure` 违规（RETROSPECTIVE 循环 11 补充），不重犯。
