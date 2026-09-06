# H2 `AI_FORMAL` 主要终点校准

**证据 ID**：`H2-endpoint-calibration-v1`
**状态**：`ACTIVE_CALIBRATION`
**证据类别**：从冻结证据推导的实测校准；不是新的实验结论
**日期**：2026-09-06
**数据来源**：[`0.1.5-evidence-index.json`](0.1.5-evidence-index.json)（128 个配对 seed block）
**机器结果**：[`H2-endpoint-calibration.json`](H2-endpoint-calibration.json)

## 1. 决定性结论

**`AI_FORMAL` 轨的主要 estimand 必须从「发生概率的配对风险差」改为「严重程度的配对差」。**

理由不是偏好，是实测：v0.1.5 用**同样这两个冻结策略**跑过 128 个配对 seed block，其
evidence index 逐假设记录了「有多少 block 产生非零配对对比」：

| 指标 | 假设数 | 有非零配对块的假设数 | 非零块数范围 |
|---|---:|---:|---|
| `occurrence`（发生） | 12 | **0** | 全部为 0 |
| `severity`（严重程度） | 12 | **12** | 13 — 117 |

发生指标的配对差在整个样本上**恒等于 0**，方差为零，检验统计量退化。**这种情况下增加
block 数不产生任何功效**——158 也好，1580 也好，功效都是 0。终点本身必须换。

严重程度则相反：12 个假设全部有非零配对块，v0.1.5 的 crash severity 效应
`p ≈ 1e-5`、CI 不含 0。

## 2. 严重程度终点的样本量

从记录的 bootstrap 区间反推每个 severity 假设的配对差标准差，取中位数：
**`SD ≈ 1.84e-2`**（观察到的最大效应是 `liquidity_drought.risk_budget_linear_v1.severity.LxM`，
`9.88e-2`，约 5.4 个 SD）。

| SESOI（以 SD 为单位） | 绝对值 | 达到 80% 功效所需 block |
|---|---:|---:|
| 1.00 SD | 1.84e-2 | 11 |
| 0.50 SD | 9.19e-3 | 42 |
| 0.25 SD | 4.60e-3 | 168 |

反过来，给定 block 数的最小可检测效应（MDE）：

| block 数 | MDE | 折合 SD |
|---:|---:|---:|
| 128（v0.1.5 实际） | 5.26e-3 | 0.29 SD |
| 158（当前合同下限） | 4.73e-3 | 0.26 SD |
| 300 | 3.44e-3 | 0.19 SD |

**结论**：在严重程度口径下，[`H2-block-power-baseline`](H2-block-power-baseline.md) 定的
**158 block 下限依然成立且宽裕**（可检测 0.26 SD 的效应）。瓶颈不再是样本量，而是
**SESOI 尚未冻结**。

## 3. 仍属 owner 决策的部分

本文不替 owner 选 SESOI。上表提供的是决策所需的实测尺度：选 0.25 SD 需要 168 个 block，
选 0.5 SD 只需 42 个。建议在 T902 冻结时同时写明「这个幅度为什么在机制上重要」，而不是
按功效方便倒选。

## 4. 对合同的具体影响

1. 三个家族各以**严重程度配对差**为主要 estimand；发生指标降为**描述性次要**，其零方差
   事实必须在报告中如实呈现，不得写成「未发现差异」。
2. 旧的 `delta=0.125` 风险差 SESOI 与之绑定的 `q=0.25` 计算一并作废（它们本就是真人口径）。
3. 新增有效性门：任何主要 estimand 在校准中若出现配对差零方差，一律不得进入正式协议。

## 5. 可复现性

```powershell
python tools/h2_endpoint_calibration.py
python tools/h2_endpoint_calibration.py --check docs/experiments/H2-endpoint-calibration.json
python -m pytest tests/unit/test_h2_endpoint_calibration.py -q
```

## 6. 本证据不能替代什么

它从 v0.1.5 的**冻结既有证据**推导，不是为 H2 新跑的模拟。v0.1.5 的市场配置、参数范围与
2×2 制度处理与 H2 计划一致但不完全相同；若 H2 改变市场参数或场景分布，必须重新校准。
本文也不证明严重程度效应会在 H2 中重现——它只证明该终点**有方差、可被检验**，而发生指标
没有。
