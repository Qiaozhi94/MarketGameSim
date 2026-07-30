# Code Review Report

**Reviewed**: commit `fbf30cd`（产品、规格、ADR、实验协议、事件 Schema 与性能基准文档）  
**Language(s)**: Markdown, YAML, TOML, JSON schema conventions  
**Review Date**: 2026-07-31  
**Severity Legend**: 🔴 Critical | 🟠 High | 🟡 Medium | 🟢 Low | 🔵 Info  
**处置状态**: 8 项已全部关闭（2026-07-31），见下「处置结论」

## 处置结论（2026-07-31）

8 项复核后全部成立。其中 2 项在 `343f7a8` 已随上一轮复查关闭，其余 6 项在本次
处置。

| 编号 | 处置 |
|---|---|
| 🟠 EXP-000 family 与实际 p 值数不一致 | 重写主要指标表：**每个参数点恰好 4 个 p 值**，每项检验先在种子内压缩为一个标量再跨种子检验，逐 lag 检验不进入判定。检验 3、4 改为**等价性检验**（TOST 形式，冻结 ε = δ = 0.05，X-005）——原写法把「未能拒绝」当作「无效应」的证据，功效越低越容易通过，与实验目的相反。「有效样本率」明确为前置门槛，不产生 p 值 |
| 🟠 KPI-007 账户链无法验证 | 采纳方案 B：`TRADE_SETTLE` 内嵌 `postings`（每笔成交两条分录，含 delta、结算后余额与持仓成本，§4.2.1）；`ORDER_ARRIVAL` 携带 `reserved_cash_delta_units`。**每次账户变动都由引发它的事件承载**，`priority_class` 冻结清单不受影响；SNAPSHOT 退回回放与交叉核对用途；SC-008、FR-004 同步 |
| 🟠 EXP-000 固定条件与中心点选点 | 新增「固定条件（X-006）」逐项冻结表（代理构成 200 个、资金/持仓/频率/延迟/费率/种子生成规则全部写值）；中心点冻结为确定性算法 X-007（4-邻接最大连通分量 → 距失败边界最远 → 字典序）；并说明代理总数取 200 是为使 `lag*` 落在可计算范围 |
| 🟡 BENCH-001 YAML 浮点 | 已于 `343f7a8` 关闭 |
| 🟡 `target_order_id` 哈希口径矛盾 | 已于 `343f7a8` 关闭（统一为纳入） |
| 🟡 费用「单调非负」表述过强 | 采纳方案 A：累计费用改为**有符号量**，守恒等式对负值同样成立；不冻结 `maker_bps + taker_bps ≥ 0`（那会拒绝合法的补贴型费率实验），改为要求配置校验标注补贴型实验并在报告中声明 |
| 🟡 Canonical JSON 不唯一 | 冻结 UTF-8 / NFC / `ensure_ascii=false` / `sort_keys` / `separators=(",", ":")` / 无 BOM / 每事件一个 LF，并声明等价于 RFC 8785 JCS；补充**哈希与文件存储解耦**（在语义字段的规范编码上计算，转存日志不改变哈希） |
| 🟢 ADR-006 编号不一致 | SC-007 → SC-008 已于 `343f7a8` 修正；本次补修 T013 → T013b |

**顺带关闭**：上一轮自查提出的 R-005（`lag*` 检查范围写窄，高 τ 参数点会整片
「不适用」）——ACF 可计算范围扩至 lag 1—250，并与检验 3 的 lag 1—20 明确分工。

**仍未关闭**：T000i 本身（评审并冻结，001 规格转 Approved）。X-006 的固定条件表是
**提案值**，须在 T000i 评审时确认；其中代理构成对 λ 的影响须在首次试运行后核对
实测值，若 `lag*` 越界则调整 X-006 或 X-001 并重新评审。

---

## Executive Summary

