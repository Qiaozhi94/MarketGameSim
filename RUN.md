# RUN — 本地运行手册

## 0.3.2 Owner Web 交易终端（H2-D1 preview）

```bash
# 1) 自由模拟（默认，无需 preview 证据）
.venv/bin/python -m market_game_sim.experiment.h2.owner_web --stage free --port 8791

# 2) 采集态（training/formal）：E2 preview 门 fail-closed，
#    必须提供含 manifest.json 的 preview 证据目录（无则打印 OWNER_WEB_PREVIEW_BLOCKED 退出码 2）
.venv/bin/python -m market_game_sim.experiment.h2.preview            # 先生成证据包（artifacts/h2/preview）
.venv/bin/python -m market_game_sim.experiment.h2.owner_web \
    --stage training --preview-dir artifacts/h2/preview --port 8791
```

打开 `http://127.0.0.1:8791`（仅绑定 loopback）。页面与验收契约见
`docs/features/0.3/0.3.2-web-trading-terminal/interaction-design.html`（定稿设计稿）
与 `docs/features/0.3/0.3.2-web-trading-terminal/interaction-design-notes.md`。

验收命令（T949-T952 旅程轨 + 集成门）：

```bash
.venv/bin/python -m pytest tests/e2e/test_h2_owner_terminal.py tests/integration/test_h2_owner_web.py -q
.venv/bin/python tools/verify.py
```

owner 证据导出（会话对象方法，Phase 2 采集流程使用）：`OwnerWebSession.export_artifact(dir)`；
证据目录机器校验：`python tools/validate_owner_evidence.py --dir docs/experiments/owner-n-of-1`。
