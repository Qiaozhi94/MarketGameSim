---
report_type: fix-verification
round: 2
date: 2026-08-15
prior_report: round 1（commit 7532c5d）
scope: diff-only
stop_condition_met: true
severity_counts: {critical: 0, high: 0, medium: 1, low: 0}
issues:
  - id: R015-C001
    title: research_claim_required 用字符串比较且字段本身无合法值校验，拼错或写 True 即静默失效
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: fail-open-validation
    status: fixed
    fix_summary: 新增 BOOL_FIELDS 闭集校验（只允许 true/false），required 解析成布尔量后再比较；并把 required=true 与 not-applicable 的矛盾提前到任意状态就报错
    regression_test: tests/unit/test_spec_lifecycle.py::test_research_claim_required_rejects_non_canonical_boolean[True|yes|TRUE|1]、::test_research_claim_required_accepts_canonical_boolean[true|false]、::test_misspelled_research_claim_required_does_not_silently_disable_gate、::test_research_claim_required_conflicts_with_not_applicable_before_done
    location: tools/spec_validation.py:216
    first_seen_round: 1
    resolved_round: 1
  - id: R015-C002
    title: EVIDENCE_CLASSES 缺 experiment-preview，与文档定义的三值标签体系不一致
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: cross-feature-contract-drift
    status: fixed
    fix_summary: experiment-preview 加入 EVIDENCE_CLASSES（用户决定升为里程碑级证据类别），同时在 validate_research_claim 里锁定它不能建立研究声明
    regression_test: tests/unit/test_spec_lifecycle.py::test_experiment_preview_is_a_legal_evidence_class、::test_experiment_preview_cannot_establish_research_claim
    location: tools/spec_validation.py:20
    first_seen_round: 1
    resolved_round: 1
  - id: R015-C004
    title: 空值 frontmatter 字段让闭集判定抛 TypeError，校验器崩溃而不是报错
    severity: high
    category: correctness
    root_cause: root-cause
    origin: fix-regression
    pattern_tag: validator-crashes-instead-of-reporting
    status: fixed
    fix_summary: 新增 in_enum()（非字符串一律不合法），kind/status/research_claim_status/evidence_class/research_claim_required 五个闭集字段全部改走它
    regression_test: tests/unit/test_spec_lifecycle.py::test_empty_frontmatter_value_is_reported_not_crashed[五个字段各一例]
    location: tools/spec_validation.py:148
    first_seen_round: 2
    resolved_round: 2
  - id: R015-C005
    title: experiment-preview 与 formal-research 两个拒绝分支重复触发，同一配置报两条错
    severity: low
    category: quality
    root_cause: root-cause
    origin: fix-regression
    pattern_tag: ""
    status: fixed
    fix_summary: 改为 if/elif，保留更具体的那条消息
    regression_test: tests/unit/test_spec_lifecycle.py::test_established_requires_done_formal_evidence（既有断言仍成立）
    location: tools/spec_validation.py:196
    first_seen_round: 2
    resolved_round: 2
  - id: R015-C003
    title: features/README 声称 gate v1 校验 AC 引用的 requirement 与测试路径，实现不存在
    severity: medium
    category: test-coverage
    root_cause: root-cause
    origin: process-gap
    pattern_tag: rule-without-gate
    status: carried-forward
    fix_summary: ""
    regression_test: ""
    location: tools/spec_validation.py:531
    first_seen_round: 1
    resolved_round:
---

# spec_validation.py 研究声明/完成态门禁检视（fix-verification）

## 结论先行

**通过（闭环候选）。** round 1 的 1 条 High（研究声明门禁 fail-open）已修；round 2
的 diff-only 复核在**我自己上一轮的修复里**抓到 2 条新问题，其中 C004 是真正的
fix-regression：新加的 `value not in BOOL_VALUES` 在字段写成 `key:`（空值）时会抛
`TypeError: unhashable type: 'list'`——校验器崩溃与校验放行同样糟。已用统一的
`in_enum()` 修掉，并顺带覆盖了四个早就存在同样隐患的旧字段。

这正是协议"最低 2 轮"的价值：C004/C005 在 round 1 物理上不存在，只有第 2 轮的
diff 复核抓得到。