上轮 8 项发现中，Q-009、NaN/JSONL 冲突、零延迟调度、M2/M3 KPI 错位、本机权限文件
忽略规则等已经关闭；数值合同、因果外键和 EXP-000 也有显著进展。但目前仍有 3 项会
阻止协议冻结：统计检验的 p 值 family 与实际检验数不一致、账户链并未真正进入因果
Schema、EXP-000 的固定配置与 σ 子实验选点仍留有运行后裁量空间。

建议修复 3 项 High 后再执行 T000i。其余问题主要是新增 ADR 之间的精确口径冲突，
修改量不大，但应在进入实现前统一。

## Findings

### Correctness / Research Validity

#### 🟠 EXP-000 的多重检验 family 与实际产生的 p 值数量不一致 — `docs/experiments/EXP-000-baseline-validation.md:90-129`

**Severity**: High

**Problem**: 文档声明每个参数点只有 4 项主要指标检验，因此主扫描为 `36 × 4 = 144`
个 p 值；但实际规则会产生至少 1 个峰度 p 值、5 个绝对收益 ACF p 值和 20 个收益 ACF
p 值，“τ 周期峰”还没有定义如何形成单个 p 值。当前实现无法唯一确定哪些 p 值进入
BH 校正。另一个问题是“lag 1—20 无显著非零”只能表示未拒绝零假设，不能为“确实近似
于零”提供证据；低统计功效也会被判为通过。

**Current Code**:

```text
| 绝对收益自相关 | ... | lag 1—5 中至少 3 个 ... 显著为正 |
| 收益自相关 | ... | lag 1—20 无显著非零 |

主扫描全部 36 个参数点 × 4 项主要指标检验 = 144 个 p 值
```

**Suggested Fix**:

```text
先为每个参数点定义恰好一个峰度检验、一个波动聚集联合检验、
一个收益自相关等价性检验、一个 τ 周期峰检验。

若保留逐 lag 检验，则按真实 p 值总数定义 family，并说明层级校正顺序。
“无自相关”使用预先冻结的等价界 ε 与 TOST/置信区间判据，
而不是以 p > 0.05 作为通过。
```

**Explanation**: 预注册的核心价值是让同一份结果只能得到一个判定。当前文本对 p 值
数量、周期峰显著性和“无效应”判据仍存在多种合法实现，运行后会产生分析自由度。

---

#### 🟠 KPI-007 的账户链仍无法由日志因果外键验证 — `specs/001-market-simulation-foundation/event-schema.md:165-195`

**Severity**: High

**Problem**: 文档声称账户变化可通过 `trade_id` 与后续 `ACCOUNT SNAPSHOT` 关联，但
`SNAPSHOT` 被明确规定不带因果外键，Schema 也没有账户变更事件、快照覆盖的 trade
范围、成交前后余额或 `trade_id`。周期快照可能聚合多笔成交，因此无法从单笔成交唯一
追溯其账户变化。这与 KPI-007 的“完整决策和账户链路”以及 SC-008 的“每一跳唯一存在”
冲突。

**Current Code**:

```text
SNAPSHOT ... 不携带因果外键。

账户变化经 trade_id 与其后的 SNAPSHOT（ACCOUNT）关联，构成完整链条。
```

**Suggested Fix**:

```text
方案 A（推荐）：新增 ACCOUNT_UPDATE / LEDGER_POSTING 事件，
字段至少包含 trade_id、agent_id、cash_delta、position_delta、
fee_delta、balance_after，并让 TRADE_SETTLE 与两侧分录显式互引。

方案 B：在 TRADE_SETTLE 中记录双方结算前后账户状态，
并将其纳入 SC-008 的完整性检查。
```

**Explanation**: “时间上位于成交之后的快照”不是因果关联。只有单笔分录或成交内嵌的
前后状态才能证明该成交如何改变账户，同时仍允许周期快照服务于回放和图表。

---

#### 🟠 EXP-000 仍未完全冻结固定条件和 σ 子实验选点 — `docs/experiments/EXP-000-baseline-validation.md:12-15,31-58`

**Severity**: High

