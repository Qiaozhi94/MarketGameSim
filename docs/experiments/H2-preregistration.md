---
kind: experiment-preregistration
id: H2-preregistration-v1
milestone: 0.3.1
status: FROZEN
frozen_at: 2026-09-07
frozen_before: first-H2-formal-sample
contract: H2-dual-track-contract-v1
---

# H2 双轨正式实验预注册

## 1. 研究问题、假设与处理因子的水平取值

在当前合成永续市场的模型族、参数范围与 H2 seed 分布内，替换同一非做市目标插槽的
决策规则，是否改变价格崩盘、流动性枯竭与强平连锁的严重程度？全部主要假设为双侧：
`H0: E[threshold - linear] = 0`，`H1: E[threshold - linear] != 0`。

`AI_FORMAL` 轨的两个水平是冻结的 `risk_budget_linear_v1` 与
`risk_budget_threshold_v1`。`OWNER_N_OF_1` 轨的水平是所有者决策，以及同 seed 的上述两条
`WINDOW_MATCHED_POLICY_CONTROL` 参照；它只作描述性个案记录，不承担研究声明。两轨的
evidence index、样本量与推断不得合并。

目标策略参数沿用 v0.1 冻结值，不为 H2 调参：`risk_appetite` 为每次运行抽取一次的
`int(Uniform[500,20000))`；threshold 策略使用 `theta_in=3000bp`、
`theta_out=1200bp`、`k_x1000=600`。正式场景必须包含高杠杆 + `maint_bp=1200` 的 HH 格。

## 2. 比较矩阵与窗口

两条 AI 策略在账户、初始资金、风险边界、信息集、动作空间、初始价格、seed 与窗口调度上
逐字段相同；允许差异只有策略 ID 与内部目标映射，不声称目标函数对齐。所有条件均使用逻辑
1 秒、每场景 60 窗、每窗最多一次动作、超时 `NO_ACTION` 的调度器；所有者墙钟窗为 8 秒。

## 3. 指标定义与判据

三个结果家族分别报告，不生成综合崩盘分数：

- `price_crash`：主要严重度为 `max_t(max(ln(P0/Pt),0))`。
- `liquidity_dry_up`：主要严重度为最长连续无成交时长占运行总时长比例。
- `liquidation_cascade`：主要严重度为单个 `chain_id` 下被强平的最大账户数；不得使用
  `chain_depth`。同一 `chain_id` 至少涉及两个账户才记为发生。

三个家族的发生率只作描述性结果。机制指标固定为指标字典中的 `H2-M-001` 激进订单、
`H2-M-002` 流动性撤回和 `H2-M-003` 风险减仓；机制只支持关联与时序解释，不作因果中介声明。

## 4. 估计量定义与分析代码

AI 轨以 paired seed block 为单位，主要估计量是每个家族的
`risk_budget_threshold_v1 - risk_budget_linear_v1` 严重程度均值。95% CI 与双侧 p 值使用
block 级 10000 次 bootstrap（seed `0`）；三个严重程度检验用 Holm、`alpha=0.05` 校正。
发生率配对差及其区间保持描述性，不进入 Holm。所有者轨只输出 24 个场景相对两条参照的
差值分布与时间线，不做显著性检验或人群区间。

分析实现冻结为 `src/market_game_sim/experiment/h2/outcomes.py` 与
`src/market_game_sim/experiment/h2/mechanisms.py`；正式 freeze manifest 保存两者 SHA-256。
结论必须同时限定“模型族、参数范围、seed 分布”，并禁用无条件的 human-effect 简称。

## 5. 样本量与功效

三个家族的 SESOI 均冻结为 0.25 SD：`price_crash` 与 `liquidity_dry_up` 为
`4.5969e-3`，`liquidation_cascade` 为 `0.25049`。AI 轨固定取得 168 个完整 paired blocks，
高于校准下限 158；不得因观察到的效应、p 值或区间宽度下调或追加。所有者轨固定 6 个训练
场景和 24 个正式 paired scenarios，分 4 天、每天 6 个，第 3 个后强制休息。

## 6. seed plan、场景顺序与分配

AI 正式 seed 按升序冻结为 `50000..50167`，技术补跑备用 seed 为 `50168..50184`；两池互斥。
每个 AI assignment 同时签发 linear 与 threshold 两臂。所有者 24 个场景的冻结顺序由审计
seed `916301` 在首次正式样本前生成并写入 `assignments.json`。任何补跑只能依冻结备用顺序取
下一项，并保留 `rerun_of_session_id` / `supersedes_pair_id` 审计链。

## 7. 排除、缺失与停止规则

仅协议漂移、技术中止、所有者中止、不完整 pair 或不完整 session 可触发排除；adjudication
不得读取价格、收益、结果或机制字段。任一侧缺失则该家族的 pair 按 complete-case 排除，不作
插补，并报告数量与原因。

AI 轨达到 168 个合格完整 pair 即停止；备用池用尽仍不足则输出 `incomplete-study`，不得分析
或形成研究声明。所有者完成 24 个正式场景即停止；所有者选择中止或资源窗口结束仍不足时也
输出 `incomplete-study`，不得进入 evidence-index 冻结。禁止基于中期结果改变停止决定。

## 8. 多重比较与敏感性边界

唯一主要多重性集合是三个家族各一个严重程度检验，采用 Holm 校正。发生率、三项机制和
所有者结果不进入该集合。交换性假设下的 sign-flip 与包含 scenario/regime 效应的分层结果仅作
敏感性分析；它们不得替代主要配对 bootstrap 结论或扩大研究声明。

## 9. 校准区、正式区与解盲

`H2-endpoint-calibration-v1`、`H2-cascade-calibration-v1` 与
`H2-block-power-baseline-v1` 是首个正式样本前的既有校准区证据，不是 H2 正式结果。
`50000..50184` 是 H2 独占正式/备用区；H1、preview 与 interactive 数据不得升级进入该区。
所有者在 24 个正式场景全部完成前不得查看任何已完成场景结果、配对差或参照策略产出。

## 10. 隐私、保留与冻结性

仓库只保存研究假名 `owner-h2-001`，不采集直接身份、键盘内容、屏幕录制或无关遥测。
正式中止记录为审计保留但不进入结果；发布前运行 PII 扫描与人工复核。冻结归档必须同时保存
本文、最终 `protocol.json`、分配表和分析代码摘要；任一摘要漂移即 fail closed。首个正式样本
后不得原地修改协议，修订必须新建版本并按本停止规则判断是否重启整项研究。
