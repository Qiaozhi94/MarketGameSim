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