**Problem**: 协议只列出了“费率、初始价格、代理总数、初始资金与持仓分布、观察频率与
延迟”等固定条件类别，没有冻结具体值，却把机器配置留到 T014b 才生成。协议无法约束
未来配置具体采用什么值。“可用区中心点”也没有数学定义；当可用区不规则、离散、多连通
或存在多个等距候选点时，研究者可以在看过结果后选择对子实验最有利的点。

**Current Code**:

```text
运行前须由本文生成 experiments/EXP-000.yaml（T014b）

固定条件：市场制度、费率、初始价格、代理总数、...

在主扫描确定的可用区中心点上...
```

**Suggested Fix**:

```text
在 M0 冻结时一并提交 experiments/EXP-000.yaml，
或在协议中逐项写出全部固定值和种子生成规则。

中心点选择冻结为确定算法，例如：
1. 对通过点构造 4 邻接连通分量；
2. 选择点数最多的分量；
3. 选择到失败边界曼哈顿距离最大的点；
4. 并列时按 τ 较小、p_trend 较小的字典序裁决。
```

**Explanation**: 配置可以在实现后生成，但其所有研究相关值必须已由预注册协议唯一决定；
否则“配置哈希”只能证明运行了哪个配置，不能证明配置不是看过中间结果后选的。

### Cross-document Consistency

#### 🟡 BENCH-001 的十进制 YAML 值违反 ADR-005 的字符串解析合同 — `benchmarks/BENCH-001.yaml:27-35,42-74`

**Severity**: Medium

**Problem**: ADR-005 要求所有十进制配置“以字符串形式读取后用 `Decimal` 解析，禁止经过
float 中转”，但 BENCH-001 中 `0.01`、`0.001`、`-1.0`、`5.0`、初始现金和持仓均是
未加引号的 YAML 数值。使用当前 PyYAML `safe_load` 验证时，这些字段实际被解析为
Python `float`。

**Current Code**:

```yaml
tick_size: 0.01
min_quantity: 0.001
fees:
  maker_bps: -1.0
  taker_bps: 5.0
initial_price: 100.00
```

**Suggested Fix**:

```yaml
tick_size: "0.01"
min_quantity: "0.001"
cash_unit: "1e-8"
fees:
  maker_bps: "-1.0"
  taker_bps: "5.0"
initial_price: "100.00"
```

对所有金额、持仓、数量和离散度十进制字段采用同一规则，并在配置校验测试中断言其输入
类型为字符串。

**Explanation**: 只在单位换算阶段使用 `Decimal(str(float_value))` 不能恢复 YAML
解析时已经丢失的原始十进制表示。

---

#### 🟡 `target_order_id` 是否参与摘要哈希在 ADR 与 Schema 中相互矛盾 — `docs/adr/006-same-timestamp-event-scheduling.md:110-115`

**Severity**: Medium

**Problem**: ADR-006 把 `target_order_id` 与其他因果外键一起排除在摘要哈希之外；事件
Schema E-002 则明确把它纳入，理由是“撤销哪一笔订单是外部可观察行为”。实现无法同时
满足两份 Accepted/Draft 合同。

**Current Code**:

```text
ADR-006：target_order_id ... 排除在哈希之外
event-schema：target_order_id ... 不可排除
```

**Suggested Fix**:

```text
采用 event-schema 的口径：纳入 target_order_id。
它标识撤单的市场语义对象，不只是事件生成方式的实现细节。
仅排除 observation_event_id、decision_event_id、intent_id、
caused_by_event_id 等纯因果定位键。
```

**Explanation**: 两次运行若撤销了不同订单，即使其他字段相同，也应产生不同的市场结果
哈希。

---

#### 🟡 手续费舍入不能保证交易所累计费用单调且非负 — `docs/adr/005-numeric-and-serialization-contract.md:60-76`

**Severity**: Medium

**Problem**: 向不利于代理方向舍入只能保证舍入余数有利于交易所，不能保证交易所净费用
单调不减或非负。maker 返佣是负费用；若可配置的返佣绝对值大于 taker 收费，单笔成交
就会降低累计费用。当前 BENCH-001 的 `-1 / +5 bps` 恰好净正，但 FR-003 允许配置费率，
文档未冻结 `taker_fee + maker_fee ≥ 0`。

