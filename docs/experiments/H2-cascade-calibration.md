# H2 `liquidation_cascade` 家族校准

**证据 ID**：`H2-cascade-calibration-v1`
**状态**：`ACTIVE_CALIBRATION`
**证据类别**：配对模拟实测校准；不是 H2 正式结论
**日期**：2026-09-06
**机器结果**：[`H2-cascade-calibration.json`](H2-cascade-calibration.json)

## 1. 为什么单独校准

[`H2-endpoint-calibration`](H2-endpoint-calibration.md) 用的是 v0.1.5 已有证据，而 v0.1.5 的三个
家族是 crash / surge / liquidity_drought——**没有强平连锁**。所以那份校准把
`liquidation_cascade` 的 SESOI 记为 `null`，而不是借用另两个家族的值。本文用两个冻结策略在
v0.1.5 的冻结运行参数上真跑 256 个配对 seed block 补上这一格。

## 2. SESOI 与样本量

| 项 | 值 |
|---|---|
| 配对 block | 256（HH 制度格） |
| 严重程度指标 | 单个 `chain_id` 下被强平的最大账户数 |
| 配对差非零 block | 128 / 256 |
| 配对差均值 | `-1.000`（threshold 相对 linear 更少连锁） |
| **实测配对 SD** | **`1.0020`** |
| **SESOI（0.25 SD）** | **`0.25049`** |
| **所需 block** | **168** |

三个家族的所需 block 因此一致为 **168**，`AI_FORMAL` 轨的最终 block 数取 **168**。

## 3. 三个必须随结论一起说明的事实

**（1）只有 HH 制度格会发生强平。** 4 个制度格各跑 64 次：

| 格 | 杠杆 | `maint_bp` | 有强平的运行 |
|---|---|---:|---:|
| LL | 低 | 300 | 0 / 64 |
| LH | 低 | 1200 | 0 / 64 |
| HL | 高 | 300 | 0 / 64 |
| **HH** | **高** | **1200** | **14 / 64** |

本 SESOI 只适用于包含 HH 格的场景分布。若 H2 的正式场景分布不含 HH，这个家族根本没有数据。

**（2）spec 当前的发生条件在本模型族里不可满足。** spec 把 `liquidation_cascade` 的发生条件
写作「同一 `chain_id` 至少两个不同账户 **且** `max(chain_depth) >= 1`」。实测 256 个配对 block
中，**观察到的 `chain_depth` 只有 `0`**。按
[`event-schema`](../contracts/event-schema.md)，`chain_depth = 0` 的定义就是「非连锁触发」，
因此该条件恒为假，发生指标的配对差全部为 0——**与另外两个家族的发生指标一样退化**，同样
不得作为主要 estimand。

**（3）本模型族从未观察到真正的连锁传导。** 既然所有 `chain_depth` 都是 0，`chain_size >= 2`
只表示「同一批判定里有两个账户被强平」，不是「A 的强平导致了 B 的强平」。因此本文的严重程度
指标必须如实读作**「一次强平判定牵连的账户数」**，报告中不得表述为连锁深度或传导强度。若 H2
要在结论里使用「强平连锁」这个词，必须同时声明：在当前冻结模型族与参数范围内，未观察到任何
深度 ≥1 的连锁传导。

## 4. 可复现性

```powershell
python tools/h2_cascade_calibration.py
python tools/h2_cascade_calibration.py --check docs/experiments/H2-cascade-calibration.json
python -m pytest tests/unit/test_h2_cascade_calibration.py -q
```

完整重跑约 65 秒（256 配对 block + 4 格探针）。

## 5. 本证据不能替代什么

它只覆盖 v0.1.5 冻结的运行参数、两个冻结策略与 HH 制度格。H2 若改变市场参数、代理构成或
场景分布，必须重跑本校准。它也不预测 H2 的正式结果——只确定该家族的严重程度终点**有方差、
可被检验**，以及发生指标不可用。
