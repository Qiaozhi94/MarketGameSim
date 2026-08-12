# 检视复盘记录

> 每完成一个检视循环(`stop_condition_met` 全部满足)追加一条,不建立新文件。
> 循环进行中的报告见同目录 `CURRENT-doc.md` / `CURRENT-code.md`(按
> `report_type` 分文件,同一时间可以有多个并行);循环内的逐轮细节不再保留
> 独立文件,需要时用 `git log --follow -p` 在本文件历史或已删除的
> `docs/reviews/2026-08-*` 提交记录里找回。

---

## 循环 0: 0.1.1 方向重构与设计文档检视

- **report_type**: doc-review
- **周期**: 2026-07-31 → 2026-08-02(37章/轮,含首次检视+多轮复审)
- **收尾状态**: 0.1.1 全面 Go;除 P1-U01 外全部关闭
- **测试覆盖变化**: 校验器测试由 3 个(全 happy path)扩为 23 个(20 个负向变异)

**遗留一条故意保持开放的项,需要在后续里程碑主动捡回来**:

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P1-U01 | artifact 最小列/键 Schema 未冻结 | Medium | test-coverage | root-cause | spec-drift | open(故意保持) | 未修复(计划0.1.4编码前处理) | — | 第36章 | — | — |

`P1-U01`:artifact 最小列/键 Schema 未冻结。判断结论是**阻断 0.1.4 报告层,
不阻断 0.1.1/0.1.2**,计划在"0.1.2 producer 落地后、0.1.4 编码前"处理。
0.1.2 已于循环1完成退出,这条的前置条件已满足——**进入 0.1.4 编码前必须
显式回来处理这一项**,不要因为原始检视文件已删除就遗忘。这是"故意保持
open"而非"忘了关",`status` 上和真正的遗留 bug 要区分开。

---

## 循环 1: 0.1.2「杠杆与第一个实验闭环」代码实现检视

- **report_type**: fix-verification
- **周期**: 2026-08-03 → 2026-08-09(7天,21轮)
- **构成**: 第1—9轮只读复核(无修复) + 第10—21轮修复(12轮)
- **回归测试**: pytest 由第9轮末尾 831 passed 增至第21轮 1135 passed(净增 304)
- **收尾状态**: E1—E7 + 附加门槛全部 `met`(证据见已归档的
  `docs/experiments/0.1.2-exit-evidence-index.json`)

**关键数据点(暴露的正是本项目引入检视收敛协议的原因)**:
- **前9轮全部是只读复核,零修复落地**——直到第10轮才第一次把发现转成代码改动。
  这本身就是"审查发散"的量化证据:9轮里问题一直在被发现,但收敛条件不存在,
  没有东西驱动它从"发现"走到"关闭"。

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| bridge-residual-rule-noncompliance | 新增回归测试测试只满足新规则四条要求中的一条 | High | test-coverage | symptom-patch | process-gap | fixed | 补齐`_verify_bridge_residuals`降级为warning的原因说明+新增集成测试锁定 | `tests/integration/test_verify_liquidation.py` | 9 | 10 | rule-compliance-gap-on-first-use |
| agent-full-withdrawal-requote-never-wired | 代理策略§6.2全撤重报从未真正接入决策路径 | Critical | correctness | root-cause | process-gap | fixed | 接入决策路径,实现§6.2全撤重报的真实调度逻辑 | 见第18轮报告(已归档,git历史) | 18 | 18 | marked-done-not-implemented |
| chain-depth-parent-link-never-passed | `chain_depth`因从未传递父链信息,任何真实运行都不可能超过0 | High | correctness | root-cause | process-gap | fixed | `_run_post_batch_risk_check`补齐父链信息传递 | 见第19轮报告(已归档,git历史) | 19 | 19 | marked-done-not-implemented |
| kpi-011-zero-sum-declaration-missing | KPI-011(零和恒等式显式声明)历史`[x]`标记但全仓库零实现 | High | correctness | root-cause | process-gap | fixed | 新增`metrics/report.py::build_zero_sum_declaration`并接入`build_study_report` | 见第21轮报告(已归档,git历史) | 21 | 21 | marked-done-not-implemented |

- 第9轮是 CLAUDE.md 新增"每次修复必须补充回归测试"规则后的首次实践检验——
  结果规则写下的同一轮,规则自己点名的反面教材(`_verify_bridge_residuals`
  降级为 warning)就没有按规则要求的方式处理。规则本身对不对不能只看写没写,
  要看第一次真实使用能不能扛住。
- **`marked-done-not-implemented` 模式在本周期至少复现 3 次**(第18/19/21轮),
  且每次都是深挖别的任务时意外撞见,不是主动排查发现的:
  - 第18轮:代理策略 §6.2 全撤重报——本周期最严重发现,组件写了但从未真正接入
    决策路径
  - 第19轮:`chain_depth` 因 `_run_post_batch_risk_check` 从未传递父链信息,
    在任何真实运行中都不可能超过 0
  - 第21轮:KPI-011(零和恒等式显式声明)历史 `[x]` 标记但全仓库零实现
  这类问题的共同特征是"组件本身有测试、但没有接入真实调用链",单元测试绿灯
  不能证明这条路径真的被执行过——这是本项目回归测试盲区里最贵的一类。三条
  的 `origin` 都标 `process-gap` 而不是单纯的 `original-coding`:核心缺陷不是
  "没写代码"本身,是"状态被标记为完成但没人验证过"这个流程漏洞,和
  personahub 循环4(F006)里同一个 `pattern_tag` 复现的案例是跨项目同源问题
  (详见 personahub `docs/reviews/RETROSPECTIVE.md`)。

**如果当时就有本skill的协议,预期会改变什么**:第1—9轮如果套用"资源预算超支即
收窄范围"和"根因分类"两条,大概率不会拖满9轮才出第一个修复;"标记完成、实际
未做"这类问题如果配合 blast-radius/tests_for 图谱查询会更早暴露(它们的共同
特征——测试覆盖存在但未接入真实路径——正是 `query_graph_tool(pattern="tests_for")`
配合执行路径追踪能直接检测的模式)。

---

## 循环 2: 0.1.3-robustness 规格/任务清单检视

