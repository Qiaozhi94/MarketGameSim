---
report_type: doc-review
round: 1
date: 2026-08-15
prior_report: 无（新循环，上一循环 0.1.4 开发前检视已归档为 RETROSPECTIVE 循环 6）
scope: full-scan
stop_condition_met: false
severity_counts: {critical: 0, high: 3, medium: 7, low: 5}
issues:
  - id: R015-D001
    title: T200 引用 0.1.4 独占的 FR-019/FR-020，R1 成果门在 0.1.5 没有需求锚点
    severity: high
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: cross-feature-contract-drift
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/features/0.1/0.1.5-goal-driven-flagship/tasks.md:32
    first_seen_round: 1
    resolved_round:
  - id: R015-D002
    title: 成果标签三值（含 experiment-preview）与校验器两值不一致，T213 的标记无法落地
    severity: high
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: cross-feature-contract-drift
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/market-game-sim-prd.md:400
    first_seen_round: 1
    resolved_round:
  - id: R015-D003
    title: R1—R5 成果门只在 tasks/PRD 存在，spec 无需求、无 AC、无退出条件，可被静默跳过
    severity: high
    category: test-coverage
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: acceptance-mapping-gap
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/features/0.1/0.1.5-goal-driven-flagship/spec.md:165
    first_seen_round: 1
    resolved_round:
  - id: R015-D004
    title: design.md 未随 tasks 的成果门改动更新，三件套不同步
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: cross-feature-contract-drift
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/features/0.1/0.1.5-goal-driven-flagship/design.md:90
    first_seen_round: 1
    resolved_round:
  - id: R015-D005
    title: Phase 2（T208—T211）没有成果门，且三处规则口径互不相同
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: partial-symmetric-fix
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/features/0.1/0.1.5-goal-driven-flagship/tasks.md:49
    first_seen_round: 1
    resolved_round:
  - id: R015-D006
    title: 成果门标记格式未统一（[成果门] vs [成果门:R1]）且无机器校验
    severity: medium
    category: test-coverage
    root_cause: root-cause
    origin: process-gap
    pattern_tag: rule-without-gate
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/features/TEMPLATE/tasks.md:21
    first_seen_round: 1
    resolved_round:
  - id: R015-D007
    title: 任务 ID 不连续，T200 排在 T201/T202 之后
    severity: low
    category: quality
    root_cause: root-cause
    origin: original-coding
    pattern_tag: ""
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/features/0.1/0.1.5-goal-driven-flagship/tasks.md:32
    first_seen_round: 1
    resolved_round:
  - id: R015-D008
    title: H1 手动沙盒同时被写成 v0.2.1+ 与 v0.1 期间并行开发，版本归属矛盾
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: ""
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/market-game-sim-prd.md:525
    first_seen_round: 1
    resolved_round:
  - id: R015-D009
    title: IR/DR/TR 六条需求没有任何 AC 或退出条件引用
    severity: medium
    category: test-coverage
    root_cause: root-cause
    origin: original-coding
    pattern_tag: acceptance-mapping-gap
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/features/0.1/0.1.5-goal-driven-flagship/spec.md:176
    first_seen_round: 1
    resolved_round:
  - id: R015-D010
    title: 成果标签定义重复三处，与 docs/README 的唯一拥有者声明冲突
    severity: medium
    category: quality
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: duplicated-source-of-truth
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/features/README.md:56
    first_seen_round: 1
    resolved_round:
  - id: R015-D011
    title: established 所需的 evidence_class / research_evidence 字段名未写入 spec 生命周期块
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: ""
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/features/0.1/0.1.5-goal-driven-flagship/spec.md:149
    first_seen_round: 1
    resolved_round:
  - id: R015-D012
    title: EV 判据到三终点家族的映射未定义重叠归属与多重比较校正
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: ""
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/contracts/degenerate-states.md:175
    first_seen_round: 1
    resolved_round:
  - id: R015-D013
    title: 三处头部块行尾双空格被删，渲染时合并成一段
    severity: low
    category: quality
    root_cause: root-cause
    origin: fix-regression
    pattern_tag: ""
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/contracts/agent-strategy.md:4
    first_seen_round: 1
    resolved_round:
  - id: R015-D014
    title: PRD 新增「技术里程碑与范围」与后续里程碑同级，形成空章节
    severity: low
    category: quality
    root_cause: root-cause
    origin: original-coding
    pattern_tag: ""
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/market-game-sim-prd.md:453
    first_seen_round: 1
    resolved_round:
  - id: R015-D015
    title: 成果包最小构成「replay.html 或 summary.md」与 T200 要求两者都有不一致
    severity: low
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: partial-symmetric-fix
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/market-game-sim-prd.md:433
    first_seen_round: 1
    resolved_round:
  - id: R015-D016
    title: 上一循环闭环的 CURRENT-doc.md 删除动作从未提交，工作树长期脏
    severity: low
    category: quality
    root_cause: root-cause
    origin: process-gap
    pattern_tag: closure-not-committed
    status: open
    fix_summary: ""
    regression_test: ""
    location: docs/reviews/CURRENT-doc.md:1
    first_seen_round: 1
    resolved_round:
