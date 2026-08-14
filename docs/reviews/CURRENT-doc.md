---
report_type: doc-review
round: 2
date: 2026-08-15
prior_report: round 1（commit 7532c5d）
scope: diff-only
stop_condition_met: true
severity_counts: {critical: 0, high: 0, medium: 7, low: 1}
issues:
  - id: R015-D001
    title: T200 引用 0.1.4 独占的 FR-019/FR-020，R1 成果门在 0.1.5 没有需求锚点
    severity: high
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: cross-feature-contract-drift
    status: fixed
    fix_summary: 新增 FR-027（成果包与成果门产物）并登记 traceability owner/exit E7；T200/T207/T213/T216/T220 五个成果门任务统一改引 FR-027
    regression_test: python tools/verify.py（真源+生命周期校验：owner 缺失、exit 不存在、AC 范围未覆盖均会失败）
    location: docs/features/0.1/0.1.5-goal-driven-flagship/tasks.md:32
    first_seen_round: 1
    resolved_round: 1
  - id: R015-D002
    title: 成果标签三值（含 experiment-preview）与校验器两值不一致，T213 的标记无法落地
    severity: high
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: cross-feature-contract-drift
    status: fixed
    fix_summary: 按决定把 experiment-preview 升为里程碑级 evidence_class（加入 EVIDENCE_CLASSES），PRD 与 features/README 写明取值范围与"只有 formal-research 能建立研究声明"
    regression_test: tests/unit/test_spec_lifecycle.py::test_experiment_preview_is_a_legal_evidence_class、::test_experiment_preview_cannot_establish_research_claim
    location: docs/market-game-sim-prd.md:400
    first_seen_round: 1
    resolved_round: 1
  - id: R015-D003
    title: R1—R5 成果门只在 tasks/PRD 存在，spec 无需求、无 AC、无退出条件，可被静默跳过
    severity: high
    category: test-coverage
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: acceptance-mapping-gap
    status: fixed
    fix_summary: 新增退出条件 E7 与 AC-011（R1—R4 成果包可单命令重建、evidence_class 正确）、AC-012（R5 交付入口两次点击可达）；T217/T218 核对范围由 AC-010 扩到 AC-012
    regression_test: tests/unit/test_spec_lifecycle.py::test_ac_range_completeness_not_fooled_by_unrelated_mention（AC 范围上界门禁，本轮由 AC-012 触发验证）
    location: docs/features/0.1/0.1.5-goal-driven-flagship/spec.md:167
    first_seen_round: 1
    resolved_round: 1
  - id: R015-D004
    title: design.md 未随 tasks 的成果门改动更新，三件套不同步
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: cross-feature-contract-drift
    status: fixed
    fix_summary: design §6 补成果包落盘结构（artifacts/showcase/<gate>/ 四件套 + 生成器强制写入"不可作结论"声明），§8 补 AC-011/AC-012 的测试映射
    regression_test: python tools/verify.py（gate v1 固定章节与三件套一致性）
    location: docs/features/0.1/0.1.5-goal-driven-flagship/design.md:83
    first_seen_round: 1
    resolved_round: 1
  - id: R015-D013
    title: 三处头部块行尾双空格被删，渲染时合并成一段
    severity: low
    category: quality
    root_cause: root-cause
    origin: fix-regression
    pattern_tag: ""
    status: fixed
    fix_summary: agent-strategy.md:4、0.1/spec.md 状态块与里程碑行、ADR-003:4 补回行尾双空格
    regression_test: —（渲染格式，靠 markdown 链接/格式检查与人工阅读）
    location: docs/contracts/agent-strategy.md:4
    first_seen_round: 1
    resolved_round: 2
  - id: R015-D016
    title: 上一循环闭环的 CURRENT-doc.md 删除动作从未提交，工作树长期脏
    severity: low
    category: quality
    root_cause: root-cause
    origin: process-gap
    pattern_tag: closure-not-committed
    status: fixed
    fix_summary: 本循环 round 1 报告直接覆盖该路径并提交（7532c5d），脏状态消解；闭环序列第 4 步补做纯删除提交
    regression_test: —（流程动作）
    location: docs/reviews/CURRENT-doc.md:1
    first_seen_round: 1
    resolved_round: 1
  - id: R015-D017
    title: 0.1.5 三件套与 v0.1 根 spec 的 updated 未随本轮改动更新
    severity: low
    category: quality
    root_cause: root-cause
    origin: process-gap
    pattern_tag: ""
    status: fixed
    fix_summary: 四份文件 updated 同步为 2026-08-15，v0.1 spec 正文的更新日期一并对齐
    regression_test: —（元数据，无机器校验；见 D006 同类缺口）
    location: docs/features/0.1/0.1.5-goal-driven-flagship/spec.md:11
    first_seen_round: 2
    resolved_round: 2
  - id: R015-D005
    title: Phase 2（T208—T211）没有成果门，且三处规则口径互不相同
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: partial-symmetric-fix
    status: carried-forward
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
    status: carried-forward
    fix_summary: ""
    regression_test: ""
    location: docs/features/TEMPLATE/tasks.md:21
    first_seen_round: 1
    resolved_round:
  - id: R015-D007
    title: 任务 ID 不连续，T200 排在 T201/T202 之后
    severity: medium
    category: quality
    root_cause: root-cause
    origin: original-coding
    pattern_tag: ""
    status: carried-forward
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
    status: carried-forward
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
    status: carried-forward
    fix_summary: ""
    regression_test: ""
    location: docs/features/0.1/0.1.5-goal-driven-flagship/spec.md:132
    first_seen_round: 1
    resolved_round:
  - id: R015-D011
    title: established 所需的 evidence_class / research_evidence 字段名未写入 spec 生命周期块
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: ""
    status: carried-forward
    fix_summary: ""
    regression_test: ""
    location: docs/features/0.1/0.1.5-goal-driven-flagship/spec.md:153
    first_seen_round: 1
    resolved_round:
  - id: R015-D012
    title: EV 判据到三终点家族的映射未定义重叠归属与多重比较校正
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: ""
    status: carried-forward
    fix_summary: ""
    regression_test: ""
    location: docs/contracts/degenerate-states.md:175
    first_seen_round: 1
    resolved_round:
  - id: R015-D010
    title: 成果标签定义重复三处，与 docs/README 的唯一拥有者声明冲突
    severity: medium
    category: quality
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: duplicated-source-of-truth
    status: fixed
    fix_summary: PRD 拥有标签语义，features/README 只拥有 frontmatter 取值与组合约束，两处互相引用不再各写一份完整定义
    regression_test: —（所有权归属，由 docs/README 所有权地图与真源自校验覆盖）
    location: docs/features/README.md:56
    first_seen_round: 1
    resolved_round: 1
  - id: R015-D014
    title: PRD 新增「技术里程碑与范围」与后续里程碑同级，形成空章节
    severity: low
    category: quality
    root_cause: root-cause
    origin: original-coding
    pattern_tag: ""
    status: carried-forward
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
    status: fixed
    fix_summary: FR-027 与 design §6 统一为四件套（RUN.md + manifest.json + replay.html + summary.md）全部必需，PRD 的"或"口径不再是唯一依据
    regression_test: AC-011（0.1.5 实现阶段落地为 tests/integration/test_showcase_bundle.py）
    location: docs/market-game-sim-prd.md:433
    first_seen_round: 1
    resolved_round: 1
