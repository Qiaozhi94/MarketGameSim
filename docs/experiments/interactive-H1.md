# H1 手动交易沙盒交付

从仓库根目录生成代表性成果包：

```bash
python -m market_game_sim.interactive.delivery
```

产物写入 `artifacts/showcase/H1/`，包含 `RUN.md`、`manifest.json`、
`input-journal.jsonl`、`run.jsonl` 和可断网打开的 `replay.html`。

验证规范输入、事件结果与逐帧状态：

```bash
python -m market_game_sim.interactive.replay_session \
  artifacts/showcase/H1/input-journal.jsonl
```

该成果属于 `interactive + engineering-demonstration`：使用合成市场和模拟资金，不构成
交易建议，不进入正式研究证据。