---

# 0.1.5 需求三件套与配套文档变更检视（doc-review）

## 结论先行

**不通过。** `python tools/verify.py` 全绿，但绿的是"结构合法"，不是"内容一致"——
本轮 16 条发现里 **0 条会被现有门禁挡下**。三条 high 全部是同一个根因的不同表现：
`f8f84b9`（成果门/交付路线图）只改了 `tasks.md` 和 PRD，没有回到 `spec.md` 和
`design.md` 建立对应的需求、AC、退出条件与技术方案，于是 R1—R5 五个成果门在
0.1.5 里没有任何验收锚点，T217/T218 逐项核对 AC-001—AC-010 时会把它们整体跳过。

审查范围：`42d424b`、`f8f84b9` 两个提交的全部文档改动 + 0.1.5 三件套全文 +
`tools/spec_validation.py` 新增校验逻辑。门禁代码本身的问题另见
`CURRENT-code.md`（3 条），本文只记文档侧。

## 发现

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R015-D001 | T200 引用 0.1.4 独占的 FR-019/FR-020，R1 成果门在 0.1.5 没有需求锚点 | High | correctness | root-cause | spec-drift | open | — | — | 1 | — | cross-feature-contract-drift |
| R015-D002 | 成果标签三值（含 `experiment-preview`）与校验器两值不一致，T213 的标记无法落地 | High | correctness | root-cause | spec-drift | open | — | — | 1 | — | cross-feature-contract-drift |
| R015-D003 | R1—R5 成果门只在 tasks/PRD 存在，spec 无需求、无 AC、无退出条件，可被静默跳过 | High | test-coverage | root-cause | spec-drift | open | — | — | 1 | — | acceptance-mapping-gap |
| R015-D004 | design.md 未随 tasks 的成果门改动更新，三件套不同步 | Medium | correctness | root-cause | spec-drift | open | — | — | 1 | — | cross-feature-contract-drift |
| R015-D005 | Phase 2（T208—T211）没有成果门，且三处规则口径互不相同 | Medium | correctness | root-cause | spec-drift | open | — | — | 1 | — | partial-symmetric-fix |
| R015-D006 | 成果门标记格式未统一（`[成果门]` vs `[成果门:R1]`）且无机器校验 | Medium | test-coverage | root-cause | process-gap | open | — | — | 1 | — | rule-without-gate |
| R015-D007 | 任务 ID 不连续，T200 排在 T201/T202 之后 | Low | quality | root-cause | original-coding | open | — | — | 1 | — | — |
| R015-D008 | H1 手动沙盒同时被写成 v0.2.1+ 与 v0.1 期间并行开发，版本归属矛盾 | Medium | correctness | root-cause | spec-drift | open | — | — | 1 | — | — |
| R015-D009 | IR/DR/TR 六条需求没有任何 AC 或退出条件引用 | Medium | test-coverage | root-cause | original-coding | open | — | — | 1 | — | acceptance-mapping-gap |
| R015-D010 | 成果标签定义重复三处，与 docs/README 的唯一拥有者声明冲突 | Medium | quality | root-cause | spec-drift | open | — | — | 1 | — | duplicated-source-of-truth |
| R015-D011 | established 所需的 `evidence_class` / `research_evidence` 字段名未写入 spec 生命周期块 | Medium | correctness | root-cause | spec-drift | open | — | — | 1 | — | — |
| R015-D012 | EV 判据到三终点家族的映射未定义重叠归属与多重比较校正 | Medium | correctness | root-cause | original-coding | open | — | — | 1 | — | — |
| R015-D013 | 三处头部块行尾双空格被删，渲染时合并成一段 | Low | quality | root-cause | fix-regression | open | — | — | 1 | — | — |
| R015-D014 | PRD 新增「技术里程碑与范围」与后续里程碑同级，形成空章节 | Low | quality | root-cause | original-coding | open | — | — | 1 | — | — |
| R015-D015 | 成果包最小构成「replay.html 或 summary.md」与 T200 要求两者都有不一致 | Low | correctness | root-cause | spec-drift | open | — | — | 1 | — | partial-symmetric-fix |
| R015-D016 | 上一循环闭环的 CURRENT-doc.md 删除动作从未提交，工作树长期脏 | Low | quality | root-cause | process-gap | open | — | — | 1 | — | closure-not-committed |

