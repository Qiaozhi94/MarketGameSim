---
report_type: doc-review
round: 5
date: 2026-08-11
prior_report: round 4（本文件 round 4 版本，git 历史可查）
scope: diff-only
stop_condition_met: false
severity_counts: {critical: 0, high: 0, medium: 0, low: 0}
issues:
  - id: R014-D001
    title: 0.1.3 状态真源未关闭，0.1.4 前置条件仍被阻塞
    severity: high
    category: correctness
    root_cause: root-cause
    origin: process-gap
    pattern_tag: marked-done-not-implemented
    status: fixed
    fix_summary: 0.1.3 spec 状态改 done 并同步派生索引；validate_prerequisites 新增 SOP §3 状态门
    regression_test: tests/unit/test_spec_lifecycle.py::test_prerequisite_not_done_blocks_implementation 等 3 条
    location: docs/features/0.1/0.1.3-robustness/spec.md:6
    first_seen_round: 1
    resolved_round: 2
  - id: R014-D002
    title: 三件套引用不存在的小节并丢失 manifest 与 oracle 的可执行合同
    severity: high
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: cross-feature-contract-drift
    status: fixed
    fix_summary: "round 4 复核证明 hex_length 只做了 shape 校验（正偶数）没做 value 校验，62 能通过；hash_algorithm 的 enum 同样只做了 shape 校验，['md5'] 也能通过。本轮在 validate_manifest_schema_data 新增三条精确值断言（hash_algorithm.enum==['blake2b']、hash.hex_length==64、hash.charset=='lowercase_hex'），并把 hex_length 数值接入 validate_manifest_schema_against_spec 的双向核对（spec 文案的『固定 N 位』与机器值不一致即报错）"
    regression_test: tests/unit/test_contract_sources.py::test_manifest_schema_mutations_are_rejected[hash hex_length 合法正偶数但非 64], [hash_algorithm 合法 enum 但非 blake2b], [hash charset 非 lowercase_hex]；::test_manifest_hash_length_drift_from_spec_is_rejected；::test_manifest_hash_length_matches_spec
    location: docs/features/0.1/0.1.4-replay-and-report/spec.md:163
    first_seen_round: 1
    resolved_round: 5
  - id: R014-D003
    title: E5 验收遗漏 NFR-004 禁止导入的 eventlog 模块
    severity: high
    category: test-coverage
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: partial-symmetric-fix
    status: fixed
    fix_summary: E5、AC-005、design.md 映射行、tasks.md T402 统一补齐 eventlog
    regression_test: tests/unit/replay/test_no_kernel_import.py（0.1.4 实现阶段落地）
    location: docs/features/0.1/0.1.4-replay-and-report/spec.md:175
    first_seen_round: 1
    resolved_round: 2
  - id: R014-D004
    title: FR-019 的交互控制与强平呈现未进入任何 AC 验收路径
    severity: high
    category: test-coverage
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: acceptance-mapping-gap
    status: fixed
    fix_summary: T404 范围扩为 AC-006；AC 范围完整性门禁改为只认范围声明语法，不被无关单独提及误导
    regression_test: tests/unit/test_spec_lifecycle.py::test_ac_range_completeness_not_fooled_by_unrelated_mention
    location: tools/spec_validation.py:446
    first_seen_round: 1
    resolved_round: 4
  - id: R014-D005
    title: 首笔成交前的空 K 线没有确定的 OHLC 规则
    severity: medium
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: undefined-initial-boundary
    status: fixed
    fix_summary: 指标字典 §1.9 新增首笔成交前规则，与 risk_mark 口径一致
    regression_test: tests/unit/replay/test_kline.py（0.1.4 实现阶段落地）
    location: docs/research/metrics-dictionary.md:144
    first_seen_round: 1
    resolved_round: 2
  - id: R014-D006
    title: 总结报告产物格式与机器可验收接口未冻结
    severity: medium
    category: quality
    root_cause: root-cause
    origin: original-coding
    pattern_tag: underspecified-output-contract
    status: fixed
    fix_summary: design.md 冻结入口签名/CLI、顶层结构、成功/失败二态与五类 failure.code
    regression_test: tests/integration/test_report_artifacts.py（0.1.4 实现阶段落地）
    location: docs/features/0.1/0.1.4-replay-and-report/design.md:63
    first_seen_round: 1
    resolved_round: 2
  - id: R014-D007
    title: artifact_root 同时来自 manifest 与 API 参数且无冲突裁决
    severity: high
    category: correctness
    root_cause: root-cause
    origin: fix-regression
    pattern_tag: duplicate-source-of-truth
    status: fixed
    fix_summary: build_report 去掉独立 artifact_root 参数/flag，唯一来源改为 manifest 顶层字段
    regression_test: tests/integration/test_report_artifacts.py（0.1.4 实现阶段落地）
    location: docs/features/0.1/0.1.4-replay-and-report/design.md:69
    first_seen_round: 2
    resolved_round: 3