- **report_type**: doc-review
- **周期**: 2026-08-08 → 2026-08-09,5轮(同一文件覆盖演进)
- **状态**: 已闭环。本地门禁(`pytest` 1135项/`ruff check .`/`ruff format --check .`/
  任务ID唯一性/`git diff --check`)全绿,提交`a8b8c5b`(docs: 完成0.1.3开发前规格收敛)
  推送后CI四个job(真源自校验/ruff/pytest×2 python版本)全部`success`
- **结论**: 0.1.3需求设计文档达到本地Go,可从T001正式开工

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.1.2-gate-not-satisfied | 0.1.3 spec/tasks要求0.1.2全部退出条件先通过,但0.1.2机器真源当时仍未满足 | Critical | correctness | root-cause | spec-drift | fixed | 待0.1.2循环1真正退出后,T001准入门才允许通过 | `docs/experiments/0.1.2-exit-evidence-index.json` | 1 | 1 | — |
| holdout-failure-blocks-exit | E4"结论在留出验证区复核通过"的措辞会反向激励选择性报告,负结果应该也是有效产出 | High | correctness | root-cause | original-coding | fixed | E4措辞改为"冻结留出区已按预注册计划一次性执行;复核结果如实报告" | — | 1 | 1 | — |
| behaviormapping-dual-output | `BehaviorMapping`同时允许输出目标仓位和订单意图,破坏单变量对照 | High | maintainability | root-cause | original-coding | fixed | 接口收窄为只返回量化后的目标仓位 | — | 1 | 1 | — |
| cell-id-seed-pairing-collision | `cell_id+seed`无法同时标识参数单元与跨处理配对 | High | maintainability | root-cause | original-coding | fixed | 拆分`cell_id`/`pair_id`/`arm_id`三种身份 | — | 1 | 1 | — |
| kpi-008-no-owner | KPI-008有验证器任务但没有产生能力对照证据的任务owner | High | test-coverage | root-cause | original-coding | fixed | 明确KPI-008验收范围与owner | — | 1 | 1 | — |
| paired-bootstrap-loses-pairing | 配对键已定义,但效应量与置信区间未要求使用配对估计,bootstrap会丢失配对结构 | High | correctness | root-cause | original-coding | fixed | T601改为按`pair_id`整对重采样 | — | 2 | 2 | — |
| cell-id-dual-identity | `cell_id`同时被定义为参数单元和具体运行,身份冲突 | Medium | maintainability | root-cause | original-coding | fixed | `cell_id`只含参数,`run_id`另外标识具体运行 | — | 2 | 2 | — |
| min-pair-sample-unfrozen | 最低有效配对样本量及技术失败补位规则未冻结 | Medium | correctness | root-cause | original-coding | fixed | T005预注册最低有效pair数与补位规则 | — | 2 | 2 | — |
| model-family-undefined | "不依赖单一模型族"没有对应的模型族定义、扫描任务或退出证据 | High | maintainability | root-cause | original-coding | fixed | 新增T106定义`model_family_id/version`,预注册至少两个模型族 | — | 2 | 2 | — |
| four-region-conflicts-three-zone | 四个互斥参数区与既有三区协议冲突,"最终报告区"没有数据语义 | High | maintainability | root-cause | spec-drift | fixed | 保持方法论三区,信念实验区再拆exploration/conclusion_holdout子区 | — | 2 | 2 | — |
| e1-behavior-mapping-family-cross-matrix | E1没有要求行为映射×模型族交叉,两个稳健性维度仍可能相互混淆 | High | correctness | root-cause | original-coding | fixed | T105建立`model_family_id×behavior_mapping_id`交叉对照矩阵 | T105/T207/T604/E1文档闭合 | 3 | 3 | — |
| lifecycle-metadata-stale | 0.1.2已完成,但0.1.3生命周期元数据仍显示"待0.1.2退出" | Medium | maintainability | symptom-patch | spec-drift | fixed | spec/tasks/README状态改为`Ready`并同步 | spec/tasks/README状态一致 | 3 | 3 | marked-done-not-implemented |
| model-family-config-diff-unvalidated | 模型族比较缺少对实际差分的校验,可能把非受控改动当作模型族变化 | High | correctness | root-cause | fix-regression | fixed | T403新增合法差分通过/额外字段拒绝/仅改ID拒绝三类TDD文档合同 | T403三类正反TDD文档合同 | 4 | 4 | — |

---

## 循环 3: 真源校验与 0.1.4 Artifact Schema 遗留闭环

- **report_type**: fix-verification
- **周期**: 2026-08-02 → 2026-08-09；遗留项修复后完成 2 轮复核
- **状态**: 已闭环。提交 `f675f73`；本地 1503 tests、`ruff check .`、
  `ruff format --check .`、`git diff --check` 全绿；CI `31316360078` 的真源校验、
  Ruff、pytest 3.11 与 pytest 3.13 全部 `success`