## 逐条问题与建议修复

### R015-D001（High）

`tasks.md:32` 的 T200 引用 `FR-019`、`FR-020`。这两条在
`docs/features/0.1/traceability.json` 里唯一 owner 是 0.1.4（已 `done`），0.1.5 的
`spec.md` 全文没有它们。后果有两层：R1 成果门在本里程碑没有可验收的需求锚点；
一条已完成里程碑的需求被另一个里程碑的任务重新认领，绕过了"单一 owner + 多 owner
必须切 scope"的规则。

建议：在 0.1.5 spec 新增一条 `FR-027`（工程成果包与单命令生成入口），T200 改引
`FR-027`，traceability 补 owner 与 exit。

### R015-D002（High）

PRD §15「成果口径」表和 `docs/features/README.md` 都定义三类标签，但
`tools/spec_validation.py:20` 的 `EVIDENCE_CLASSES` 只有
`engineering-demonstration` 和 `formal-research`。T213 要求预览 manifest 标
`experiment-preview`——一旦这个值进入任何 spec frontmatter，生命周期校验直接报错。

这一条需要先做一个决定（决定属于用户）：`experiment-preview` 是**里程碑级证据类别**
（那就进 `EVIDENCE_CLASSES`），还是**只作为 manifest/产物字段、不进 frontmatter`**
（那就在 PRD 和 features/README 里显式写明它不是 `evidence_class` 的合法值）。
D003、D010 的改法取决于这个选择。

### R015-D003（High）

R1—R5 五个成果门在 0.1.5 `spec.md` 里没有任何对应物：没有 FR/NFR、没有 AC、
E1—E6 也不涉及。而 T217/T218 的核对范围写死为 `AC-001`—`AC-010`。于是"成果门未
交付"不会导致任何验收项失败——正是本仓库历史上
`marked-done-not-implemented` 的成因结构（RETROSPECTIVE 循环 1 复现 3 次）。

建议：新增 `E7：R1—R5 五个成果门各自产出可打开产物且证据标签正确`，并为 R1/R5
各补一条 AC（R2/R3/R4 可挂在既有 AC-001/AC-006/AC-007 上），tasks 的核对范围随之
扩到 `AC-011`。

### R015-D004（Medium）

`design.md` 停在 `42d424b`，对 `artifacts/showcase/latest/` 的目录结构、`RUN.md` /
`manifest.json` 字段、三类证据标签的落盘位置、`tests/integration/test_showcase_bundle.py`
等三个新测试文件零描述。§8 的验收映射表也没有它们。

### R015-D005（Medium）

`TEMPLATE/tasks.md` 写的是"每个 Phase 末尾必须有一项 `[成果门]`"，`features/README.md`
写的是"必须按可独立演示的 Phase 切分"，PRD 写的是"必须留下至少一个中间成果门"。
三种口径。按最严的模板口径，0.1.5 的 Phase 2（T208—T211，运行族与证据权限）违规。

建议：口径统一到一处（推荐 `features/README.md` 持有规则、PRD 只持有项目级顺序与
估算），然后要么给 Phase 2 补成果门，要么把它并入 Phase 1/3。

### R015-D006（Medium）

模板写 `[成果门]`，0.1.5 实际写 `[成果门:R1]`。格式没定死，将来加校验会直接踩空。
本仓库其它生命周期规则（状态唯一性、AC 范围、legacy 迁移映射）都有门禁，只有这条
纯靠人工——参考 RETROSPECTIVE 循环 1 的教训，"规则写下的同一轮就被违反"是常态。

### R015-D007（Low）

`tasks.md` 里 T200 出现在 T201/T202 之后。模板要求"任务 ID 必须全文件连续且唯一"。
依赖节又写"T200 立即执行"，编号顺序与执行顺序双重矛盾。建议整体重排为
T201（成果基线）/ T202（Contract 冻结）/ T203（预注册）…… 或把 Phase 0 提到第 1 节之前。

### R015-D008（Medium）

PRD 把 H1 手动沙盒放进 `### v0.2.1+：交易者沙盒与人在环实验`，同一节又写"H1 可在
R3/R4 期间并行开发"，0.1.5 `tasks.md` §5 也写"R2 后的 H1 独立 Feature"。v0.1 尚未
收口就并行开 v0.2.1 内容，与"完整 v0.1 签收 = 0.1.1—0.1.5 全部通过"的收口定义冲突。
建议：要么把 H1 明确成"v0.1 之外、不参与签收的并行 Feature"，要么老实排到 v0.1 之后。

