# RUN — 本地运行手册

## 0.3.2 Owner Web 交易终端（自由模拟）

```bash
.venv/bin/python -m market_game_sim.experiment.h2.owner_web --stage free --port 8791
```

打开 `http://127.0.0.1:8791`（仅绑定 loopback）。页面与验收契约见
`docs/features/0.3/0.3.2-web-trading-terminal/interaction-design.html`（定稿设计稿）
与 `docs/features/0.3/0.3.2-web-trading-terminal/interaction-design-notes.md`。

验收命令（T949-T952 旅程轨 + 集成门）：

```bash
.venv/bin/python -m pytest tests/e2e/test_h2_owner_terminal.py tests/integration/test_h2_owner_web.py -q
.venv/bin/python tools/verify.py
```

## 0.4.1 持续 AI 市场（纯 AI 生态）

按 `StrategyRoster` 装配的纯 AI 市场，冷启动锚打破预热死锁，四个策略族 + 量化族。

```bash
# 启动持续运行的 live 市场（loopback）
.venv/bin/python -m market_game_sim.experiment.h2.live_market --seed 7 --port 8792

# 市场质量报告（六项质量 + 五项 stylized facts，未通过项在第一屏可见）
.venv/bin/python -m market_game_sim.metrics.quality_run --seconds 2200

# 量化交易者族运行 artifact（固定信号序列，不依赖 alphamill 运行时）
.venv/bin/python -m market_game_sim.experiment.quant_family_run --seconds 300
```

三者的产出一律是 `engineering-demonstration`：不进任何 evidence index，不建立研究
声明。量化族 artifact 另带单向边界声明（沙盘结果不得用作策略有效性证据、不回流
alphamill 证据链，ADR-011 §决策 5），落盘前自检，缺声明或出现绩效字段即失败。

实测记录见 [`docs/experiments/0.4.1-market-quality-baseline.md`](docs/experiments/0.4.1-market-quality-baseline.md)。

## 已归档入口（随 ADR-010 归档，机械保留但当前不执行）

下列入口属于已归档的 **N-of-1 采集轨**（6 训练 + 24 正式场景）。归档是
[`ADR-010`](docs/decisions/010-market-ecology-research-pivot.md) 的范围裁决，不是未达标
（处置见 [`releases/0.3.md`](docs/features/releases/0.3.md)）：机械与测试保留在仓库，
**受控对照类研究问题复活时可启用**，届时须先修订研究北极星与配对协议。
在此之前不要按这些命令采集数据——它们产出的 artifact 没有任何轨道消费。

```bash
# 采集态（training/formal）：E2 preview 门 fail-closed，必须提供含 manifest.json 的
# preview 证据目录（无则打印 OWNER_WEB_PREVIEW_BLOCKED 退出码 2）
.venv/bin/python -m market_game_sim.experiment.h2.preview            # 生成证据包（artifacts/h2/preview）
.venv/bin/python -m market_game_sim.experiment.h2.owner_web \
    --stage training --preview-dir artifacts/h2/preview --port 8791

# 训练实验启动器（owner Web 终端驱动 H2 训练场景，0.3.2 T937/T939 机制层）
.venv/bin/python -m market_game_sim.experiment.h2.owner_experiment --position 0 --port 8793
```

owner 证据导出（会话对象方法，归档采集流程使用）：`OwnerWebSession.export_artifact(dir)`；
证据目录机器校验：`python tools/validate_owner_evidence.py --dir docs/experiments/owner-n-of-1`。

## 待接入入口

- ~~**持续 AI 市场（`experiment/h2/live_market.py`）**：启动命令与市场质量报告命令
  尚未写入本文件~~ → **已接入**（0.4.1 T978，成果门 `H2-E3`）：见上「0.4.1 持续 AI 市场」。