C003（README 承诺但未实现的 AC 校验）为 Medium，显式 carried-forward。

## 发现

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R015-C001 | `research_claim_required` 字符串裸比较且无合法值校验，拼错或写 True 即静默失效 | High | correctness | root-cause | original-coding | fixed | BOOL_FIELDS 闭集校验 + required/not-applicable 矛盾提前报错 | `test_research_claim_required_rejects_non_canonical_boolean` 等 4 组 | 1 | 1 | fail-open-validation |
| R015-C004 | 空值字段让闭集判定抛 TypeError，校验器崩溃而不是报错 | High | correctness | root-cause | fix-regression | fixed | 新增 `in_enum()`，五个闭集字段统一走它 | `test_empty_frontmatter_value_is_reported_not_crashed`（5 个字段） | 2 | 2 | validator-crashes-instead-of-reporting |
| R015-C002 | `EVIDENCE_CLASSES` 缺 experiment-preview，与文档三值体系不一致 | Medium | correctness | root-cause | spec-drift | fixed | 加入闭集并锁定它不能建立研究声明 | `test_experiment_preview_is_a_legal_evidence_class` 等 2 条 | 1 | 1 | cross-feature-contract-drift |
| R015-C005 | 两个拒绝分支重复触发，同一配置报两条错 | Low | quality | root-cause | fix-regression | fixed | 改为 if/elif，保留更具体的消息 | `test_established_requires_done_formal_evidence` | 2 | 2 | — |
| R015-C003 | README 声称 gate v1 校验 AC 引用的 requirement 与测试路径，实现不存在 | Medium | test-coverage | root-cause | process-gap | carried-forward | — | — | 1 | — | rule-without-gate |

## round 2 复核记录（diff-only）

复核范围：`3d24ba3` 的 diff（`tools/spec_validation.py` 与
`tests/unit/test_spec_lifecycle.py`），不重读整个校验器。

1. **C004（fix-regression）**：实测复现——`research_claim_required:` 空值经
   `parse_frontmatter` 得到 `[]`，`[] in {"true","false"}` 直接抛 `TypeError`。
   同样的写法在 `kind`/`status`/`research_claim_status`/`evidence_class` 上早就存在，
   只是没人写过空值。修复用 `in_enum()` 统一处理，回归测试对五个字段各测一次，
   并断言 `[]` 这个前提本身仍成立（`parse_frontmatter` 改行为时测试会明说要重写）。
2. **C005（quality）**：`experiment-preview` 的拒绝分支与既有 `!= formal-research`
   分支重复触发。改 if/elif。
3. **C001 的修复是根因修复**：判定标准（协议 §4）——"以后有人把闭集校验删掉，
   测试会红吗？"会。四组测试分别锁住非闭集值被拒、闭集值通过、拼错 key 时第二道
   防线仍生效、矛盾组合在 draft 阶段就报错。
4. **未发现其它 fix-regression**：`validate_completion_state` 与 legacy 迁移映射逻辑
   本轮未改动，不在 diff 范围内。

## carried-forward 的理由

**C003**（gate v1 的 AC → requirement / 测试路径校验未实现）：实现它需要定义
"draft 阶段是否放宽"的规则，并会立刻让当前多个里程碑的 AC 失败（0.1.5 的
AC-001—AC-012 都没写测试路径）。这是一次独立的门禁改造 + 全仓规格回填，不应塞进
本轮的 fail-open 修复。它与文档侧 D006/D009 属同一模式（`rule-without-gate`），
建议合并成下一个循环处理。

## 停止条件评估

| 条件 | 状态 |
|---|---|
| Critical/High 清零 | ✅ C001、C004 均已修，剩 1 Medium carried-forward |
| 本地 `python tools/verify.py` 全绿 | ✅ 提交前每次跑过（test_spec_lifecycle.py 77→81 passed） |
| 最少 2 轮，第 2 轮 diff-only | ✅ round 2 抓到 2 条，其中 1 条 fix-regression |
| 图谱 `detect_changes_tool` | ✅ 每次提交后跑过；报告的 "Untested: in_enum/validate_*" 是误报——这些函数经 `sv` fixture 动态加载调用，图谱静态解析看不到该边 |
| CI 最终门禁跑绿 | 待触发（本轮为收敛候选轮，push 后确认） |
