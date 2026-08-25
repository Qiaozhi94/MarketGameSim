---
report_type: doc-review
round: 7
date: 2026-08-26
prior_report: "round 6 + T201 contract commits through 5c3fcaa"
scope: diff-only
stop_condition_met: false
severity_counts: {critical: 0, high: 1, medium: 0, low: 0}
issues:
  - id: R017-D001
    title: T201 的目标/约束数学合同、V1 Schema 与运行族字段矩阵尚未冻结
    severity: high
    category: correctness
    root_cause: root-cause
    origin: process-gap
    pattern_tag: contract-name-without-semantics
    status: fixed
    fix_summary: "目标数学、退化行为、约束边界、四个 V1 Schema、三族白名单与四类 golden vectors 已落入 goal_contract_v2.json；闭集与重算门禁已接入统一验证"
    regression_test: "tests/unit/test_contract_sources.py::test_goal_contract_mutations_are_rejected、::test_decision_evidence_records_both_cursor_boundaries"
    location: src/market_game_sim/schema/goal_contract_v2.json:1
    first_seen_round: 1
    resolved_round: 7
  - id: R017-D002
    title: T202 预注册尚未冻结，且必填清单未覆盖模型参数
    severity: high
    category: test-coverage
    root_cause: root-cause
    origin: process-gap
    pattern_tag: implementation-before-preregistration
    status: carried-forward
    fix_summary: "预注册结构门禁已就位；仍需执行 T202，并把 risk_appetite 分布与 threshold 参数加入冻结清单"
    regression_test: "tests/unit/test_spec_lifecycle.py::test_preregistration_missing_item_is_rejected 等 5 条；模型参数项待 T202 补"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/tasks.md:33
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
    regression_test: "tests/unit/test_spec_lifecycle.py::test_status_gate_as_final_task_passes"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/tasks.md:79
    first_seen_round: 1
    resolved_round: 2
  - id: R017-D005
    title: R5 的 clean-checkout 链接与单命令成果包要求缺少统一验收
    severity: high
    category: test-coverage
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: partial-symmetric-fix
    status: fixed
    fix_summary: "AC-011 扩至 R1—R5；AC-012、design §8 与 T220 已要求同一条命令在 clean checkout 中生成成果包和仓库内交付入口后再验链接"
    regression_test: "待实现阶段补：tests/integration/test_delivery_entry.py"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/spec.md:203
    first_seen_round: 1
    resolved_round: 5
  - id: R017-D006
    title: 状态回写门禁依赖自然语言正则，既可绕过也会误报
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: fix-regression
    pattern_tag: prose-inferred-lifecycle-gate
    status: fixed
    fix_summary: "已改为显式 [状态门] 标记，校验唯一性和末项位置，不再解析任务措辞"
    regression_test: "tests/unit/test_spec_lifecycle.py::test_status_gate_before_other_tasks_is_rejected、::test_prose_about_done_no_longer_false_positives、::test_duplicate_status_gate_is_rejected"
    location: tools/spec_validation.py:711
    first_seen_round: 2
    resolved_round: 5
  - id: R017-D007
    title: 新增制度约束合同重复扣除 reserved，并把减仓量错误纳入保证金裁剪
    severity: high
    category: correctness
    root_cause: root-cause
    origin: fix-regression
    pattern_tag: cross-contract-margin-double-count
    status: fixed
    fix_summary: "制度约束已与 margin-and-account §3.3 统一为 reserved_after 与 risk_equity 比较，纯减仓豁免，翻仓只约束过零后的新开仓段"
    regression_test: "tests/unit/test_contract_sources.py::test_constraint_layer_uses_the_single_admission_formula"
    location: docs/contracts/agent-strategy.md:288
    first_seen_round: 4
    resolved_round: 5
  - id: R017-D008
    title: 状态门 legacy 豁免用 created 冒充关闭时间，0.1.5 在 done 时可删除标记并绕过门禁
    severity: high
    category: correctness
    root_cause: root-cause
    origin: fix-regression
    pattern_tag: creation-date-used-as-closure-date
    status: fixed
    fix_summary: "取消豁免逻辑（frontmatter 没有'何时关闭'这个事实，created 不是它的代理），0.1.4 的 T405 回填 [状态门] 标记，所有 gate v1 里程碑一律执法"
    regression_test: "tests/unit/test_spec_lifecycle.py::test_missing_status_gate_is_rejected_regardless_of_status_or_created[4 status × 3 created]"
    location: tools/spec_validation.py:744
    first_seen_round: 5
    resolved_round: 5
  - id: R017-D009
    title: 生命周期门与任务依赖对预注册时点互相矛盾
    severity: high
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: two-gates-one-fact
    status: fixed
    fix_summary: "拆成作用域不同的两个门：生命周期门只管能不能开工（ready 不再要求预注册），预注册门管能不能声称（T213 起的统计实现、experiment-preview 与 formal-research 一律阻塞）；tasks §1/§4 补前置条件作用域"
    regression_test: "—（口径统一，无机器判据）；配套的产物结构校验见 D002"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/spec.md:161
    first_seen_round: 5
    resolved_round: 6
  - id: R017-D010
    title: 目标合同门禁允许必备字段、矩阵行与 vectors 被静默删除
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: silent-no-op-gate
    status: fixed
    fix_summary: "校验器锁定结构字段、枚举、三族矩阵、四类 vector ID 和退化语义闭集"
    regression_test: "tests/unit/test_contract_sources.py::test_goal_contract_mutations_are_rejected（新增 15 组）"
    location: tools/spec_validation.py:1203
    first_seen_round: 7
    resolved_round: 7
  - id: R017-D011
    title: DecisionEvidenceV1 缺游标边界且事件 ID 类型误写为 int
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: cross-contract-type-drift
    status: fixed
    fix_summary: "DecisionEvidenceV1 增加 from/to 游标；六个事件 ID 字段统一为 str"
    regression_test: "tests/unit/test_contract_sources.py::test_decision_evidence_records_both_cursor_boundaries、事件 ID 反向变异"
    location: src/market_game_sim/schema/goal_contract_v2.json:44
    first_seen_round: 7
    resolved_round: 7
