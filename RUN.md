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

## 0.4.3 锚定市场（含价值投资者族）

```bash
# 按装配清单启动 live 市场（清单文件名即 roster_id，内容不再哈希到该 id 即拒绝启动）
.venv/bin/python -m market_game_sim.experiment.h2.live_market --port 8793 \
    --roster-file docs/experiments/0.4.3-rosters/roster-2425a8200ca1a1e748a34a7e9d8b99ba.json

# 锚强度旋钮的全窗口单调性测量（T1107，约 30 分钟，--jobs 控制并行，注意内存）
.venv/bin/python -m market_game_sim.metrics.anchor_strength --jobs 3 --out /tmp/anchor-strength.json

# 成果门 H2-E4：同一清单全窗口跑两次并判定（T1108，约 17 分钟）
.venv/bin/python -m market_game_sim.metrics.anchored_market \
    --roster-file docs/experiments/0.4.3-rosters/roster-2425a8200ca1a1e748a34a7e9d8b99ba.json \
    --out /tmp/anchored-market.json
```

同样是 `engineering-demonstration`。实测记录见
[`docs/experiments/0.4.3-anchored-market.md`](docs/experiments/0.4.3-anchored-market.md)。

## 0.4.2 人类扰动：会话 artifact 落盘

```bash
# 载体 C（count 6 / sensitivity 150）种子 7：先预热到窗口起点（约 3 分钟，期间终端拒单），
# 开放后把 owner 的每笔动作逐条落盘（文件须不存在；Ctrl-C 正常退出时封口）
.venv/bin/python -m market_game_sim.experiment.h2.live_market --port 8793 \
    --roster-file docs/experiments/0.4.2-rosters/roster-e7c9bdeeb558c5b7ed849d73e0e33704.json \
    --session-out /tmp/owner-session.jsonl

# 按种子生成载体 C 的清单（只用 0.4.3 扫描预注册登记的固定项）
.venv/bin/python -m market_game_sim.experiment.perturbation.carrier --seeds 7
```

```bash
# 功效基线：20 个种子的无人类基线全窗口（单进程约 4 小时，单个种子峰值内存 11 GB 以上，
# 15 GB 内存的机器上只能 --jobs 1 且不要同时跑别的重任务）。每跑完一个种子即写入
# artifacts/0.4.2-power-cache/，被中断后重跑同一命令会跳过已完成的种子
.venv/bin/python -m market_game_sim.experiment.perturbation.preregistration power --jobs 1

# 读功效报告后登记 MDE（四个指标依次为 H2F-S-001..004），收录目录下全部会话，写预注册文件；
# 提交后把输出的 sha256 钉进 preregistration.PREREGISTRATION_SHA256
.venv/bin/python -m market_game_sim.experiment.perturbation.preregistration preregister \
    --sessions-dir <会话目录> --mde <m1> <m2> <m3> <m4> --open-loop-seeds <种子…>

# 同种子重放（与封口逐位比对）、正式配对与效应量报告（只读已钉住的预注册）
.venv/bin/python -m market_game_sim.experiment.perturbation.paired replay --session <会话> --out /tmp/replay.json
.venv/bin/python -m market_game_sim.experiment.perturbation.paired pair --session <会话> --out /tmp/effect.json
```

格式见 [`docs/experiments/0.4.2-perturbation-session-format.json`](docs/experiments/0.4.2-perturbation-session-format.json)；
产出为 `experiment-preview`、`run_mode: interactive`，不进任何 evidence index。载体 C 未达
0.4.3 `QUALIFIED`、SC-502 不稳定，只作载体。

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
