# Implementation Plan: Market Simulation Foundation

**对应规格**：`specs/001-market-simulation-foundation/spec.md`  
**状态**：Draft

## 技术上下文

- Python 3.11+
- `src` 布局，核心领域逻辑尽量使用标准库
- pytest + 属性/不变量测试
- 初期输出 JSONL/Parquet；可视化不进入核心层

## 候选组件边界

```text
SimulationClock/EventQueue
        ↓
Agent → OrderGateway → Exchange/OrderBook → Trade
  ↑                ↓                      ↓
ObservationBus   Risk/Ledger          EventLog
```

## 宪章检查

| 原则 | 状态 | 计划证据 |
|---|---|---|
| 可追溯规格优先 | 通过 | 代码和测试名称引用 FR/SC 编号 |
| 撮合正确性 | 待实现 | 守恒、不变量和优先级测试 |
| 实验可复现 | 待实现 | 单一 RNG 注入及配置快照 |
| 角色与能力分离 | 通过 | 策略、账户、信息集分别建模 |
| 先验证市场 | 待实现 | 独立基准验证报告 |
| 安全与合规 | 通过 | 无真实交易连接器 |

## 阶段

1. 领域模型与确定性撮合。
2. 账户、风控和事件日志。
3. 基础规则代理与合成基本价值。
4. 批量实验、统计指标和验证。
5. 评审后再决定 ABIDES/PAMS 兼容或迁移策略。

## 关键风险

- 代理规则可能预先决定实验结论：使用消融实验、参数扫描和盲化分析缓解。
- 统计特征可能只在狭窄参数区间出现：保存失败区域，不做选择性报告。
- 过早追求真实交易所细节：以验收指标作为范围边界。
