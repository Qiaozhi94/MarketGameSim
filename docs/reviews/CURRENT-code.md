---
report_type: fix-verification
round: 11
date: 2026-08-13
prior_report: 本文件 round 10 版本（reviewer diff-only，1 Critical，1 条 open）
scope: diff-only
stop_condition_met: false
severity_counts: {critical: 0, high: 0, medium: 0, low: 0}
issues:
  - id: report-manifest-not-enforced-parquet-as-json
    title: 冻结 E1 结论被不一致 cells 二次重算并反转
    severity: critical
    category: correctness
    root_cause: root-cause
    origin: original-coding
    pattern_tag: test-simulates-itself
    status: fixed
    fix_summary: 根因是 0.1.3 evidence 的 E1 cells 序列化丢弃 effect_direction（producer 用 diff>20 阈值判方向，signal diff=10 → direction=0），adapter 用 sign(effect_size) 重推导致结论反转。修复：run_robustness_demo.py 的 E1 cells 序列化补 effect_direction/ci 字段；证据文件补上真实 effect_direction；新增 verify_frozen_evidence 自一致性门禁（cells 重算 report 必须等于冻结 report，fail-closed）；write_artifacts/build_artifacts 改为接收冻结 evidence 整体并先过门禁；robustness_conclusion 原样消费冻结 conclusion
    regression_test: test_report_real_producers.py 新增 frozen_evidence_self_consistent（冻结结论 依赖边界 原样进入 T604，不被翻转为 同向成立）+ frozen_evidence_gate_rejects（篡改 direction 被门禁拒绝）；narrow 测试改用真实冻结 boundary 字段
    first_seen_round: 1
    resolved_round: 11
---

# 0.1.4「回放与总结报告」代码实现检视 — round-10 修复复核（round 11）

## 结论

**round 10（reviewer diff-only）的 1 Critical 已修复。** 本地统一质量门
`python tools/verify.py` 全绿（**1811 tests passed**），真源自校验、规格生命周期、
ruff check/format 全部通过。冻结 0.1.3 E1 证据自一致性恢复：cells 携带真实
effect_direction，冻结 report 与 cells 重算一致；adapter 通过 `verify_frozen_evidence`
门禁后**原样消费冻结 conclusion**（依赖边界），不再被 cells 重算翻转为同向成立。

**`stop_condition_met: false`**：检视人已独立运行本地门禁，GitHub CLI 认证也已
恢复；CI 最终门禁尚未触发。在本轮提交对应的 CI 全绿前保留本文件，不宣告闭环。

## 本轮复核范围（diff-only）

复核 round 10 的 1 条 Critical 对应修复：

- **根因定位**：0.1.3 demo 的 E1 cell 用 `diff > 20` 阈值判 `effect_direction`
  （signal diff=10 → direction=0），但 cells **序列化时丢弃 effect_direction**；
  adapter 用 `sign(effect_size)` 重推 direction（signal 变 +1），重算结论
  同向成立 ≠ 冻结结论 依赖边界。冻结证据本身是自洽的（report 与带 direction 的
  cells 一致），丢字段的是序列化。
- **修复**：
  1. `tools/run_robustness_demo.py`：E1 cells 序列化补 `effect_direction`/`ci_low`/
     `ci_high`（producer 侧根因）；
  2. `docs/experiments/0.1.3-exit-evidence.json`：4 个 cell 补真实 effect_direction
     （belief→1、signal→0，按 producer 阈值规则）；
  3. `verify_frozen_evidence` 自一致性门禁：从冻结 cells（含 effect_direction 逐字
     消费）重算 report，必须等于冻结 report，否则 ValueError（fail-closed）；
  4. `write_artifacts`/`build_artifacts` 改为接收**冻结 evidence 整体**，先过门禁再
     消费；`robustness_conclusion_artifact` 直接接收冻结 conclusion 逐字使用。

## 发现

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| report-manifest-not-enforced-parquet-as-json | 冻结 E1 结论被不一致 cells 二次重算并反转 | Critical | 正确性 | 根因 | 原始编写 | fixed | cells 补 effect_direction + 自一致性门禁 + 原样消费冻结结论 | frozen_evidence_self_consistent + frozen_evidence_gate_rejects | 1 | 11 | test-simulates-itself |

## 本轮 diff 复核记录

- **证据自洽恢复**：修复后 `verify_frozen_evidence` 对真实冻结证据通过（冻结
  conclusion=依赖边界 与 cells 重算一致）；篡改任一 cell 的 direction 即被门禁拒绝
  （fail-closed 反例测试）。
- **结论逐字消费**：`robustness_conclusion_artifact` 的 cross_verdict 来自冻结
  report，T604 文本包含 依赖边界；`test_frozen_evidence_self_consistent` 断言冻结结论
  未被翻转为 同向成立。
- **narrow 字段保真**：`test_narrow_region_requires_parameter_scan` 改用真实冻结
  boundary（axis="700" 字符串），逐字段断言 machine_readable 与冻结产物一致。
- **fix-regression 检查**：无新引入 High/Critical；`verify.py` 全绿（1811 tests）。

## 验证证据

- `python tools/verify.py`：通过；**1811 tests passed**（较 round 10 净增 2 条）；
  真源自校验、规格生命周期、ruff check/format 全通过。
- 门禁测试：真实证据通过；篡改 direction 被拒（ValueError）。
- 结论保真：robustness_conclusion.elements.cross_verdict == 冻结 conclusion（依赖边界）。
- **待办**：commit/push，并用 `gh run watch <run-id> --exit-status` 确认全部 job
  全绿。