---

# 0.1.5 需求三件套与配套文档变更检视（doc-review）

## 结论先行

**通过（闭环候选）。** round 1 全量扫描 16 条，round 2 只审修复 diff，新增 1 条
（D017，元数据未同步），未发现修复引入的文档缺陷。3 条 High 全部关闭，根因统一：
`f8f84b9` 只改了 `tasks.md` 与 PRD，没有回到 `spec.md`/`design.md` 建立需求、AC、
退出条件与技术方案。现在 R1—R5 有了 `FR-027 → E7 → AC-011/AC-012` 的完整锚点链，
`T217/T218` 的核对范围也扩到 AC-012，成果门不再能被静默跳过。

7 条 Medium 与 1 条 Low 按协议 §1 显式 carried-forward（不阻塞闭环，理由见文末）。
门禁代码侧另见 `CURRENT-code.md`。

## 发现

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R015-D001 | T200 引用 0.1.4 独占的 FR-019/FR-020，R1 成果门在 0.1.5 没有需求锚点 | High | correctness | root-cause | spec-drift | fixed | 新增 FR-027 + traceability owner/exit E7；五个成果门任务改引 FR-027 | `python tools/verify.py` 真源与生命周期校验 | 1 | 1 | cross-feature-contract-drift |
| R015-D002 | 成果标签三值与校验器两值不一致，T213 的标记无法落地 | High | correctness | root-cause | spec-drift | fixed | experiment-preview 升为里程碑级 evidence_class；两处文本写明取值与组合约束 | `test_experiment_preview_is_a_legal_evidence_class`、`test_experiment_preview_cannot_establish_research_claim` | 1 | 1 | cross-feature-contract-drift |
| R015-D003 | R1—R5 成果门无需求/AC/退出条件，可被静默跳过 | High | test-coverage | root-cause | spec-drift | fixed | 补 E7、AC-011、AC-012；核对范围扩到 AC-012 | `test_ac_range_completeness_not_fooled_by_unrelated_mention` | 1 | 1 | acceptance-mapping-gap |
| R015-D004 | design.md 未随 tasks 的成果门改动更新 | Medium | correctness | root-cause | spec-drift | fixed | design §6 补成果包落盘结构，§8 补 AC-011/012 映射 | `python tools/verify.py` gate v1 结构校验 | 1 | 1 | cross-feature-contract-drift |
| R015-D010 | 成果标签定义重复三处，与所有权地图冲突 | Medium | quality | root-cause | spec-drift | fixed | PRD 拥有语义，features/README 只拥有取值与组合约束 | —（所有权，真源自校验覆盖） | 1 | 1 | duplicated-source-of-truth |
| R015-D015 | 成果包最小构成「或」与 T200「且」不一致 | Low | correctness | root-cause | spec-drift | fixed | FR-027 与 design §6 统一为四件套全部必需 | AC-011（实现阶段落为 `test_showcase_bundle.py`） | 1 | 1 | partial-symmetric-fix |
| R015-D013 | 三处头部块行尾双空格被删，渲染合并成一段 | Low | quality | root-cause | fix-regression | fixed | 三处补回行尾双空格 | — | 1 | 2 | — |
| R015-D016 | 上一循环 CURRENT-doc.md 删除动作从未提交 | Low | quality | root-cause | process-gap | fixed | round 1 报告覆盖该路径并提交，闭环序列补做纯删除提交 | — | 1 | 1 | closure-not-committed |
| R015-D017 | 三件套与根 spec 的 updated 未随改动更新 | Low | quality | root-cause | process-gap | fixed | 四份文件 updated 同步为 2026-08-15，正文日期对齐 | —（无机器校验，见 D006） | 2 | 2 | — |
| R015-D005 | Phase 2（T208—T211）没有成果门，三处规则口径不同 | Medium | correctness | root-cause | spec-drift | carried-forward | — | — | 1 | — | partial-symmetric-fix |
| R015-D006 | 成果门标记格式未统一且无机器校验 | Medium | test-coverage | root-cause | process-gap | carried-forward | — | — | 1 | — | rule-without-gate |
| R015-D007 | 任务 ID 不连续，T200 排在 T201/T202 之后 | Medium | quality | root-cause | original-coding | carried-forward | — | — | 1 | — | — |
| R015-D008 | H1 沙盒的版本归属矛盾（v0.2.1+ vs v0.1 并行） | Medium | correctness | root-cause | spec-drift | carried-forward | — | — | 1 | — | — |
| R015-D009 | IR/DR/TR 六条需求无 AC 或退出条件引用 | Medium | test-coverage | root-cause | original-coding | carried-forward | — | — | 1 | — | acceptance-mapping-gap |
| R015-D011 | established 所需字段名未写入 spec 生命周期块 | Medium | correctness | root-cause | spec-drift | carried-forward | — | — | 1 | — | — |
| R015-D012 | EV → 三终点家族映射未定义重叠与多重比较校正 | Medium | correctness | root-cause | original-coding | carried-forward | — | — | 1 | — | — |
| R015-D014 | PRD「技术里程碑与范围」形成空章节 | Low | quality | root-cause | original-coding | carried-forward | — | — | 1 | — | — |

