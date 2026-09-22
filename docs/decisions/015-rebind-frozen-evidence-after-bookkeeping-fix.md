# ADR-015：L1 缺陷修复只改变簿记记录时，冻结证据可凭经济等价证明重绑

日期：2026-09-23  
状态：Accepted（owner 裁决，2026-09-23「撤单后不发布行情」修复的证据处置，方案 A）  
关联规格：[`../features/0.4/0.4.1-ai-market-ecology/spec.md`](../features/0.4/0.4.1-ai-market-ecology/spec.md)
（T961 市场质量口径依赖行情发布的完整性）  
关联决策：[`ADR-012`](012-evidence-rebinding-attestation.md)（0.1.5 证据索引重绑盖章）、
[`ADR-013`](013-l1-matching-core-clearing-split.md)（L1a/L1b）  
关联合同：[`../contracts/event-schema.md`](../contracts/event-schema.md) §4.2 推论 3、§4.3  
关联实现：[`../../src/market_game_sim/evidence/economic_projection.py`](../../src/market_game_sim/evidence/economic_projection.py)、
[`../../tools/prove_economic_equivalence.py`](../../tools/prove_economic_equivalence.py)、
[`../../src/market_game_sim/experiment/h2/evidence_index.py`](../../src/market_game_sim/experiment/h2/evidence_index.py)

## 背景

0.4.1 T961 冻结「双边盘口可用率」口径时发现 L1 缺陷：`book/matching.py` 的撤单分支在
`_handle_cancel` 后直接返回，**撤单改变了盘口也不写 `MARKET_DATA_PUBLISH`**，违反事件
Schema §4.2 推论 3。一张撤单把某一侧撤空后，公开记录仍显示双边盘口，直到下一笔挂单。
任何从行情发布计算盘口可用率、档位的指标都会被高估。

修复本身很小，但两份**已签收的正式证据**绑定的是完整事件流摘要：

| 证据 | 绑定方式 | 修复后 |
|---|---|---|
| 0.1.5 T215（`0.1.5-evidence-index.json`） | 全树源码哈希 + 检查点内的事件流 | 源码哈希变化（ADR-012 已有盖章机制） |
| 0.3.1 H2（`H2-ai-evidence-index.json`） | 每个 block/arm 的 `events_sha256` | 336 个摘要全部失配，分析入口按设计拒绝运行 |

H2 冻结 index 没有任何重绑机制，报错原文是「冻结证据不可原地改写；如确需修订，显式移除
旧文件并按预注册修订规则留痕」。预注册 §10 禁止的是「原地修改**协议**」，本次协议哈希、
分配表、样本集合都不变，变化的只是代码产出的簿记记录。

实测（`tools/prove_economic_equivalence.py --baseline 9e514bd --t215 --h2`）：

- T215：1024 个主跑的经济投影与冻结检查点中的事件流**逐一相同**，运行分类、终局价格、
  终止态全部不变；新增 586,805 条行情发布；
- H2：基线 `9e514bd` 复现 336/336 个冻结摘要（证明基线就是产出证据的代码），修复后
  336/336 个 arm 的经济投影与基线相同。

重绑前并行会话合入了 0.4.1 T961/T963/T964/T974（其中 T963 改动 T215 运行路径）。证明在
合并后的代码上重跑一遍，结论不变（T215 1024/1024、H2 336/336），实际重绑用的就是这棵树。

## 决策

1. **「经济投影」是唯一判据，其定义在代码里**：
   `evidence/economic_projection.py` 以**排除清单**而非白名单定义投影——去掉
   `MARKET_DATA_PUBLISH` 记录，以及指向它们的字段（`market_data_event_id`、观察游标、
   `observed_at`、`decision_evidence` 里的游标），其余每条记录的每个字段都参与比较。
   白名单会静默忽略没人想到要列的字段；排除清单让任何意料之外的差异都计数。修改排除
   清单等于修改本 ADR，必须递增 `PROJECTION_VERSION`。
2. **允许重绑的条件（全部满足）**：
   - 改动是对 L1 已有合同的**合规修复**，不是改变合同；
   - 经济等价证明是**全量**的（每个 run/arm 都比较，且全部相同），不是抽样；
   - 基线必须能复现冻结摘要，否则证明无效（基线不是产出证据的代码）；
   - 证明可由仓库内工具在任意时刻重跑（`reproduce` 字段给出命令）。
3. **H2 index 的重绑机制**（`evidence_index.rebind_frozen_index`）：
   - 只有摘要字段（`events_sha256`、`artifact_sha256`）允许变化；重建结果在任何其他
     字段上不同即拒绝——那不是重绑，是重新做实验；
   - 追加一条 `rebind_attestations` 记录：日期、ADR、理由、旧 index 文件的 sha256、
     变化字段、经济等价证明。只追加，不改写历史记录；
   - `load_frozen_index` 对 attestation 做封闭键集与「全量等价」校验，不合格即 fail
     closed，所以分析入口不会接受一份证明不完整的重绑。
4. **T215 按 ADR-012 盖章**，理由引用本 ADR 与同一份证明。
5. **研究声明不变**：两份证据的研究声明、效应量、判定都不因重绑改变。验收条件：重绑后
   H2 正式分析除 `index_binding.sha256`（随 index 必然变化）外逐字节复现已冻结的
   `H2-ai-analysis.json`，由 `analysis.rebind_analysis` 强制——其他任何字段不同即拒绝，
   说明该改动改变了研究结果，不能走本通道。

## 备选方案

- **方案 B：H2 分析门改为比较经济投影摘要**。门禁语义变弱：以后任何非经济字段的漂移
  都看不见，属于安全校验降级。不采纳。
- **方案 C：暂不修，xfail 挂起**。L1 缺陷继续存在，所有下游盘口指标都要各自从事件重建
  订单簿绕开它。不采纳。
- **方案 D：重新执行 H2 正式实验**。经济结果已证明相同，重跑只会得到相同的样本与结论，
  只多付机器时间；且会把「重绑」伪装成「新实验」。不采纳。

## 后果

- 正面：L1 回到合同；冻结证据第一次有了「修簿记不改经济」的正式通道，且它是可重跑、
  可审计、机器强制的；旧摘要可由 `prior_index_sha256` 在 git 历史中找回。
- 负面：新增一类维护对象（经济投影定义）；今后任何改变经济投影的 L1 改动都**不能**走
  本通道，只能重新执行实验。
- 后续行动：
  - ADR-011 背景表里「52.3% 的秒无双边盘口」来自修复前的行情发布，可能偏乐观；
    0.4.1 T967 的首份质量报告应在修复后的代码上重新实测，不沿用该数字；
  - 指标字典 §3.3「有效点差」引用的日志字段 `mid_before_half_ticks` 并不存在（实际字段
    `valuation_mark_before_half_ticks` 单边时退化为 `last × 2`），另行修订；
  - 行情发布的 SUBMIT 路径仍按「簿是否变脏」而非 §4.3 字段是否变化来发布，是反方向的
    偏差（多发不漏发），不影响正确性，另行评估。