- **范围**: 原根目录 `code-review-report.md` 的 5 项 finding，加第 2 轮发现的 1 项
  fix-regression。循环 0 的 P1-U01 行记录的是当时“不阻断 0.1.1/0.1.2”的历史分级；
  本表按原检视报告的 High 严重度闭环并取代其 open 状态。

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| schema-validator-source-consistency | Schema validator 未覆盖字段 grammar、E-002 与文档字段表的一致性 | High | correctness | root-cause | original-coding | fixed | 增加字段 grammar、结构引用、封闭计数及 JSON↔Markdown/E-002 双向校验 | `tests/unit/test_contract_sources.py::test_schema_mutations_are_rejected`; `::test_new_field_missing_from_doc_is_rejected`; `::test_e002_missing_hash_field_is_rejected` | 1 | 1 | cross-source-contract-drift |
| trace-validator-display-scope | Trace validator 未消费动态 ID family，且不校验 owner scope 与展示表 | High | correctness | root-cause | original-coding | fixed | 从 `tracked_id_families` 生成提取规则，校验 scope、owner、退出条件及展示矩阵 | `tests/unit/test_contract_sources.py::test_trace_mutations_are_rejected`; `::test_rendered_matrix_drift_is_rejected`; `::test_multi_digit_requirement_ids_are_extracted` | 1 | 1 | partial-symmetric-fix |
| artifact-minimum-schema-unfrozen | 10 类上游 artifact 只有版本要求，没有实际最小列/键 Schema | High | correctness | root-cause | spec-drift | fixed | 新增 `report_artifacts.json`，冻结 producer、format、版本、shape 与递归字段类型，并由 spec/T001/T302 引用 | `tests/unit/test_contract_sources.py::test_artifact_schema_mutations_are_rejected`; `::test_artifact_schema_producer_drift_from_spec_is_rejected`; `::test_duplicate_artifact_row_in_spec_is_rejected` | 1 | 2 | schema-version-without-schema |
| validator-tests-happy-path-only | 真源校验测试只有当前仓库 happy path，删除 guard 后仍可全绿 | Medium | test-coverage | root-cause | process-gap | fixed | 校验函数接收可变异 data/text，并为每类 guard 建立仓库内负向测试 | `tests/unit/test_contract_sources.py`（31 tests，含 27 个负向/漂移场景） | 1 | 1 | happy-path-only-gate |
| fixed-pythonhashseed-masks-nondeterminism | 固定 `PYTHONHASHSEED=0` 无法发现误用内置 `hash()` 的跨进程差异 | Medium | test-coverage | root-cause | process-gap | fixed | 保留普通测试固定 seed，同时新增不同 seed 的独立进程输出比较 | `tests/integration/test_cross_process_determinism.py::test_output_is_byte_identical_across_different_hashseeds` | 1 | 1 | fixed-seed-hides-nondeterminism |
| artifact-validator-third-truth-source | 首轮修复在 validator 中又手抄 artifact ID/producer 映射，形成第三真相源 | Medium | correctness | root-cause | fix-regression | fixed | 删除常量映射，完整性只由 registry↔spec 双向集合比较判定，并拒绝重复展示行 | `tests/unit/test_contract_sources.py::test_artifact_schema_mutations_are_rejected`; `::test_duplicate_artifact_row_in_spec_is_rejected` | 2 | 2 | cross-source-contract-drift |

**模式性教训**: `cross-source-contract-drift` 在原始缺陷和首轮修复中各出现一次，说明
“给真源加校验”本身也可能悄悄再造一份真相；正确结构是机器 registry 保存完整合同，
人类展示表只做双向派生核对，validator 不得持有第三份业务映射。来源分布为
`original-coding` 2、`spec-drift` 1、`process-gap` 2、`fix-regression` 1；最长存活的是
`artifact-minimum-schema-unfrozen`，从第 1 轮到第 2 轮关闭，其余均在发现轮关闭。

---

## 循环 4: 0.1.3「模型稳健性」代码实现检视

- **report_type**: fix-verification
- **周期**: 2026-08-09，4 轮（首轮全量 + 3 次针对性修复复核）
- **状态**: 已闭环。HEAD `d052c98`；本地 1524 tests、`ruff check .`、
  `ruff format --check .` 全绿；CI `31319759708` 的真源自校验、ruff、pytest 3.11、
  pytest 3.13 全部 `success`
- **结论**: 1 个 Critical、5 个 High 全部关闭；E1 从错误的“同向成立”修正为如实报告
  “依赖边界”

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v013-cross-matrix-zero-direction | 交叉矩阵忽略零方向单元并错误宣告整矩阵同向成立 | Critical | correctness | root-cause | original-coding | fixed | 全部单元显著、非零且方向一致才允许“同向成立” | `tests/unit/robustness/test_cross_matrix.py::TestReport::test_zero_direction_cells_break_same_direction`; `::test_all_zero_direction_insufficient`; `::test_one_non_significant_cell_insufficient` | 1 | 2 | test-simulates-itself |
| v013-random-path-intersection-only | 共同随机路径只比较键交集，完全错位或空交集仍通过 | High | correctness | root-cause | original-coding | fixed | 比较完整键集并拒绝空路径 | `tests/integration/test_experiment.py::test_check_shared_randomness_parity_detects_key_set_mismatch`; `::test_check_shared_randomness_parity_rejects_empty_path` | 1 | 3 | partial-symmetric-fix |
| v013-signal-family-ablation-index-shift | `signal_family` 消融后仍按原始位置取因子 | High | correctness | root-cause | original-coding | fixed | 因子值携带名称，家族按名称选择 | `tests/unit/agent/test_families.py::TestSignalFamilyAblationNameBinding::test_ablate_other_factor_keeps_momentum_book` | 1 | 2 | index-shift-after-filter |
| v013-bridge-assert-optimized-away | KPI-009 生产门使用 `assert`，`python -O` 下非零残差被接受 | High | correctness | root-cause | original-coding | fixed | 改为显式 `BridgeResidualError` | `tests/integration/test_experiment.py::test_verify_bridge_residuals_raises_on_nonzero_under_opt` | 1 | 2 | safety-check-assert |
| v013-integrity-guards-fail-open | 预注册、配置差分与留出状态机接受合同禁止状态 | High | correctness | root-cause | original-coding | fixed | 对称差分检测删除；`_MISSING` 区分合法 None；零差分拒绝；补齐预注册与留出状态门 | `tests/unit/robustness/test_diff_validator.py::TestOtherContrasts::test_nullable_value_change_is_not_deletion`; `::test_zero_diff_contrast_rejected`; `::test_zero_diff_ablation_rejected`; `::test_deleted_treatment_field_rejected` | 1 | 4 | partial-symmetric-fix |
| v013-signal-family-required-factor-ablation | `signal_family` 对 momentum/book 的 leave-one-out 被修复代码改成直接报错 | High | correctness | symptom-patch | fix-regression | fixed | 对剩余家族因子重归一，仅无家族因子存活时拒绝 | `tests/unit/agent/test_families.py::TestSignalFamilyAblationNameBinding::test_ablate_book_renormalizes_to_momentum`; `::test_ablate_momentum_renormalizes_to_book`; `::test_no_family_factor_left_fails_closed` | 2 | 3 | partial-symmetric-fix |