---

# 0.1.5 进入开发前终检

**当前结论：T201 已收口，0.1.5 可进入工程开发；T202 仍阻塞 T213—T217 与所有研究声明。**
下面保留各轮证据，round 7 的最新状态见文末。

## 发现

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R017-D001 | T201 合同未冻结 | High | correctness | root-cause | process-gap | fixed | 机器合同、闭集、矩阵与 vectors 全部冻结 | 合同正反测试 | 1 | 7 | contract-name-without-semantics |
| R017-D002 | T202 未冻结且漏模型参数 | High | test-coverage | root-cause | process-gap | carried-forward | T213 前冻结真实预注册、risk_appetite 分布和 threshold 参数 | 结构门禁已就位；参数项待补 | 1 | — | implementation-before-preregistration |
| R017-D003 | 游标消费顺序错误 | High | correctness | root-cause | spec-drift | fixed | 已统一为先消费、成功提交后原子推进 | 待实现阶段补：T206 故障注入测试 | 1 | 2 | cursor-commit-before-consume |
| R017-D004 | 状态回写任务早于最终成果门 | High | correctness | root-cause | process-gap | fixed | R5 为 T220，状态门为最后一项 T221 | `test_status_gate_as_final_task_passes` | 1 | 2 | lifecycle-transition-before-final-task |
| R017-D005 | R5 clean-checkout 与单命令验收未统一 | High | test-coverage | root-cause | spec-drift | fixed | AC-011/012、design §8、T220 已同步同一命令生成后验链接 | 待实现阶段补：`test_delivery_entry.py` | 1 | 5 | partial-symmetric-fix |
| R017-D006 | 状态回写门禁依赖自然语言 | Medium | correctness | root-cause | fix-regression | fixed | 显式 `[状态门]` 已替代自然语言正则 | 生命周期门禁 6 组测试 | 2 | 5 | prose-inferred-lifecycle-gate |
| R017-D007 | 约束合同重复扣除 reserved | High | correctness | root-cause | fix-regression | fixed | 已统一 `reserved_after <= risk_equity`、减仓豁免与翻仓分段 | `test_constraint_layer_uses_the_single_admission_formula` | 4 | 5 | cross-contract-margin-double-count |
| R017-D008 | legacy 豁免用 created 冒充关闭时间 | High | correctness | root-cause | fix-regression | fixed | 取消豁免并给 0.1.4 回填真实 `[状态门]` | 12 组状态门测试 | 5 | 5 | creation-date-used-as-closure-date |
| R017-D009 | 生命周期门与预注册门混用 | High | correctness | root-cause | spec-drift | fixed | 两门按作用域拆分 | 预注册结构测试 | 5 | 6 | two-gates-one-fact |
| R017-D010 | 合同门禁可静默漏检 | High | correctness | root-cause | original-coding | fixed | 锁定全部必备闭集和模型数值不变量 | 新增 15 组变异 | 7 | 7 | silent-no-op-gate |
| R017-D011 | 决策游标与事件 ID 类型漂移 | High | correctness | root-cause | original-coding | fixed | 补游标并统一 str | 游标正向 + 类型反向测试 | 7 | 7 | cross-contract-type-drift |