## round 2 复核记录（diff-only）

复核范围：`3d24ba3`、`6bd0cfd`、`a640956` 三个修复提交的 diff 与相邻契约
（traceability owner/exit、AC 范围门禁、design §8 映射），不重读全文。

- **D001/D003 的锚点链完整**：FR-027 在版本根 spec 声明 → traceability owned/E7 →
  0.1.5 spec §4 与 E7 → AC-011/AC-012 → 五个成果门任务引用，任一环缺失都会被
  `validate_owners`/`_check_ac_range_completeness` 挡下（已实测：改小 tasks 的 AC
  上界会失败）。
- **D002 的两侧都锁住了**：预览可以作为 evidence_class 出现，但不能建立研究声明，
  两个方向各有一条测试。
- **新增 D017**：本轮改了四份规格文件却没动 `updated`，round 2 抓到并修掉。它和
  D006 同类——规则存在但无门禁，只是这次靠人工发现。
- **未发现 fix-regression（文档侧）**：D013 的行尾空格是上一批提交带出来的，
  不是本轮修复引入。代码侧的 fix-regression 见 `CURRENT-code.md` R015-C004。

## carried-forward 的理由

按协议 §1，Medium/Low 记录但不阻塞。以下 8 条明确留到下一循环，不是遗忘：

- **D005/D006/D007**（成果门规则口径、标记格式、任务 ID 顺序）：属于跨 Feature 的
  模板与门禁改造，改动面覆盖 `TEMPLATE/`、`features/README.md` 与所有里程碑
  tasks，应作为独立循环处理，而不是塞进 0.1.5 的锚点修复。
- **D008**（H1 版本归属）：需要产品决定 H1 是否算 v0.1 范围外的并行 Feature，
  属于用户决策而非文档一致性修复。
- **D009/D011/D012**（IR/DR/TR 无 AC、established 字段名、EV 家族映射）：都需要在
  0.1.5 进入 `ready-for-development` 评审前补齐，属于同一份三件套的下一轮细化。
- **D014**（PRD 空章节）：纯排版。

## 停止条件评估

| 条件 | 状态 |
|---|---|
| Critical/High 清零 | ✅ 3 条 High 全部 fixed，剩余 7 Medium + 1 Low 显式 carried-forward |
| 本地 `python tools/verify.py` 全绿 | ✅ 每个修复提交前均跑过（1822→1826 passed，ruff 全绿） |
| 最少 2 轮，第 2 轮 diff-only | ✅ round 2 已执行，新增并关闭 D017 |
| CI 最终门禁跑绿 | 待触发（本轮为收敛候选轮，push 后确认） |