**模式性教训**: `partial-symmetric-fix` 出现 3 次，是本周期最集中的模式：只检查集合交集、
只检测删除的一种方向、或用症状性 fail-closed 代替正确语义，都会让修复在相邻反例上再次
失效。来源分布为 `original-coding` 5、`fix-regression` 1；最长存活的是
`v013-integrity-guards-fail-open`，从第 1 轮到第 4 轮关闭。后续验证器应优先使用结构化
状态（显式 missing sentinel、完整键集、非空实际差分），并为正反两个方向同时建测试。

---

## 循环 5: 目录结构改造代码检视

- **report_type**: code-review
- **周期**: 2026-08-10，11 轮（首轮全量 + 十轮 diff-only 复核）
- **状态**: 已闭环。HEAD `556c7f8` + round-11 修复；本地 1573 tests、
  `validate_spec_lifecycle`、ruff 0.16 下 check/format 全绿
- **结论**: 2 个 High + 6 个 Medium + 3 个 Low（含 round-1/2/3/7 修复引入的
  STRUCT-C003/C004/C005）全部关闭

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| STRUCT-C001 | 链接与文档所有权门禁未接入生产校验入口 | High | correctness | root-cause | process-gap | fixed | validate_spec_lifecycle 调用 check_docs_links 与 check_ownership_index；分轮补跨层级状态漂移、版本 README 遍历、design/architecture 不变量与字段级合同门禁 | `tests/unit/test_spec_lifecycle.py` 各所有权/链接/不变量用例 | 1 | 7 | test-simulates-itself |
| STRUCT-C002 | 版本级生命周期与 release 收口规则未执行 | High | correctness | root-cause | process-gap | fixed | 新增 validate_versions；round-3 closed_at 结构化解析，正文子串不绕过 | `tests/unit/test_spec_lifecycle.py::test_version_done_prose_closed_at_bypass_fails` 等 | 1 | 3 | marked-done-not-implemented |
| prereq-cycle-false-positive | 环检测对菱形依赖误报 | Medium | correctness | root-cause | original-coding | fixed | 三色 DFS 只判当前路径回边 | `tests/unit/test_spec_lifecycle.py::test_prereq_diamond_not_flagged_as_cycle` | 1 | 1 | — |
| tasks-status-uniqueness-skipped | gate-0 里程碑 tasks 状态不被检查 | Medium | correctness | root-cause | original-coding | fixed | 独立检查 design 与 tasks | `tests/unit/test_spec_lifecycle.py::test_tasks_status_uniqueness_without_design` | 1 | 1 | — |
| dup-id-info-lost | 重复 ID 覆盖丢失首个信息 | Low | quality | root-cause | original-coding | fixed | 保留首个条目，重复追加 __dups__ | `tests/unit/test_spec_lifecycle.py::test_dup_id_preserves_dups` | 1 | 1 | — |
| section-substring-match | 章节子串匹配误匹配 | Low | quality | root-cause | original-coding | fixed | 精确匹配顶层标题 | `tests/unit/test_spec_lifecycle.py` test_gate1_* | 1 | 1 | — |
| STRUCT-C003 | round-1 修复遗留死代码（seen dict 永不触发） | Low | quality | symptom | fix-regression | fixed | 移除永不触发的 seen 逻辑 | `tests/unit/test_spec_lifecycle.py::test_dup_id_preserves_dups` | 2 | 2 | — |
| STRUCT-C004 | 重复 ID 回归测试写入仓库固定路径 | Medium | test-coverage | root-cause | fix-regression | fixed | 改用 pytest tmp_path | `tests/unit/test_spec_lifecycle.py::test_dup_id_preserves_dups` | 3 | 3 | test-writes-repo-state |
| STRUCT-C005 | architecture 门禁把带冒号的合法引用误判为合同复制 | Medium | correctness | symptom | fix-regression | fixed | 先修单行带冒号引用；再改为可判定单行语法：C1:/C2: 后同一行出现方程运算符（=/≡/Σ）才算定义式，不跨行采样、不用固定 token | `tests/unit/test_spec_lifecycle.py::test_architecture_colon_reference_passes`; `::test_architecture_cross_line_reference_passes`; `::test_architecture_generic_equation_fails`; `::test_milestone_design_colon_reference_passes` | 8 | 11 | partial-symmetric-fix |

**模式性教训**: 两个 High 都属于 `marked-done-not-implemented`/`test-simulates-itself`——
把校验函数"写出来"却"没接进生产入口"，CLI 还输出"链接校验通过"，绿灯成了假阳性。
这类缺陷只有"入口级接线测试"能抓住。STRUCT-C001 跨 7 轮、C005 是 round-7 修复引入的
`partial-symmetric-fix`，且因"单行引用放行"用例不足而一路拖到 round-11：先补带冒号引用、
再补跨行误报、再补通用方程漏报。**教训：任何"区分 X 与 Y"的门禁必须同时覆盖 X 放行与
Y 拒绝的每个变体，且最好一开始就用可判定语法（如"同一行方程运算符"）而非启发式
（固定 token 列表、固定字符窗口）——启发式每补一个用例就漏一个相邻反例。** 来源分布
为 `process-gap` 4、`original-coding` 4、`fix-regression` 3、`spec-drift` 1；修复自伤率
稳定在每轮 20-30%，1 轮就宣布闭环是假闭环。

---

## 循环 5-文档: 目录结构改造文档检视

- **report_type**: doc-review
- **周期**: 2026-08-10，11 轮（首轮全量 + 十轮 diff-only 复核）
- **状态**: 已闭环。STRUCT-D001/D002/D003 内容修复成立；D004 在代码通道全部 Medium/High
  清零并通过复核后才标记闭环

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| STRUCT-D001 | releases 目录未纳入 Git 且链接指向目录 | Medium | correctness | root-cause | process-gap | fixed | 新增 releases/README.md 索引，链接改到该文件 | `tests/unit/test_spec_lifecycle.py::test_entry_level_dir_as_file_rejected` | 1 | 1 | marked-done-not-implemented |
| STRUCT-D002 | 改造方案顶部仍称 M030 待确认 | Low | quality | root-cause | spec-drift | fixed | 顶部状态同步为 M030 已完成 | — | 1 | 1 | cross-feature-contract-drift |
| STRUCT-D003 | 文档检视报告仍标 round 1 却宣称第二轮已完成 | Medium | correctness | root-cause | process-gap | fixed | 报告元数据与正文统一为真实轮次 | — | 2 | 3 | marked-done-not-implemented |
| STRUCT-D004 | RETROSPECTIVE 合并报告类型并提前记录闭环 | Medium | correctness | root-cause | process-gap | fixed | report_type 单值化；代码通道 High 与 STRUCT-C005 Medium 清零并通过复核后才闭环 | — | 2 | 11 | marked-done-not-implemented |