---

# 0.1.4 开发前最终文档检视

## 结论

**本地开发门放行；检视尚未正式闭环。** R014-D002 经历 round 2→3→4→5 四轮迭代才完全关闭——每轮都是同一类
"shape 校验冒充 value 校验"的模式在不同字段上重复出现（hex_length 的奇偶性 vs 精确
值、hash_algorithm 的 enum 形状 vs 精确值），round 5 把三处精确值断言一次性补齐并
接入 spec↔JSON 双向核对，diff-only 复核未再发现同类缺口。本地统一质量门
`python tools/verify.py` 全绿（1595 tests）。`stop_condition_met` 仍为 false，仅因为
修复尚未提交/推送，最终 CI 门没有可验证的远端提交；这不阻塞开始 0.1.4 开发。

## 有限检查清单（round 1）

- [x] 前置里程碑状态、任务与退出证据一致性
- [x] spec / design / tasks 引用与上下游合同可解析性
- [x] FR / NFR / SC 到 AC、任务与测试路径的闭环
- [x] 边界状态：bootstrap、空簿、首笔成交前 K 线、缺失/额外 artifact
- [x] 本地统一质量门：`python tools/verify.py`

## 本轮复核范围（diff-only）

只审 round 4 报告标记为 carried-forward 的 1 条（R014-D002 精确值缺口）对应的
本轮修复 diff，不重新通读全文。

## 发现

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R014-D001 | 0.1.3 状态真源未关闭，0.1.4 前置条件仍被阻塞 | High | 正确性 | 根因 | 流程缺口 | fixed | 状态转 done + 派生索引同步 + 前置状态门 | `test_spec_lifecycle.py` 3 条 | 1 | 2 | marked-done-not-implemented |
| R014-D002 | 三件套引用不存在的小节并丢失 manifest 与 oracle 的可执行合同 | High | 正确性 | 根因 | 规格漂移 | fixed | 补三处精确值断言（enum/hex_length/charset）+ spec↔JSON 位数双向核对 | `test_contract_sources.py` 5 个新变体 | 1 | 5 | cross-feature-contract-drift |
| R014-D003 | E5 验收遗漏 NFR-004 禁止导入的 eventlog 模块 | High | 测试覆盖 | 根因 | 规格漂移 | fixed | 四处清单统一补齐 eventlog | `test_no_kernel_import.py`（实现阶段） | 1 | 2 | partial-symmetric-fix |
| R014-D004 | FR-019 的交互控制与强平呈现未进入任何 AC 验收路径 | High | 测试覆盖 | 根因 | 规格漂移 | fixed | AC 范围完整性门禁改为只认范围声明语法 | `test_ac_range_completeness_not_fooled_by_unrelated_mention` | 1 | 4 | acceptance-mapping-gap |
| R014-D005 | 首笔成交前的空 K 线没有确定的 OHLC 规则 | Medium | 正确性 | 根因 | 规格漂移 | fixed | 冻结首笔成交前 OHLC=initial_price | `test_kline.py`（实现阶段） | 1 | 2 | undefined-initial-boundary |
| R014-D006 | 总结报告产物格式与机器可验收接口未冻结 | Medium | 质量 | 根因 | 原始编写 | fixed | 冻结入口签名/CLI/顶层结构/失败二态 | `test_report_artifacts.py`（实现阶段） | 1 | 2 | underspecified-output-contract |
| R014-D007 | artifact_root 同时来自 manifest 与 API 参数且无冲突裁决 | High | 正确性 | 根因 | 修复引入 | fixed | 去掉独立参数，唯一来源改为 manifest | `test_report_artifacts.py`（实现阶段） | 2 | 3 | duplicate-source-of-truth |