**Current Code**:

```text
该方向保证「交易所累计费用」单调不减且非负
```

**Suggested Fix**:

```text
选择其一：
A. 删除“单调不减且非负”要求，把累计费用定义为可为负的有符号净费用；
B. 增加配置约束：对任意成交 maker_bps + taker_bps ≥ 0，
   并处理双方舍入后仍可能出现的最小单位边界。
```

**Explanation**: 现金守恒只要求交易所费用账户按实际有符号费用记账，并不要求它非负。
把非负性误当成守恒前提会拒绝合法的补贴型费率实验，或产生错误断言。

---

#### 🟡 Canonical JSON 规则不足以产生唯一字节流 — `docs/adr/005-numeric-and-serialization-contract.md:108-118`

**Severity**: Medium

**Problem**: 当前只冻结了整数、null 和键排序，没有冻结 UTF-8 编码、Unicode 转义/
正规化、空白与分隔符、换行及布尔值表示。两个合规序列化器仍可分别输出
`{"名称":"值"}` 与 `{"\u540d\u79f0":"\u503c"}`，或使用不同空白，导致对“规范序列化
字节”计算的 KPI-002 哈希不同。

**Current Code**:

```text
对象键按 UTF-8 码位升序排列
```

**Suggested Fix**:

```text
明确采用一种完整 canonicalization：
- 直接引用 RFC 8785 JCS；或
- 冻结 UTF-8、NFC、ensure_ascii=false、sort_keys=true、
  separators=(',', ':')、禁止 BOM、每事件恰好一个 LF。

更稳妥的是哈希语义字段编码，而日志换行格式只用于存储。
```

**Explanation**: “排序后的对象”不等于唯一字节表示；KPI-002 若跨 Python 版本或其他
工具读取/重写日志，差异会暴露。

---

#### 🟢 ADR-006 的验收编号与正式规格不一致 — `docs/adr/006-same-timestamp-event-scheduling.md:90,149-158`

**Severity**: Low

**Problem**: ADR-006 §4 标题写“SC-007”，但正式规格把数值守恒定义为 SC-007、因果链
定义为 SC-008。ADR 后面的同步清单已经使用 SC-008；后续行动又写进入 T013，而任务表
实际新增的是 T013b。

**Current Code**:

```text
引用完整性作为验收断言（SC-007）
...进入 T013 的验收范围
```

**Suggested Fix**:

```text
引用完整性作为验收断言（SC-008）
...进入 T013b 的验收范围
```

**Explanation**: 这是小型文档错误，但需求追溯和测试命名高度依赖编号，最好在冻结前
消除。

## Positive Observations

- 上轮 8 项中的 Q-009、NaN/JSONL、零延迟调度、M2 KPI-008、`.claude` 忽略规则已明确
  关闭。
- ADR-005 将价格、数量、现金和费用统一到整数域，方向正确，能够显著降低账本实现风险。
- ADR-006 的严格递增事件键与显式因果外键，使确定性和可审计性从原则进入了可测试合同。
- EXP-000 已补齐 τ 网格、σ 敏感性实验、运行长度、burn-in、bootstrap 次数和种子记录。
- PR-001—PR-019、KPI-001—KPI-012 和规格追溯关系完整；本地 Markdown 链接检查未发现
  失效目标。
- 工作区在审查开始时是干净的，commit `fbf30cd` 已与 `origin/main` 同步。

## Summary

| Severity | Count |
|----------|-------|
| 🔴 Critical | 0 |
| 🟠 High | 3 |
| 🟡 Medium | 4 |
| 🟢 Low | 1 |
| 🔵 Info | 0 |

**Bottom Line**: 这次修改已经关闭了大部分上一轮缺口，但在修正统计检验合同、账户分录
追溯和研究配置冻结方式之前，仍不建议将 001 规格转为 Approved。