**模式性教训**: 文档通道的缺陷集中于 `marked-done-not-implemented`——报告宣称完成
的轮次/状态与元数据、与真实验证结果不一致；且 RETROSPECTIVE 在代码通道仍有 High 时
提前标记"已闭环"。教训：报告 frontmatter 的 round/scope/report_type/stop_condition
必须与正文和实际验证结果严格同步；复盘归档必须在所有相关通道的停止条件都满足后
才标记闭环，不能先写结论后补元数据。

---

## 循环 6: 0.1.4「回放与总结报告」开发前文档检视

- **report_type**: doc-review
- **周期**: 2026-08-11，5 轮（首轮全量 + 4 次 diff-only 复核）
- **状态**: 已闭环。修复提交 `8beb1c9`；本地 `python tools/verify.py` 通过
  1595 tests，CI `31408615638` 的真源与生命周期校验、ruff、pytest 3.11、
  pytest 3.13 全部 `success`
- **结论**: 5 个 High 与 2 个 Medium 全部关闭，0.1.4 可以开始开发

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R014-D001 | 0.1.3 状态真源未关闭，0.1.4 前置条件仍被阻塞 | High | correctness | root-cause | process-gap | fixed | 0.1.3 spec 状态改 done 并同步派生索引；新增 SOP §3 前置状态门 | `tests/unit/test_spec_lifecycle.py::test_prerequisite_not_done_blocks_implementation` 等 3 条 | 1 | 2 | marked-done-not-implemented |
| R014-D002 | 三件套引用不存在的小节并丢失 manifest 与 oracle 的可执行合同 | High | correctness | root-cause | spec-drift | fixed | 补齐三处精确值断言，并将摘要位数接入 spec↔JSON 双向核对 | `tests/unit/test_contract_sources.py::test_manifest_schema_mutations_are_rejected` 3 个变体；`::test_manifest_hash_length_drift_from_spec_is_rejected`；`::test_manifest_hash_length_matches_spec` | 1 | 5 | cross-feature-contract-drift |
| R014-D003 | E5 验收遗漏 NFR-004 禁止导入的 eventlog 模块 | High | test-coverage | root-cause | spec-drift | fixed | E5、AC-005、design 映射与 T402 统一补齐 eventlog | `tests/unit/replay/test_no_kernel_import.py`（0.1.4 实现阶段落地） | 1 | 2 | partial-symmetric-fix |
| R014-D004 | FR-019 的交互控制与强平呈现未进入任何 AC 验收路径 | High | test-coverage | root-cause | spec-drift | fixed | T404 扩为 AC-006；AC 范围门禁只认范围声明语法 | `tests/unit/test_spec_lifecycle.py::test_ac_range_completeness_not_fooled_by_unrelated_mention` | 1 | 4 | acceptance-mapping-gap |
| R014-D005 | 首笔成交前的空 K 线没有确定的 OHLC 规则 | Medium | correctness | root-cause | spec-drift | fixed | 指标字典冻结首笔成交前 OHLC=initial_price | `tests/unit/replay/test_kline.py`（0.1.4 实现阶段落地） | 1 | 2 | undefined-initial-boundary |
| R014-D006 | 总结报告产物格式与机器可验收接口未冻结 | Medium | quality | root-cause | original-coding | fixed | 冻结入口签名、CLI、顶层结构与成功/失败二态 | `tests/integration/test_report_artifacts.py`（0.1.4 实现阶段落地） | 1 | 2 | underspecified-output-contract |
| R014-D007 | artifact_root 同时来自 manifest 与 API 参数且无冲突裁决 | High | correctness | root-cause | fix-regression | fixed | 删除独立 artifact_root 参数/flag，唯一来源改为 manifest | `tests/integration/test_report_artifacts.py`（0.1.4 实现阶段落地） | 2 | 3 | duplicate-source-of-truth |

**模式性教训**: 7 条问题的来源分布为 `spec-drift` 4、`process-gap` 1、
`original-coding` 1、`fix-regression` 1。R014-D002 存活最长（第 1→5 轮）：通用 shape
校验不能替代业务 value 校验，合同字段必须同时覆盖结构合法、精确值和跨真源双向一致性。
R014-D003 的 `partial-symmetric-fix` 与 R014-D007 的 `duplicate-source-of-truth` 进一步说明，
跨文档清单要一次对称更新，API 参数和 manifest 不能并存为同一配置的两个真源。

---

## 循环 7: 0.1.4「回放与总结报告」代码实现检视

- **report_type**: fix-verification
- **周期**: 2026-08-11 → 2026-08-13，11 轮（round 1 全量扫描 → round 2/3/5/6/7/8/9/10
  reviewer 复核 → round 4/6/7/8/9/10/11 修复复核）
- **状态**: 已闭环。修复提交 `9632382`；本地 `python tools/verify.py` 全绿
  （**1811 tests**）；CI `31616754010` 的真源与生命周期校验、ruff、pytest 3.11、
  pytest 3.13 全部 `success`；T403 浏览器验收由 `tools/t403_offline_check.js`
  （含 --self-test）真实 Chrome 离线验证通过