### R015-D009（Medium）

`IR-501`、`IR-502`、`DR-501`、`DR-502`、`TR-501`、`TR-502` 只在 §4 声明和 tasks 引用，
AC-001—AC-010 没有一条引用它们，E1—E6 也不点名。接口/数据/事件三类需求整体缺验收锚点。

### R015-D010（Medium）

三类证据标签同时定义在 PRD §15 表、`features/README.md` 和 `spec_validation.py` 常量里，
而 `docs/README.md` 的所有权地图刚把"阶段成果"判给 PRD 独占。三份定义已经不一致（见
D002），正是重复真源的典型后果。

### R015-D011（Medium）

`spec.md` §5 写 `not-established -> established  status=done 且 formal-research evidence
index 存在`，但校验器实际要求的是 frontmatter 里的 `evidence_class: formal-research`
和 `research_evidence: [仓库内相对路径]` 两个 key。spec 和 tasks 都没写出这两个字段名，
实施到 T219 时必漏。

### R015-D012（Medium）

`degenerate-states.md` 新增的方向映射把 EV-4 按 bid/ask 侧分给崩盘/暴涨，但 EV-4
（单边清空且无新增挂单）本身也满足流动性枯竭的语义；EV-3 与 EV-4 的重叠归属没定义。
同时写了"同一运行可命中多个家族"，却没说明三族分别推断时用什么多重比较校正
（ADR-003 说"预注册各自校正"，方法未定）。

### R015-D013（Low）

三处头部元数据块的行尾双空格被删除，Markdown 渲染时与下一行合并：
`docs/contracts/agent-strategy.md:4`、`docs/features/0.1/spec.md:15-17`、
`docs/decisions/003-goal-driven-agents-and-flagship-identification.md:4`。
`origin` 标 `fix-regression`：这是 `42d424b` 改文案时带出来的。

### R015-D014（Low）

PRD 新增的 `### 技术里程碑与范围` 与其后的 `### 0.1.1` 同为三级标题，形成一个空章节，
里程碑并没有从属于它。应升为二级或改成普通引导句。

### R015-D015（Low）

PRD 写"每个成果包至少包含 `RUN.md`、`manifest.json`、一个 `replay.html` **或**
`summary.md`"，T200 要求两者都有。另：README 已声明 0.1.4 交付了离线 HTML 回放与报告
能力，R1 仍估 4–8 小时，文档没说明 R1 相对既有 0.1.4 产物的增量是什么。

### R015-D016（Low）

`docs/reviews/CURRENT-doc.md` 在 HEAD 中存在（0.1.4 循环的 round 5 终版），但工作树里
被删除且从未提交，导致每次会话开工自检都报"未提交的共享文档改动"。上一循环的闭环
第 6 步只做了一半。本轮新报告直接覆盖该文件，脏状态随本轮提交消解。

## 停止条件评估

| 条件 | 状态 |
|---|---|
| Critical/High 清零 | 未满足（3 条 High） |
| 本地 `python tools/verify.py` 全绿 | 已满足（1822 passed，ruff 全绿）——但对本轮全部发现无检出能力 |
| CI 最终门禁触发一次 | 未到收敛候选轮，不触发 |
| 图谱 `detect_changes_tool` 复核 | 本轮为纯文档变更，不适用 |

下一轮（round 2）为 `diff-only`，只审本轮修复的 diff 及其相邻契约，不重新通读全文。
