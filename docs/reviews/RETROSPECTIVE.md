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

## 循环 5: 目录结构改造代码/文档检视

- **report_type**: code-review（含 doc-review 并行通道）
- **周期**: 2026-08-10，2 轮（首轮全量 + 一轮 diff-only 复核）
- **状态**: 已闭环。HEAD `26dfa00`；本地 1562 tests、`validate_spec_lifecycle`、
  `verify.py` 全绿
- **结论**: 2 个 High（链接/所有权门禁未接线、版本收口规则未执行）+ 4 个 Medium/Low
  原始缺陷 + 1 条 round-1 修复引入的死代码，全部关闭

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| STRUCT-C001 | 链接与文档所有权门禁未接入生产校验入口 | High | correctness | root-cause | process-gap | fixed | validate_spec_lifecycle 调用 check_docs_links 与 check_ownership_index | `tests/unit/test_spec_lifecycle.py::test_entry_level_dead_link_rejected`; `::test_entry_level_dir_as_file_rejected`; `::test_ownership_index_missing_fails`; `::test_ownership_index_broken_link_fails` | 1 | 1 | test-simulates-itself |
| STRUCT-C002 | 版本级生命周期与 release 收口规则未执行 | High | correctness | root-cause | process-gap | fixed | 新增 validate_versions：版本 done 强制关联 release/closed_at/全部里程碑 done | `tests/unit/test_spec_lifecycle.py::test_version_done_without_release_fails`; `::test_version_done_release_without_closed_at_fails`; `::test_version_done_with_pending_milestone_fails`; `::test_version_done_valid_closes_clean` | 1 | 1 | marked-done-not-implemented |
| prereq-cycle-false-positive | 环检测对菱形依赖误报 | Medium | correctness | root-cause | original-coding | fixed | 三色 DFS 只判当前路径回边 | `tests/unit/test_spec_lifecycle.py::test_prereq_diamond_not_flagged_as_cycle` | 1 | 1 | — |
| tasks-status-uniqueness-skipped | gate-0 里程碑 tasks 状态不被检查 | Medium | correctness | root-cause | original-coding | fixed | 独立检查 design 与 tasks，不以 design 存在为前置 | `tests/unit/test_spec_lifecycle.py::test_tasks_status_uniqueness_without_design` | 1 | 1 | — |
| dup-id-info-lost | 重复 ID 覆盖丢失首个信息 | Low | quality | root-cause | original-coding | fixed | 保留首个条目，重复追加 __dups__ | `tests/unit/test_spec_lifecycle.py::test_dup_id_preserves_dups` | 1 | 1 | — |
| section-substring-match | 章节子串匹配误匹配 | Low | quality | root-cause | original-coding | fixed | 精确匹配顶层标题 | `tests/unit/test_spec_lifecycle.py` test_gate1_* | 1 | 1 | — |
| STRUCT-D001 | releases 目录未纳入 Git 且链接指向目录 | Medium | correctness | root-cause | process-gap | fixed | 新增 releases/README.md 索引，链接改到该文件 | `tests/unit/test_spec_lifecycle.py::test_entry_level_dir_as_file_rejected` | 1 | 1 | marked-done-not-implemented |
| STRUCT-D002 | 改造方案顶部仍称 M030 待确认 | Low | quality | root-cause | spec-drift | fixed | 顶部状态同步为 M030 已完成 | — | 1 | 1 | cross-feature-contract-drift |
| STRUCT-C003 | round-1 修复遗留死代码（seen dict 永不触发） | Low | quality | symptom | fix-regression | fixed | 移除永不触发的 seen 逻辑 | `tests/unit/test_spec_lifecycle.py::test_dup_id_preserves_dups` | 2 | 2 | — |

**模式性教训**: 两个 High 都属于 `marked-done-not-implemented`/`test-simulates-itself`——
把校验函数"写出来"却"没接进生产入口"，CLI 还输出"链接校验通过"，绿灯成了假阳性。
这类缺陷只有"入口级接线测试"能抓住（只测孤立纯函数永远发现不了函数从未被调用）。
来源分布为 `process-gap` 4、`original-coding` 4、`fix-regression` 1、`spec-drift` 1；
round-1 修复自身引入 1 条死代码（STRUCT-C003），被第 2 轮 diff-only 复核发现，印证了
"修复自伤率每轮 20-30%"——1 轮就宣布闭环是假闭环。