## round 5 复核证据

- **D005**：FR-027/E7、AC-011、AC-012、design §8 与 T220 现已共同锁定 R5 单命令和
  clean-checkout 链接，语义闭合。
- **D006/D008**：显式标记消除了自然语言绕过与误报；但当前豁免实现把
  `status=done && created<规则日` 当成“规则前已关闭”。对创建于 2026-08-14、未来才关闭的
  0.1.5，删除 `[状态门]` 后校验返回零错误，D008 可稳定复现。
- **D007**：新合同与 `margin-and-account §3.3` 的唯一准入式一致，减仓和翻仓边界已修。
- **D001/D002**：修复方选择 carried-forward，而不是关闭；这与 frontmatter 的 High=2
  一致，但仍不满足 review 停止条件。尤其 spec 仍是 `draft`，且明写 ready 前要求 Contract
  与预注册评审通过，不能把 T203“立即执行”解释为完整开发已放行。

## 门禁

- `python tools/verify.py`：通过，1880 tests passed；ruff、format、真源与生命周期全绿。
- `detect_changes_tool(cf33e1e..c9d4148)`：风险 0.55，0 个受影响流程，提示状态回写门禁
  存在测试映射缺口；D008 的变异输入补足了图谱未覆盖的时间语义。
- 当前 HEAD `c9d4148` 的 GitHub check-runs 为空；修复提交 `8c65291` 的历史 CI 绿不能替代
  最新报告提交的 HEAD 门禁。High 未清零，本轮不进入最终 CI/删除阶段。

## 修复回写（round 5 的修复者，2026-08-15）

**D008 采纳并已修**（提交 `c5c148b`）。

**复现确认**：`{status: done, created: 2026-08-14}` + 删掉 `[状态门]` → 校验零错误。
检视人判断准确，这是我在 `9f71d1f` 引入的定时炸弹：0.1.5 一旦转 `done` 就自动落入
豁免，而那正是最需要这道门的时刻。

**根因比"条件写歪"更深一层**：frontmatter 里**根本没有"何时关闭"这个事实**，
`created` 不是它的代理。我前后两版豁免（按 `created` / 按 `done && created`）都在猜
同一个不存在的字段——第一版被 round 4 的自我复核抓到并改成第二版，第二版被本轮抓到。
**同一个错误连犯两次，说明修法本身不对：不该继续找更准的推断条件，而该取消推断。**

按检视人首选方案修：取消豁免分支，0.1.4 的 T405 回填 `[状态门]`——那一项本来就是
"回写 spec 验收证据、活跃索引和状态"，标注是如实描述而非伪造完成。现在没有例外分支，
也就没有第三次猜错的机会。回归测试改为 12 组参数化（4 status × 3 created）断言
"缺标记一律失败"。

### 对本轮报告两处事实的更正

1. **CI 可核验**（第二次出现该判断）：`gh run list --limit 3 --json headSha,conclusion`
   显示 `c9d4148`、`8c65291`、`cf33e1e` 结论均为 `success`。用 `--commit` 参数查不到
   可能是 gh 版本差异，建议改用 `--json headSha` 过滤。