- **结论**: round 1—10 的 45 条发现全部处理完毕

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| public-replay-config-defaults | 公开 build_replay 用硬编码配置默认值 | Critical | correctness | root-cause | original-coding | fixed | RUN_HEADER 增四字段 + ReplayConfig.from_header + build_replay 读 header | `test_replay_frame_consistency.py::test_e1_frame_consistency_through_public_build_replay`；`::test_e1_frame_consistency_non_default_config` | 1 | 2 | duplicate-source-of-truth |
| report-manifest-not-enforced-parquet-as-json | 报告不校验 manifest 内容、JSON 冒充 Parquet | Critical | correctness | root-cause | original-coding | fixed | validate_artifact_value 全量校验（shape/required_fields/嵌套/可空/schema_version）+ ArtifactRead/SchemaError | `test_report_artifacts.py` 空{}/缺字段/错类型/多行 table/非UTF8 夹具 | 1 | 2 | test-simulates-itself |
| e6-controls-malfunction | E6 控件失效（含 OK 误标强平） | High | correctness | root-cause | original-coding | fixed | JS .includes/setTimeout/双序列/底基座/verdict 过滤 | `test_frame_presentation.py` 5 条 + verdict 3 例 | 1 | 2 | — |
| kline-view-absent-period-wrong | K 线缺失且周期 5 小时 | High | correctness | root-cause | original-coding | fixed | 60s 周期 + 参数化 + kline-canvas/drawKlines | `test_kline.py` + `test_frame_presentation.py` | 1 | 2 | — |
| report-decode-failures-escape-contract | 解码失败逃出二态契约 | High | correctness | root-cause | original-coding | fixed | 全路径 try/except 归一化 failure + exit 1 | `test_report_artifacts.py` 不可解码 + CLI | 1 | 2 | — |
| log-reader-accepts-invalid-logs | 读取器接受无效日志 | High | correctness | root-cause | original-coding | fixed | 结构/快照/索引/末提交/版本/run_id 全量校验 | `test_log_reader.py` 10 条 | 1 | 2 | — |
| artifact-path-escape | artifact 路径逃逸 | High | correctness | root-cause | original-coding | fixed | 绝对路径拒绝 + is_relative_to 限制 | `test_manifest.py` 绝对/../ 逃逸 + 批量 | 1 | 2 | trust-boundary-escape |
| html-script-injection | 内联 JSON 脚本注入 | Medium | correctness | root-cause | original-coding | fixed | <,>,& 转义 | `test_script_injection_escaped_in_embedded_data` | 1 | 2 | — |
| frame-missing-timestamp | Frame 缺时间戳 | Medium | correctness | root-cause | original-coding | fixed | Frame.timestamp 取事务时间戳 | `test_frame_sequence.py` 2 条 | 1 | 2 | — |
| large-log-materialization | 大日志物化+重复扫描 | Medium | quality | root-cause | original-coding | fixed | K 线单遍分桶 + JS 循环 min/max | `test_kline.py` 2 条 | 1 | 2 | — |
| downsample-invalid-rules | 非法降采样规则 | Medium | correctness | root-cause | original-coding | fixed | __post_init__ 校验 + CLI 错误退出 | `test_downsampling.py` 5 条 | 1 | 2 | — |
| negative-results-shape-conflict | negative_results 形状冲突 | Medium | correctness | root-cause | spec-drift | fixed | design.md §4 改对象（verbatim） | 字节一致断言保留 | 1 | 2 | — |
| acceptance-tests-prove-markers | 验收测试只证 marker | Medium | test-coverage | root-cause | process-gap | fixed | E1 走公共路径 + 真实 table 夹具；浏览器由 E2/T403 手动 | 公共路径 2 条 + 多行夹具 | 1 | 3 | test-simulates-itself |
| report-pair-atomicity | 报告未成对原子发布 | Low | quality | root-cause | original-coding | fixed | 专属临时目录+fsync+如实文档 | rename 失败 + 无残留 | 1 | 2 | — |
| public-replay-config-defaults-r2 | 生产 header 可用错误默认配置（无生产闭环 E2E） | Critical | correctness | root-cause | original-coding | fixed | build_run_header 四字段必填 + 生产闭环 E2E（cfg→header→日志→build_replay→oracle） | `test_e1_closed_loop_through_build_run_header` | 1 | 3 | duplicate-source-of-truth |
| report-manifest-not-enforced-parquet-as-json-r2 | Parquet 仍按 JSON 解码 | Critical | correctness | root-cause | original-coding | fixed | report_read_format=json 版本化 JSON 投影契约 + 显式消费 + 校验 | `TestReportReadFormat::test_unknown_report_read_format_rejected` | 1 | 3 | test-simulates-itself |
| e6-controls-malfunction-r2 | 权益公式漏 mult/首笔前 mark=0/降采样强平错位 | High | correctness | root-cause | original-coding | fixed | JS 乘 mult + initial_price 回退 + 展示索引映射 | `test_frame_presentation.py` 3 条 | 1 | 3 | partial-symmetric-fix |
| log-reader-accepts-invalid-logs-r2 | bootstrap 精确结构未强制 | High | correctness | root-cause | original-coding | fixed | 前两条 SNAPSHOT 连续事务/顺序/t=0/index=0 强制；契约文档如实改写 | `test_log_reader.py` 6 条 | 1 | 3 | partial-symmetric-fix |
| run-header-fields-without-schema-bump | 必填 header 字段无版本升级 | High | correctness | root-cause | fix-regression | fixed | ADR-004 + event schema v3 + v2 显式拒绝策略 | `test_schema_version_is_3` + 493 测试 | 2 | 3 | cross-version-contract-break |
| report-empty-table-rejected-without-contract | 无约束却拒空 table | High | correctness | root-cause | fix-regression | fixed | 移除空表 blanket 拒绝（空 [] 合法） | `TestTableSemantics` 正反例 | 2 | 3 | overstrict-fail-closed |
| report-cross-artifact-run-id-unchecked | 未校验 artifact run_id 一致 | High | correctness | root-cause | original-coding | fixed | validate_run_id_consistency 全 artifact/行唯一性 | `TestCrossArtifactRunId` 3 条 | 2 | 3 | cross-artifact-consistency-gap |
| frame-missing-timestamp-r2 | 时间轴未用逻辑时间 | Medium | correctness | root-cause | original-coding | fixed | frame-info 展示 f.timestamp | `test_frame_info_displays_logical_timestamp` | 1 | 3 | partial-symmetric-fix |
| large-log-materialization-r2 | build_replay 全量物化再采样 | Medium | quality | root-cause | original-coding | fixed | 构建期按模过滤（downsample 参数） | `test_inline_downsample_matches_post_hoc_apply` | 1 | 3 | partial-symmetric-fix |
| kline-period-invalid-crash | 非正周期除零 | Medium | correctness | root-cause | fix-regression | fixed | API/CLI 拒绝 period_ns<=0，exit 2 | `test_kline.py` 3 条 + CLI 实测 | 2 | 3 | boundary-validation-gap |
| artifact-nullability-hardcoded-outside-registry | 可空规则第三真源 | Medium | quality | root-cause | fix-regression | fixed | nullable 完全下沉 registry（删硬编码） | `TestNullableFromRegistry` 3 条 | 2 | 3 | third-truth-source |