## 本轮 diff 复核记录

- R014-D002（精确值断言）：`validate_manifest_schema_data` 新增三条硬编码业务
  值断言——`hash_algorithm.enum` 必须逐字节等于 `['blake2b']`、`hash.hex_length`
  必须等于 `64`、`hash.charset` 必须等于 `'lowercase_hex'`；三者都独立于
  `_validate_artifact_fields` 的通用 shape 校验（enum 非空数组 / hex_length 正
  偶数 / charset 属于已知集合），后者继续负责结构层面的第一道防线，前者负责
  "就是这个业务值"的第二道防线，与 `validate_artifact_schema_data` 里
  `format not in {"json","parquet"}` 的既有模式一致。
- 独立复现 round 4 描述的确切场景（`hex_length: 62`、`enum: ["md5"]`）均已被
  新断言拒绝；`_manifest_missing_entry_field` 变异（删掉 `hash` 整个字段）在
  新增 `return` 保护下不会在字段集合校验失败后继续对不存在的键取值出错。
- 新增 `validate_manifest_schema_against_spec` 的位数双向核对：解析 spec.md
  "固定 N 位十六进制小写摘要" 中的 N，与机器 `hex_length` 比较；正向测试确认
  当前仓库 64/64 一致，负向测试确认单独改动 spec 文案到 128 会被抓到——这条
  独立于精确值断言，防的是"JSON 值本身没错，但 spec 文案单独漂移"这一半的
  盘。
- 未发现新的 fix-regression：本轮改动只新增校验函数内的断言与对应测试，未触及
  已冻结的字段集合、章节锚点或 AC 范围逻辑。

## 验证证据

- `python tools/verify.py`：通过；1595 tests passed（较 round 4 新增 5 条：
  精确值变异 3 条 + 位数双向核对正反 2 条），真源自校验、生命周期校验、
  ruff check/format 均通过。
- 无任何校验从「失败即拒绝」降级为「仅警告」；本轮新增测试均为正反两面。
- 独立复现验证：`hex_length=62`、`hash_algorithm=["md5"]`、
  `charset="uppercase_hex"`、spec 单独改为 128 位，四种漂移均被明确拒绝。
- R014-D002 的存活轮数（round 1→5，共 4 轮）是本次检视所有 issue 中最长的，
  根因是同一个模式（shape 校验冒充 value 校验）在不同字段上分批暴露，而不是
  审查发散——每轮暴露的都是前一轮遗留的具体新缺口，且每轮都缩小了范围
  （round 2：3 个子问题 → round 3：摘要长度维度 → round 4：值校验维度 →
  round 5：全部补齐），符合收敛而非打转。

## 收尾提示

本轮为本地收敛候选；仓库 CLAUDE.md 要求推送后以 `gh run watch` 确认 CI 全绿才算
正式闭环。本次修复未提交、未推送，尚未触发 CI；并且 `CURRENT-doc.md` 仍是未跟踪
文件，round 1—5 不在 git 历史中。提交时须先纳入版本控制；CI 绿后完整回写 issue 表到
RETROSPECTIVE，再由检视人删除本文件。
