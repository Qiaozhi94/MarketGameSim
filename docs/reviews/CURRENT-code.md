---
report_type: code-review
round: 1
date: 2026-08-15
prior_report: 无（与 CURRENT-doc.md 同批产生，拆分为独立循环）
scope: full-scan
stop_condition_met: false
severity_counts: {critical: 0, high: 1, medium: 2, low: 0}
issues:
  - id: R015-C001
    title: research_claim_required 用字符串比较且字段本身无合法值校验，拼错或写 True 即静默失效
    severity: high
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: fail-open-validation
    status: open
    fix_summary: ""
    regression_test: ""
    location: tools/spec_validation.py:216
    first_seen_round: 1
    resolved_round:
  - id: R015-C002
    title: EVIDENCE_CLASSES 缺 experiment-preview，与文档定义的三值标签体系不一致
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: cross-feature-contract-drift
    status: open
    fix_summary: ""
    regression_test: ""
    location: tools/spec_validation.py:20
    first_seen_round: 1
    resolved_round:
  - id: R015-C003
    title: features/README 声称 gate v1 校验 AC 引用的 requirement 与测试路径，实现不存在
    severity: medium
    category: test-coverage
    root_cause: root-cause
    origin: process-gap
    pattern_tag: rule-without-gate
    status: open
    fix_summary: ""
    regression_test: ""
    location: tools/spec_validation.py:531
    first_seen_round: 1
    resolved_round:
---

# spec_validation.py 新增研究声明/完成态门禁检视（code-review）

## 结论先行

**不通过。** `42d424b` 新增的 `validate_research_claim` 与 `validate_completion_state`
方向正确、负向路径也大体齐备（`research_evidence` 做了绝对路径、逃逸、存在性三重
校验，legacy 迁移映射做了唯一性与目标存在性校验，`_without_fenced_code` 对未闭合围栏
选择 fail-closed——这几处值得保留）。问题集中在**新门禁自身的开关是 fail-open 的**：
一个 frontmatter 键拼错就能让整条研究声明门禁静默消失，而这正是它要防的那类事故。

与文档侧 3 条重合发现（标签体系、承诺未实现的校验）在此以代码视角单独追踪，闭环
证据是 `tests/unit/test_spec_lifecycle.py` 的负向变异测试，不是文档改动。

## 发现

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R015-C001 | `research_claim_required` 用字符串比较且字段本身无合法值校验，拼错或写 `True` 即静默失效 | High | correctness | root-cause | original-coding | open | — | — | 1 | — | fail-open-validation |
| R015-C002 | `EVIDENCE_CLASSES` 缺 `experiment-preview`，与文档定义的三值标签体系不一致 | Medium | correctness | root-cause | spec-drift | open | — | — | 1 | — | cross-feature-contract-drift |
| R015-C003 | features/README 声称 gate v1 校验 AC 引用的 requirement 与测试路径，实现不存在 | Medium | test-coverage | root-cause | process-gap | open | — | — | 1 | — | rule-without-gate |

## 逐条问题与建议修复

### R015-C001（High）

```python
if (
    front.get("status") == "done"
    and front.get("research_claim_required") == "true"
    and claim != "established"
):
```

`parse_frontmatter` 是自研子集解析器，`research_claim_required: true` 得到字符串
`"true"`，所以当前 v0.1 spec 能命中。但：

- 写成 `True` / `yes` / `"true"` 之外的任何变体 → 条件为假，门禁消失，无任何报错；
- 把 key 拼成 `research_claim_requred` → 同样静默放行；
- `validate_frontmatter_meta` 对 `research_claim_status` 做了闭集校验，但对
  `research_claim_required` 没有任何合法值校验。

这与本仓库 fail-closed 原则相反，也和 `research_claim_status` 的处理不对称
（`partial-symmetric-fix`）。更关键的是：这个门禁保护的是"v0.1 能否签收"这件事，
静默失效等于签收闸门不存在。

建议修复：把该字段纳入 `validate_frontmatter_meta` 的闭集校验（合法值仅
`true`/`false`，缺省视为 `false`），比较改为解析后的布尔量；同时对
`research_claim_status: not-applicable` 与 `research_claim_required: true` 并存的组合
显式报错（当前只在 `status == done` 时才检查，draft 阶段的矛盾配置可以一直潜伏）。

配套回归测试（按 CLAUDE.md「正反两种结果都要断言」要求）：
`research_claim_required: True` / 拼错 key / 合法 `true` 三个变体，前两者必须被拒、
第三者在 `established` 时通过。

### R015-C002（Medium）

`EVIDENCE_CLASSES = {"engineering-demonstration", "formal-research"}` 与 PRD §15、
`docs/features/README.md` 定义的三值标签冲突（详见 CURRENT-doc.md R015-D002）。
修复方向取决于文档侧那条决定；无论选哪边，都需要一条负向测试锁定
"`experiment-preview` 能/不能出现在 frontmatter"这个结论，避免以后被无声改回。

### R015-C003（Medium）

`docs/features/README.md` 的 gate 规则写着 gate v1"额外校验……AC 引用真实存在的
requirement 与仓库内测试路径"。`validate_gate1` 实际只做了：固定章节、Q/DQ 关闭、
AC 范围上界完整性。**AC → requirement 存在性、AC → 仓库内测试路径存在性两项都没有
实现。** 0.1.5 的 AC-001—AC-010 恰好完全没有引用任何测试路径，也没被拦下。

这条与 R015-D009（IR/DR/TR 无 AC 覆盖）互为因果：如果这个门禁存在，D009 在写 spec
的当天就会被拦下，而不是靠人工检视发现。

建议修复：实现 `_check_ac_references`，对 gate v1 的 spec 校验每条 AC 括号内引用的
ID 必须在本 spec 声明过，并要求 AC 或其对应 tasks 项至少给出一个存在的仓库内测试
路径；对 `draft` 状态可放宽为"路径可不存在但必须声明"，避免阻塞尚未开工的里程碑。

## 停止条件评估

| 条件 | 状态 |
|---|---|
| Critical/High 清零 | 未满足（1 条 High） |
| 本地 `python tools/verify.py` 全绿 | 已满足（1822 passed）——但三条发现均无测试覆盖 |
| CI 最终门禁触发一次 | 未到收敛候选轮，不触发 |
| 图谱 `detect_changes_tool` 复核 | 修复落地后需跑一次 |

下一轮（round 2）为 `diff-only`，只审修复 diff 与新增测试，不重新通读 `spec_validation.py`。