**模式性教训**: 全周期 32 条问题。来源分布：`original-coding` 24、`fix-regression` 5、
`spec-drift` 1、`process-gap` 2。**round 2/3 的 18 条里 5 条是前一轮修复引入的
（`fix-regression`）——修复自伤率稳定在每轮 20-30%，每轮闭环都必须有独立复核轮**。
三类反复出现的模式：
① `partial-symmetric-fix` 出现 6 次（修一半：校验补了顺序没补、字段加了契约没升版、
帧键改了 reader 没改 spec/design/tasks）——**对称性检查（契约两端/清单两端同时更新）
应成为修复的默认动作**；② `test-simulates-itself` 出现 4 次——marker 断言、手写夹具
与"声明 parquet 按 json 读"的格式矛盾，都会系统性高估完成度，验收必须走公共入口 +
真实形状，契约声明必须与消费实现一致；③ `boundary-validation-gap` 3 次——kline 周期、
降采样零匹配这类"合法输入产生非法输出"的边界，必须在 API/CLI 边界显式拒绝。
**最贵的教训是 `duplicate-source-of-truth`（跨 4 轮）与契约漂移**：配置一旦出现在日志
之外就会以默认值回来；文档声明（txn 1/2）与内核实际行为（b/b+1）矛盾时，必须统一
全部真源而不是只改一处。**本轮把从未兑现的 parquet 声明正式改为 json 契约**——仓库
里从未有 parquet 文件，与其保留"设计意图"式的假声明，不如让契约如实描述消费实现。

**round 3/4 补充（6 条）**：

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| report-manifest-not-enforced-parquet-as-json-r3 | 声明 Parquet 却按 JSON 解码 | Critical | correctness | root-cause | original-coding | fixed | 格式契约正式改 json + 删冗余 report_read_format | `TestFormatContract` 2 条 | 1 | 4 | test-simulates-itself |
| log-reader-accepts-invalid-logs-r3 | bootstrap 帧键跨真源冲突 | High | correctness | root-cause | original-coding | fixed | spec/design/tasks/frames/writer 六处统一 b/b+1 | E1 公共路径端到端 | 1 | 4 | partial-symmetric-fix |
| run-header-fields-without-schema-bump-r3 | v2 日志被接受 | High | correctness | root-cause | fix-regression | fixed | read_log 强制 schema_version==3 | `test_log_reader.py` 3 条 | 2 | 4 | cross-version-contract-break |
| frame-missing-timestamp-r3 | timeline 未用逻辑时间 | Medium | correctness | root-cause | original-coding | fixed | timeline 改 timestamp 驱动 | `test_timeline_is_timestamp_based` | 1 | 4 | partial-symmetric-fix |
| acceptance-tests-prove-markers-r3 | 浏览器行为证据缺失 | Medium | test-coverage | root-cause | process-gap | carried-forward | T403/AC-002 撤勾 + 显式待办 | —（手工验收项） | 1 | — | test-simulates-itself |
| downsample-empty-output-breaks-html | 零帧破页 | Medium | correctness | root-cause | original-coding | fixed | 空帧拒绝（ValueError + CLI exit 2） | `test_downsampling.py` 2 条 | 3 | 4 | boundary-validation-gap |

**round 5/6 补充（4 条）**：

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| report-manifest-not-enforced-parquet-as-json-r5 | 格式契约无真实 producer 产物链 | Critical | correctness | root-cause | original-coding | fixed | artifact_export 适配层（真实 producer 输出 → registry 形状）+ 真实 producer E2E | `test_report_real_producers.py` 2 条 | 1 | 6 | test-simulates-itself |
| log-reader-accepts-invalid-logs-r5 | reader 接受缺必填字段 | High | correctness | root-cause | original-coding | fixed | EVENT/trailer 必填字段强制 + event-schema 残留清理 | `test_log_reader.py` 4 条 | 1 | 6 | partial-symmetric-fix |
| timestamp-timeline-collapses-same-time-frames | 同时间戳多帧不可达 | High | correctness | root-cause | fix-regression | fixed | 唯一帧位置 + 时间戳展示 | `test_timeline_reaches_every_frame_with_duplicate_timestamps` | 4 | 6 | non-unique-key-mapping |
| acceptance-tests-prove-markers-r5 | 浏览器行为证据缺失 | Medium | test-coverage | root-cause | process-gap | fixed | t403_offline_check.js 真实 Chrome 离线验证 | `tools/t403_offline_check.js` | 1 | 4 | test-simulates-itself |

**round 5/6 模式教训**: 4 条中 2 条 `fix-regression` 持续出现——round-4 的 timestamp 时间轴
修复引入了「同 timestamp 折叠」新问题（`non-unique-key-mapping`），印证收敛协议每轮
20-30% 自伤率；轮次要继续直到 diff-only 复核不再发现新问题。**最深的根因是
`test-simulates-itself`（跨 5 轮仍未根除）**：测试一直按 registry 自造 artifact，直到
round 5 才发现「真实 producer 根本不产出 registry 形状」——registry 与 producer 从未
接线。修法不是改 label，而是**补上缺失的适配层（artifact_export）+ 真实运行 E2E**，
让「报告能消费真实冻结产物」成为可复现的机器断言。**教训：当契约两端的实现（registry
schema 与 producer 输出）分别开发时，「自证」测试会长期掩盖它们之间的形状分歧；唯一
的根治是双向适配层 + 全链 E2E。** T403 浏览器证据最终以仓库工具
（`tools/t403_offline_check.js`）固化——真实 Chrome 离线验证可重复运行，不再依赖
「手工验收」的空洞勾选。