2. **D001/D002 的"生命周期矛盾"部分成立**：报告说"spec 要求 ready 前完成预注册，tasks
   又只要求 T213 前完成"。这确实是两处口径不一致，**我接受这条子结论**，但它是 D002
   衍生出的新问题（口径矛盾），与"预注册产物不存在"（任务未执行）是两件事。下轮修复
   时应拆成独立条目，否则一个 ID 同时代表"任务没做"和"文档打架"，关闭条件无法判定。

### 仍未闭环

D001/D002 仍 carried-forward，关闭路径是执行 T201/T202，不是文档修改。**本文件保留，
删除权在检视人。**

## 修复回写（round 6 的修复者，2026-08-16）

**D002 按 round 5 回写里的提议拆成两条**，并修掉其中可修的那半：

| ID | 内容 | 状态 |
|---|---|---|
| **D009**（新拆出） | 生命周期门与任务依赖对预注册时点互相矛盾 | **fixed**（`c8d730e`） |
| **D002**（本体） | 预注册产物本身不存在 | carried-forward——只能由执行 T202 关闭 |

拆分理由：一个 ID 同时代表"任务没做"和"文档打架"时，关闭条件无法判定——修好文档它
仍然开着，执行完任务又说不清哪部分算修完。

### D009 的修法：两个门作用域不同，不是二选一

报告给的选项是"ready 前完成真实预注册"或"把预注册门移到 T213 前"。两个都不采纳原样，
因为它们默认这是**同一个门的两种放置**。实际是两件事：

- **生命周期门**管"能不能开工"：`ready-for-development` 只要求三件套与 Contract（T201）
  评审通过；
- **预注册门**管"能不能声称"：T202 冻结前只允许 `engineering-demonstration`，T213 起
  的统计实现、`experiment-preview`（R3）与任何 `formal-research` 一律阻塞。

把预注册塞进 `ready` 会让 R1 这种纯工程包装被研究前置卡住，和 PRD §15 的 `R1 → R5`
顺序直接冲突；完全不设门又会让统计实现先看到模型行为再定口径。两个门各管一件事，
两个失败模式都被挡住。`tasks §1` 补了前置条件的作用域说明（`T201` 阻塞 T204—T212，
`T202` 只阻塞 T213—T217，R1 都不阻塞），`§4` 补了 `T202` 不阻塞 `T203—T212` 的显式条目。

### 顺带补上 D002 挂了两轮的 regression_test

D002 的 `regression_test` 字段从 round 1 起一直写着"待补：0.1.5 预注册结构与冻结字段
校验"。现已落地 `validate_preregistrations`：`docs/experiments/*preregistration*.md`
必须覆盖八项必填内容，同时校验模板自身仍覆盖这八项——两边漂移立刻报错，而不是一边
悄悄失效。

产物尚不存在时校验静默通过，但**用 4 条构造测试证明它不是空转的门**（漏"停止规则"
被拒、完整通过、模板漂移被拒、真实仓库模板覆盖八项）——这是循环 9 记下的
`silent-no-op-gate` 判据的直接应用：一个当前没有输入的门，必须先证明它在有输入时会响。

### 仍未闭环

D001（T201 未执行）、D002（T202 未执行）仍 carried-forward，关闭路径是执行任务。
**本文件保留，删除权在检视人。**

## round 7 修复回写（2026-08-26）

- **D001 已关闭**：T201 机器合同、字段闭集、三族矩阵与四类 golden vectors 均已冻结；
  里程碑推进为 `ready-for-development`。
- **D010 已关闭**：此前删除必备字段、`seed_plan` 矩阵行或整个退化 vector 家族仍会绿；
  现在这些变异及模型方程、参数上界漂移全部被 `validate_goal_contract_data` 拒绝。
- **D011 已关闭**：`DecisionEvidenceV1` 直接记录 from/to 游标，所有事件 ID 字段与
  `event_fields.json` 统一为字符串。
- **D002 保留**：T202 尚未执行，且关闭前还需把 `risk_appetite` 分布及
  `theta_in/theta_out/k_x1000` 加入预注册必填项；因此本报告不删除、停止条件仍为 false。
