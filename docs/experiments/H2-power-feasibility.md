# H2 Q-304 功效可行性证据

**证据 ID**：`H2-Q304-power-feasibility-v4`  
**状态**：`SUPERSEDED_BY_SCOPE_CLARIFICATION`  
**证据类别**：规划敏感性分析；不是 H1 真人输入、H2 pilot 或正式研究结果  
**日期**：2026-09-06

## 1. 结论

本证据按“130 名外部真人参与者”计算，已被
[`H2-dual-track-contract`](H2-dual-track-contract.md) 废止。当前合同中的 130 是配对 seed
block；两者的方差结构和推断单位不同，本计算不得用于当前 go/no-go。以下内容仅保留为历史
决策证据和可复现记录。

当前“固定 130 名已分配参与者、每人 8 局”的资源规划能在冻结的三个参与者内相关情景中
达到至少 80% 功效，Q-304 的保守规划分支判定为 `go`。130 是最差相关性情景刚好达到门槛
的下限，不应再向下取整。实际报酬预算已由
[`H2-compensation-budget`](H2-compensation-budget.md) 冻结；正式招募前仅剩模拟人类策略
经验校准门。

| 参与者内相关 `rho` | N=130 功效 | 达到 80% 的最小 N |
|---:|---:|---:|
| 0.2 | 0.998037 | 49 |
| 0.5 | 0.934125 | 90 |
| 0.8 | 0.800030 | 130 |

## 2. 输入与来源

- `delta=0.125`：0.3.1 Q-304 冻结的主要发生率配对风险差 SESOI。
- `q=0.25`：沿用 [`0.1.5-preregistration.md`](0.1.5-preregistration.md) §6 的配对不一致概率。
- 每人 8 局、pair 缺失 10%、`rho=0.2/0.5/0.8`：0.3.1 Q-304 冻结敏感性网格。
- 三个主要家族、family-wise `alpha=0.05`：使用保守的 Holm 首步阈值 `alpha/3`。

## 3. 方法

每局配对差取 `D in {-1,0,1}`，使用 v0.1 的方差口径
`Var(D)=q-delta^2`。缺失完全随机的规划近似令
`m=8*(1-0.10)=7.2`，参与者均值的方差为：

```text
Var(mean D | participant) = (q - delta^2) * (1 + (m - 1) * rho) / m
```

随后按参与者为独立聚类，计算双侧正态近似功效，并从 N=2 起搜索首个功效不低于 0.80 的 N。
该计算比完整 Holm 联合分布更保守，因为每一家族都按 Holm 首步阈值规划。

## 4. 可复现性

机器结果：[`H2-power-feasibility.json`](H2-power-feasibility.json)。

```powershell
python tools/h2_power_feasibility.py
python tools/h2_power_feasibility.py --check docs/experiments/H2-power-feasibility.json
python -m pytest tests/unit/test_h2_power_feasibility.py -q
```

## 5. 不能替代的证据

仓库目前没有 H1 真人输入、H2 pilot 数据或已实现的 simulated-human policy，因此本计算不能
声称完成经验校准。正式招募前必须补充模拟人类策略或独立 pilot 的方差/相关性依据；若校准
结果使 N=130 的功效低于 80%，必须回到 no-go 或在查看任何 H2 正式结果前重新设计并生成
新版本证据，不得覆盖本文件或原 JSON。
