---
kind: milestone
id: 0.4.3
parent: v0.4-market-ecology
version: "0.4"
doc_kind: design
gate_version: 1
created: 2026-09-25
updated: 2026-10-04
---

# 0.4.3：外生价格锚 - 设计

> Owner: qiaozhi li | Spec: `spec.md`

## 0. 输入与约束

- 行为真相源：[`spec.md`](spec.md)。判据、门限与口径全部引自
  [`0.4.1 spec §6`](../0.4.1-ai-market-ecology/spec.md#6-成功与验收)，本里程碑不重新定义。
- L1 合同不可改；`ADR-011` §决策 2 已由 `ADR-017` 修订（只许可恒定外生参照）；`ADR-016` §4.1 的两条强度前置必须满足。
- `TraderStrategy` 协议与分级信息集不改，`PROTOCOL_VERSION` 保持 1（spec `IR-701`）。

## 1. 技术概要与影响面

新增一个恒定外生参照与一个消费它的策略族，全部落在 L2 策略层与装配层内。不改撮合、
账本、保证金、强平、事件 schema 与策略协议，因此可沿用
[`ADR-015`](../../../decisions/015-rebind-frozen-evidence-after-bookkeeping-fix.md)
的经济等价证明机制处理冻结证据。

影响面：

- `agent/strategy_layer/families/` 新增 `value_investor` 族；
- `experiment/roster.py`：`_FAMILIES` 新增该族与参数校验；族 builder 需要读到
  `engine.initial_price_ticks`（现有 builder 签名为 `(agent_id, family, ordinal)`，不含
  engine，`build_agent_specs` 须为该族传入）；装配时断言 `engine.mult == DEFAULT_MULT`（T1100）；
- `agent/strategy_layer/families/_common.py`：量纲修正与量级哨兵（T1100/T1104）；
- `metrics/`：单调性扫描组件（新建）、预注册文件读取与哈希校验（新建）；
- 质量报告：锚过强诊断字段与终点判定字段。

## 2. 架构与模块边界

**`v_t` 是派生量，不是新状态**：`v_t ≡ engine.initial_price_ticks`。它由 roster 的 engine
块唯一决定，因此已被 `roster_id` 覆盖（derives-don't-store），不需要随机源，也不需要
新的运行头块。

**下发通道**：价值族 builder 把 `v_t` 写进该族代理的 `AgentSpec.strategy_private`
（`{"value_reference_ticks": v_t}`），运行时经 `handler.py` 并入 `model_private_state`，
族实现从这里读取——与 `trend_following` 的 `time_scale_index` 是同一条已在用的通道
（`roster.py` `_build_native_trader`、`handler.py` 构造 `AgentInternalStateV1` 处）。
其他族的 builder 不写该键；分级信息集（`protocol.py`）完全不涉及 `v_t`。

**锚的强度不在 `v_t` 里**：`v_t` 恒定，强度由价值族的 `count` 与 `sensitivity_x1000`
决定（spec `FR-702`）；资金不是强度维度（`live_market` 统一 `10**14`）。0.4.1 §14 的
钉死形态对应强度无穷大，是扫描区间的一端。

**响应函数**（`T1106` 实现，形式可在 binding/单调性失败时更换，见 §7）：

```text
dev_bp      = (price − v_t) × 10000 / v_t
fraction    = min(1000, sensitivity_x1000 × |dev_bp| / 100) / 1000
target      = −sign(dev_bp) × trunc(fraction × max_position_units)
```

## 3. 数据模型与 Migration

- **roster**：新增族条目 `value_investor`（`count`、`observe_interval_ns`、`latency_ns`、
  `params.sensitivity_x1000` 等），沿用既有 `FAMILY_KEYS` 结构；**不新增顶层键**，
  `TOP_LEVEL_KEYS` 与既有 roster 的 `roster_id` 不变。
- **`ExperimentConfig` 的 `config_hash`**：价值族代理的 `strategy_private` 非空，按
  `config.py` 既有规则进入哈希；不含价值族的既有配置哈希不变。
- **质量报告**：新增锚过强诊断块与终点判定字段（`QUALIFIED` / `UNQUALIFIED` / 未完成），
  缺省时既有报告结构不变。
- **预注册文件**：强度网格、种子集合与两条扫描筛选判据（含分段口径，spec `SC-704`），单文件、先提交后扫描；扫描记录写入
  其内容哈希（`AC-708`）。

## 4. 接口、Contract 与 Event

- **不新增事件类型、不改策略协议**。价值族的决策写进既有 `AGENT_DECIDE` 的
  `internal_state`，与 0.4.1 的四个族一致（TR-501）；`goal_model_version` 不变。
- `v_t` 是装配期常量，不随逻辑时刻求值。

## 5. Runtime、Workflow 与并发

装配与推进沿用 0.4.1 的 `LiveMarket.advance()` 结构，不改推进语义。强度扫描是对同一入口
按预注册网格逐格调用，不新建实验框架；不需要「关闭价值族」的对照运行（spec US-702 注）。

## 6. UI 与可观测性

本里程碑不改 Web 终端，人类观察面不出现 `v_t`（spec `IR-701`）。`v_t` 与市价的偏离、
锚过强诊断字段随质量报告落盘。

## 7. 失败、恢复、安全与兼容

- **锚过强**（价格被钉死）：0.4.1 §14 实测过该形态——价格 1.6 小时只走 0.55%、波动
  聚集翻 FAIL、趋势族主动成交仅 4 笔。以诊断字段在报告顶部如实呈现；**判定只由
  SC-701/SC-702 决定**，不另设异质性否决（ADR-016 裁决 B）。
- **强度参数名存实亡**：按 ADR-016 §4.1 的两种形态（不 binding / binding 但不单调）
  分别有断言，命中即 fail closed，须更换 §2 的响应函数形式（最多两种，见 §9 残余风险 2）。
- **合约乘数不一致**：`engine.mult != DEFAULT_MULT` 时装配 fail closed（T1100）。
- **量级哨兵**：族层仓位上限隐含杠杆超 100 倍即 fail closed（T1104）。
- **预注册被绕过**：扫描入口在预注册文件缺失或哈希不符时 fail closed（`AC-708`）。

## 8. 测试策略与验收映射

| AC | 验证路径 |
|---|---|
| AC-701 | `v_t` 派生值与恒定性正反断言（`tests/unit/agent/test_value_reference.py`） |
| AC-702 | 价值族单调性单元测试 + `sensitivity_x1000` 的 binding 与单调性、`count` 的单调性实测 + 量级哨兵正反与变异验证 |
| AC-704 | 达标与未达标两条终点的门禁测试（`tests/integration/test_anchored_quality_gate.py`） |
| AC-705 | 锚过强诊断字段存在且不改判定的正反测试 |
| AC-706 | `v_t` 只在价值族私有参数中、协议版本不变、人类载荷不含的正反测试 |
| AC-707 | 锚定市场全窗口不发散、窗口末有成交、同种子复现（`tests/integration/test_anchored_market.py`） |
| AC-708 | 预注册文件缺失/哈希不符时扫描拒绝的正反测试 |

`AC-703` 随原 `FR-703` 撤销，编号不复用。

## 9. 已确认决策与残余风险

- 已确认：不使用实盘数据；不改 L1；不改策略协议；判据一字不改地承接自 0.4.1。
- **残余风险 1**：「钉死」与「发散」之间的窗口可能很窄或不存在；判据已在 spec `SC-704`
  预注册，未找到即按 `UNQUALIFIED` 收口，不得事后加格或改判据。
- **残余风险 2**（2026-10-04 更新）：强度挂载点已由 spec Q-703 定为价值族的响应函数，
  不挂任何容量约束。剩余风险是该响应函数在实测中被证明不 binding 或不单调——按
  ADR-016 §4.1 fail closed，须换响应函数形式，不得保留名存实亡的参数；最多两种形式，
  第二种实测前预注册，两种都失败即 `UNQUALIFIED`（spec §5）。
- **残余风险 3**（2026-10-04 已兑现）：`T1100` 修正后仓位上限收紧约 1000 倍，全窗口实测
  无锚基线由约 2700 秒停摆提前到约 2000 秒（0.4.1 报告 §21）。owner 裁决照修、如实记录、
  不调族参数。对本里程碑的含义：价值族要撑住的是一个**更快发散**的基线，强度扫描（T1111）
  的网格须覆盖这一点。

## 10. 待确认设计问题

- [x] DQ-701: `v_t` 进哪个信息层？— **owner 裁决（2026-10-04）：不进 I0—I3，只对价值族可见。** 落地路径在文档检视后由「协议正交字段」改为「逐代理私有参数通道」，裁决意图不变、协议零改动，理由见 spec Q-702。
- [x] DQ-702: 对照轮是否进 evidence index？— **owner 裁决（2026-10-04）：不进。** 同日稍后 owner 撤销了「关闭价值族」对照要求（spec US-702 注），本问题随之失去对象；扫描产物同样不进 evidence index，与 0.4.1 NFR-503 一致。
