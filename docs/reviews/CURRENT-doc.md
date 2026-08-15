---
report_type: doc-review
round: 2
date: 2026-08-15
prior_report: "round 1（commit 33a548c 之前的未提交版本，已随本轮一并提交）"
scope: diff-only
stop_condition_met: true
severity_counts: {critical: 0, high: 0, medium: 0, low: 0}
issues:
  - id: R017-D001
    title: T201 的目标/约束数学合同、V1 Schema 与运行族字段矩阵尚未冻结
    severity: high
    category: correctness
    root_cause: root-cause
    origin: process-gap
    pattern_tag: contract-name-without-semantics
    status: fixed
    fix_summary: "design §4 新增「T201 必须冻结的清单」5 组（目标模型数学/退化输入行为/约束边界/四个 V1 Schema/三族逐字段 allow-deny 矩阵），要求产出可被参数化测试消费的 golden vector；T201 任务描述指向该清单"
    regression_test: "待补：T201 落地时的 golden vector 与 allow/deny 矩阵参数化测试"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/design.md:58
    first_seen_round: 1
    resolved_round: 1
  - id: R017-D002
    title: T202 预注册不存在，2 × 2 的估计量、样本量与停止规则尚未冻结
    severity: high
    category: test-coverage
    root_cause: root-cause
    origin: process-gap
    pattern_tag: implementation-before-preregistration
    status: fixed
    fix_summary: "experiment-template.md 预注册段新增制度因子实验必填清单 8 项；T202 改为逐项填满并明确冻结前不得开始 T213 与正式运行"
    regression_test: "待补：T202 落地时的预注册字段完整性校验"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/tasks.md:26
    first_seen_round: 1
    resolved_round: 1
  - id: R017-D003
    title: 游标在消费前推进，异常重试会跳过尚未消费的公开事件
    severity: high
    category: correctness
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: cursor-commit-before-consume
    status: fixed
    fix_summary: "design §5 改为四步显式顺序（读游标→消费 (last_seen, current]→写证据→全部提交成功后才原子推进），写明失败回滚与幂等要求；FR-022 与 AC-002 补行为约束与故障注入验收；T206 明确要写该测试"
    regression_test: "待补（T206）：消费中途失败后重试不丢事件、不重复写证据的故障注入测试"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/design.md:71
    first_seen_round: 1
    resolved_round: 1
  - id: R017-D004
    title: T220 先推进 done/established，随后才执行 T221，必然违反 gate v1 的 done 门
    severity: high
    category: correctness
    root_cause: root-cause
    origin: process-gap
    pattern_tag: lifecycle-transition-before-final-task
    status: fixed
    fix_summary: "R5 成果门提到 T220、状态回写降为 T221 并要求全部勾完后同批回写；新增 validate_status_writeback_is_last 门禁防复发"
    regression_test: "tests/unit/test_spec_lifecycle.py::test_status_writeback_before_other_tasks_is_rejected[5 种措辞]、::test_status_writeback_as_final_task_passes"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/tasks.md:70
    first_seen_round: 1
    resolved_round: 1
  - id: R017-D005
    title: R5 要求 README 链接代表性回放，但回放只落被忽略目录且单命令要求没有验收锁定
    severity: high
    category: test-coverage
    root_cause: root-cause
    origin: spec-drift
    pattern_tag: delivery-artifact-not-ci-reachable
    status: fixed
    fix_summary: "R5 四类产物固定为 docs/experiments/ 下已提交路径（报告/限制说明/evidence index/代表性回放，回放 ≤5 MB 并降采样标注）；R1—R4 仍留 artifacts/ 由 RUN.md 重建；AC-012 与 T220 改为 clean checkout 断言"
    regression_test: "待补（T220）：clean checkout 中 README 两跳可达且链接全部有效的集成测试"
    location: docs/features/0.1/0.1.5-goal-driven-flagship/design.md:83
    first_seen_round: 1
    resolved_round: 1
---

# 0.1.5 进入开发前终检

**结论：5 条 High 全部关闭，可进入开发。** round 1 由另一份会话完成全量扫描并给出
5 条 High；本轮（round 2）先逐条独立复核——**不照单全收**——再修复，最后对新门禁做
变异探测。5 条全部复核为真，无误报。

## 发现

| ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R017-D001 | T201 的目标/约束数学合同、V1 Schema 与运行族字段矩阵尚未冻结 | High | correctness | root-cause | process-gap | fixed | design §4 新增「T201 必须冻结的清单」5 组，要求产出可被参数化测试消费的 golden vector | 待补（T201 落地时） | 1 | 1 | contract-name-without-semantics |
| R017-D002 | T202 预注册不存在，2×2 的估计量、样本量与停止规则尚未冻结 | High | test-coverage | root-cause | process-gap | fixed | 预注册模板新增制度因子实验必填清单 8 项；T202 逐项填满，冻结前不得开始 T213 与正式运行 | 待补（T202 落地时） | 1 | 1 | implementation-before-preregistration |
| R017-D003 | 游标在消费前推进，异常重试会跳过尚未消费的公开事件 | High | correctness | root-cause | spec-drift | fixed | design §5 改为先消费后原子推进的四步顺序，写明回滚与幂等；FR-022/AC-002/T206 同步 | 待补（T206 故障注入） | 1 | 1 | cursor-commit-before-consume |
| R017-D004 | T220 先推进 done/established，随后才执行 T221，必然违反 gate v1 的 done 门 | High | correctness | root-cause | process-gap | fixed | R5 提到 T220、状态回写降为 T221；新增 `validate_status_writeback_is_last` 门禁 | `test_status_writeback_before_other_tasks_is_rejected`（5 种措辞）、`..._as_final_task_passes` | 1 | 1 | lifecycle-transition-before-final-task |
| R017-D005 | R5 要求 README 链接代表性回放，但回放只落被忽略目录 | High | test-coverage | root-cause | spec-drift | fixed | R5 四类产物固定为 `docs/experiments/` 下已提交路径（回放 ≤5 MB）；AC-012/T220 改为 clean checkout 断言 | 待补（T220 集成测试） | 1 | 1 | delivery-artifact-not-ci-reachable |
| R017-D006 | 状态回写门禁只认一种措辞，"标记为 done" 可无声绕过 | Medium | correctness | root-cause | fix-regression | fixed | 正则扩为推进/标记/转为/改为/置为/切换到 六类动词 | 同 D004 的参数化测试（新增 3 种措辞） | 2 | 2 | — |

## round 2 复核记录（diff-only）

**逐条独立复核结论**（复核在修复之前做，避免"报告说是就是"）：

- **D004 确认**：`tasks.md` 里 T220 写"推进 `done / established`"、T221 是 R5 成果门，
  而 gate v1 的 done 要求全部任务勾完——死锁成立。顺带说明这是我在循环 9 重排任务时
  保留下来的既有顺序，不是本次新引入。
- **D003 确认**：design §5 原文"先按事件 ID 推进该代理游标，再消费区间内公开成交"
  与 `agent-strategy.md:46`"消费完成后才原子推进"逐字冲突。
- **D005 确认**：`.gitignore` 含 `artifacts/`，而 AC-012 要求 README 两跳到达回放。
- **D001/D002 确认但降级处理**：两条指出的是"实现者必须自行发明"，修复方式不是替
  用户把数学和样本量定下来（那是研究设计决策），而是把**必须决定什么**显式列成清单，
  让 T201/T202 有可判定的完成标准。

**变异探测发现 D006**：新写的 `validate_status_writeback_is_last` 只认"推进"一词，
喂入"把里程碑标记为 done"直接漏检。已扩为六类动词并把三种漏检措辞加进参数化测试。

**图谱**：本轮改动 4 个 Markdown + 1 个校验器函数，`detect_changes_tool` 报 0 个受
影响流程；校验器侧的覆盖由 111 passed 的生命周期测试锁定。

## 停止条件评估

| 条件 | 状态 |
|---|---|
| Critical/High 清零 | ✅ 5 条 High 全部 fixed，round 2 新增的 D006 当轮关闭 |
| 本地 `python tools/verify.py` 全绿 | ✅（一次例外：33a548c 提交时 ruff 红，当场发现并 amend 修正） |
| 最少 2 轮，第 2 轮 diff-only | ✅ round 1 全量（他人会话）+ round 2 diff-only 变异探测 |
| CI 最终门禁跑绿 | 待触发（本轮为收敛候选轮） |
