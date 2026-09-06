# H2 `AI_FORMAL` 配对 block 样本量基线

**证据 ID**：`H2-block-power-baseline-v1`
**状态**：`ACTIVE_PLANNING_BASELINE`（**下限仍有效**，但本文的 `delta=0.125` / `q=0.25` 是
**发生率口径**，该终点已被 [`H2-endpoint-calibration`](H2-endpoint-calibration.md) 判定为零方差、
不可作主要 estimand；严重程度口径下 158 的可检测效应是 0.26 SD，下限依然成立）
**证据类别**：规划敏感性分析；不是模拟校准结果、pilot 或正式研究结论
**日期**：2026-09-06
**机器结果**：[`H2-block-power-baseline.json`](H2-block-power-baseline.json)

## 1. 为什么需要这份新证据

[`H2-power-feasibility`](H2-power-feasibility.md) 是**已废止**的真人方案记录，它的实验单位是
「参与者」：130 名参与者 × 每人 8 局 × 缺失 10% ≈ **936 个配对局**。
[`H2-dual-track-contract`](H2-dual-track-contract.md) 把单位改成了「配对 seed block」，130 个
block 就是 **130 个配对局**——信息量相差约 7 倍。**数字相同不等于结论可以沿用**，旧文件自己
也写明「不得用于当前 go/no-go」。本文提供替代基线。

## 2. 结论

在合同冻结的 SESOI `delta=0.125`、配对不一致概率 `q=0.25`、三家族 Holm 首步阈值 `alpha/3`
（双侧）下，独立配对 block 的功效为：

| 配对 block 数 | 单个家族功效 |
|---:|---:|
| 130（旧数字直接沿用） | **0.709** |
| **158（当前假设下的 80% 功效点）** | **0.803** |
| 200 | 0.896 |
| 260 | 0.962 |

**因此 130 不足以支撑合同的主要估计量**，`AI_FORMAL` 轨道的下限取 **158**。

## 3. 对 `q` 的敏感性

`q` 是纯代理配对轨道从未测量过的量（v0.1 的 `q=0.25` 来自与真人相关的预注册口径，同 seed 下
两个确定性策略的配对不一致概率可能明显不同）：

| 假设 `q` | 达到 80% 功效的最小 block 数 |
|---:|---:|
| 0.15 | 91 |
| 0.25 | 158 |
| 0.35 | 225 |

结论：**校准前任何具体 N 都是假设**。合同因此规定 158 是**下限**而不是目标值，校准结果可以
上调，不得下调。

## 4. 方法

* 每个 block 对一个结果家族产生一次配对差 `D in {-1, 0, 1}`；`Var(D) = q - delta^2`。
* 纯代理轨道没有参与者内聚类，block 之间独立，故 `Var(mean D) = Var(D) / N`。
* 三个主要家族都按 Holm 首步阈值 `alpha/3` 规划，这是最保守的一步。
* 技术故障由预签发备用 seed 整局替换，故规划不再额外扣减缺失率。

## 5. 可复现性

```powershell
python tools/h2_block_power.py
python tools/h2_block_power.py --check docs/experiments/H2-block-power-baseline.json
python -m pytest tests/unit/test_h2_block_power.py -q
```

## 6. 本证据不能替代什么

它只是解析近似的规划基线，不是经验校准。合同的剩余门仍然要求：用冻结 AI 策略跑配对模拟，
测量真实的 `q` 与配对差分布，再确定最终 block 数。若校准结果要求的 N 超出算力预算，必须在
查看任何正式结果之前重新设计（收紧 SESOI 或更换主要终点），不得下调本基线，也不得覆盖本
文件或其 JSON。