**round 6/7 补充（3 条）**：

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| report-manifest-not-enforced-parquet-as-json-r7 | 格式链无生产写出口 | Critical | correctness | root-cause | original-coding | fixed | write_artifacts/build_artifacts + CLI + 真实数据驱动负结果/结论 | `test_report_real_producers.py`（生产入口） | 1 | 7 | test-simulates-itself |
| log-reader-accepts-invalid-logs-r7 | trailer 全字段未封闭 | High | correctness | root-cause | original-coding | fixed | §6.2 五字段 + 状态条件 + 边界表 b 标注 | `test_log_reader.py` 3 条 | 1 | 7 | partial-symmetric-fix |
| acceptance-tests-prove-markers-r7 | T403 工具可假绿 | Medium | test-coverage | root-cause | process-gap | fixed | 全合取 pass + 索引 seek + --self-test | `t403_offline_check.js --self-test` | 1 | 7 | test-simulates-itself |

**round 6/7 模式教训**: 三个顽固问题最终都指向同一根因——**「工具/测试能自证通过」不等于
「真实行为正确」**：① 格式链的「自造 artifact」拖到第 7 轮才由「生产写出口 + 真实运行
E2E」根除（适配层 + CLI 让冻结产物链成为生产代码）；② T403 浏览器工具的 `&&`/`||`
优先级让任一 OR 分支即可绕过其余断言（假绿）——验收工具的 pass 判定必须显式括号全
合取，并用 `--self-test` 对已知坏输入做反证；③ trailer 校验的「字段存在才比较」模式
（`if x is not None`）系统性放行缺失字段——契约字段应强制存在而非可选比较。**验收与
校验代码本身也需要被测试**（工具的 self-test、校验器的正反例），否则验收工具就是
`test-simulates-itself` 的最终形态。

**round 7/8 补充（1 条）**：

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| report-manifest-not-enforced-parquet-as-json-r8 | 生产入口伪造 T604/T606 语义 | Critical | correctness | root-cause | original-coding | fixed | 接入真实 build_final_conclusion + NegativeResultReport 封闭枚举门禁 + 真实交叉矩阵 | `test_negative_results_pass_real_t606_validation` | 1 | 8 | test-simulates-itself |

**round 8/9 补充（1 条）**：

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| report-manifest-not-enforced-parquet-as-json-r9 | T105 矩阵不足且 T606 类别语义错配 | Critical | correctness | root-cause | original-coding | fixed | 2×2 真实矩阵 + 按证据语义分类（vanish/reversal/narrow） | 3 条语义测试 + 2×2 E2E | 1 | 9 | test-simulates-itself |

**round 8/9 模式教训**: 「枚举合法」不等于「语义正确」——上一轮修到 T606 枚举合法
（`validate()` 通过），本轮 reviewer 用独立负例证明语义仍错位：消失被标成窄区、反转被
标成消失。**分类逻辑必须按证据语义设计（同族异映射消失 / 显著反向 / 子集显著），并配
三态正反测试锁定**，而不是从枚举里挑一个看起来差不多的类别。另外 1×2 子矩阵因
`CrossMatrix.report` 只对调用方传入维度校验而报 `complete=true`——**完整性校验必须对
真实合同维度（E1 最低 2×2）校验，不能由调用方自报维度**。

**round 7/8 模式教训**: 「真实 producer 链」的最后一层伪装——适配层曾自创
`no_endpoint_effect` 类别并被 T606 封闭枚举拒绝。**当契约方（registry/T606 枚举）已有
自己的语义校验器时，适配层必须直接消费该校验器（fail-closed），而不是另写一套宽松的
字段级校验**——宽松校验正是 `test-simulates-itself` 的隐蔽形态：格式对、语义错。
修复后 robustness_conclusion/negative_results/robustness_effects 全部由真实
T604/T105/T606 producer 构造并经其门禁，E2E 以真实 2-cell 交叉矩阵驱动。至此
`test-simulates-itself` 在 8 轮内被逐步根除：registry 声明 → 消费格式 → 生产写入口 →
真实 producer 语义，每一层都从「自证」换成了「真实产物」。

**round 9/10 补充（1 条）**：

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| report-manifest-not-enforced-parquet-as-json-r10 | 2×2 临时重跑替代冻结上游证据且窄区语义错误 | Critical | correctness | root-cause | original-coding | fixed | 消费冻结 0.1.3 证据 + narrow 仅由参数扫描产生 | family_dependence + narrow_requires_parameter_scan | 1 | 10 | test-simulates-itself |

**round 9/10 模式教训**: 「用真实底层函数重新生成另一套证据」仍是 `test-simulates-itself`
——哪怕函数是真实的，只要结果不是**预注册/冻结**的那一份，就只是另一套未预注册证据。
修复的关键是**把证据来源切到冻结产物**（0.1.4 CLI 读取 `0.1.3-exit-evidence.json` 的
E1 交叉矩阵与 E2 参数扫描），而不是在消费层重现生成。同时 `narrow_parameter_region`
的语义必须绑定**参数轴扫描证据**（failure boundary localization），不能由交叉矩阵的
稀疏性（模型族依赖）推断——**同一个枚举类别必须与同一个证据来源一一对应**，这是
「语义正确」的可判定形式。

**round 10/11 补充（1 条）**：

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| report-manifest-not-enforced-parquet-as-json-r11 | 冻结 E1 结论被不一致 cells 二次重算并反转 | Critical | correctness | root-cause | original-coding | fixed | cells 补 effect_direction + 自一致性门禁 + 原样消费冻结结论 | frozen_evidence_self_consistent + frozen_evidence_gate_rejects | 1 | 11 | test-simulates-itself |

**round 10/11 模式教训**: 本轮暴露了**「冻结产物」自身的字段完整性**问题——0.1.3
evidence 的 E1 cells 序列化丢弃 `effect_direction`（producer 的 >20 阈值规则在序列化后
无法还原），消费方只能从 effect_size 重推方向，导致冻结结论被静默改写。**跨里程碑消费
冻结产物时，产物的自一致性（report == 从其 cells 可重算）必须有 fail-closed 门禁**，
且**序列化必须保留推导所需的全部中间字段**（direction 是独立于 effect_size 的语义，
不能由后者重推）。「原样消费」的关键不是再包一层函数，而是让冻结产物的每个字段都能
逐字传递到最终 report，任何一步的「重推导」都是 `test-simulates-itself` 的变体。
