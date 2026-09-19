# ADR-010：项目方向重构——从 N-of-1 配对对比转向持续 AI 市场生态与人类扰动研究

日期：2026-09-19  
状态：Accepted（用户裁决，2026-09-19 实验首场体验后对话）  
关联规格：[`../features/0.3/0.3.2-web-trading-terminal/spec.md`](../features/0.3/0.3.2-web-trading-terminal/spec.md)  
关联文档：[`../research/owner-research-question.md`](../research/owner-research-question.md)（北极星）、
[`../features/0.3/0.3.2-web-trading-terminal/interaction-design.html`](../features/0.3/0.3.2-web-trading-terminal/interaction-design.html)、
[`../../src/market_game_sim/experiment/h2/live_market.py`](../../src/market_game_sim/experiment/h2/live_market.py)

## 背景

0.3.2 的 owner 采集轨沿用了 0.3.1 配对对比的方法论：60 逻辑秒冻结市场跨度、
观察白名单（只给参照策略可见的信息子集）、每窗至多一次规范动作。该框架的
目的是让 owner 的数据能与两条参照臂做"干净"的对比。

训练场景 0 的首次实测（2026-09-19）暴露了这条链路的体验与意义双重问题：
实验页只有冻结观察子集的 7 个数字字段（无 K 线、无盘口、无成交流），场景
在 owner 未及上手时即按 1:1 节拍自动走完全部窗口（32 窗全 NO_ACTION）。
owner 随后的质疑直指设计前提：

- 没有价格历史（K 线）与市场上下文，人类无法做出任何有依据的交易判断；
- 固定场次、固定跨度、固定节奏是"受控实验的假设"，不是真实市场的运行方式；
- owner 的真实研究兴趣不是个人交易画像，而是**市场生态的稳定性与人类扰动**。

## 决策

1. **owner 研究问题正式成文**（[`owner-research-question.md`](../research/owner-research-question.md)），
   成为所有 owner-facing 设计的第一判据：
   - 研究人类参与对 AI 市场稳定性的影响（何种操作诱发崩盘/暴涨）；
   - 研究 AI 市场自身的均衡与突变；
   - 明确不做 owner 个人画像、不做固定场次节奏、不做配对公平性观察砍削。
2. **live_market 成为主干实验载体**：持续运行的 AI 市场（0.3.1 冻结配置的
   真实代理家族——做市商 + 因子策略——增量内核驱动实时互交易），owner 经
   Web 终端随时进出，市价/限价/撤单直通内核撮合路径；稳定性指标
   （价格序列、收益、大波动事件、最大回撤）逐秒记录、可导出。
3. **观察面按"真实交易者所见"重构**，不再受配对白名单约束：
   盘口（≤10 档）、最近成交、K 线（1m/5m/15m/1h/4h）、完整账户、进行中
   蜡烛、 TradingView 式交互（缩放/平移/时间轴）。白名单外指标
   （MA/MACD/24h/标记价格/预估强平价）仅属自由模拟演示，标注即可。
4. **N-of-1 配对对比轨归档**：0.3.1 配对协议、assignment/准入机械、原
   24 场正式采集流程整体冻结保留（基础设施完好），当出现"受控对照"类
   研究问题时可复活。

## 后果

- **正面**：owner 终端体验与真实市场一致；稳定性研究即刻可行；配对方法
  论不再绑架产品层；同种子确定性保留（无人类介入时轨迹可复现，构成
  天然的对照基线）。
- **代价**：原 0.3.2 的 6 训练 + 24 正式 N-of-1 采集流程、`admitted`/
  evidence index 链路在 live 轨不适用（live 轨不入 evidence index，
  与归档的配对轨同等待遇）；`build_kline_set`/`live_market` 的长历史
  支持需随运行时长迭代。
- **门禁**：owner-facing 里程碑的 G1 前置一项"研究问题确认"（见
  features/README §阶段成果门）：本次交付如何服务《owner 研究问题》。
- **归档轨**：0.3.1 配对协议与 N-of-1 场景机械保留在仓库（spec/design/
  tests/artifacts 目录与文档不删除），标注"归档，受控对照问题复活时可启用"。
