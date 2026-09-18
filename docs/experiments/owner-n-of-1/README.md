# owner n-of-1 证据包（0.3.2 T929 冻结合同）

本目录固定存放 owner 单人研究（n-of-1）的采集证据。目录布局与字段 schema 由
`docs/features/0.3/0.3.2-web-trading-terminal/tasks.md` T929 冻结，且必须先于任何
真实采集冻结。机器校验入口：

```bash
python tools/validate_owner_evidence.py --dir docs/experiments/owner-n-of-1
```

退出码 0 = 通过；非 0 = 失败（逐条打印 `ERROR: <原因>`）。校验工具以本文件为
schema 真源，两者必须同步修改。

## 目录布局

| 文件 | 作用 |
| --- | --- |
| `environment.json` | 目标环境记录（OS / Python / 启动命令 / 记录时间） |
| `owner-session-manifest.json` | 场景会话清单（训练 6 场 + 正式 24 场） |
| `owner-evidence-index.json` | 索引：研究状态、冻结停止原因、计数、manifest 哈希 |

## schema

### environment.json

所有字段均为非空字符串：

| 字段 | 说明 |
| --- | --- |
| `os` | 操作系统与平台描述 |
| `python` | 解释器版本 |
| `command` | 场景启动命令原文 |
| `recorded_at` | 环境记录时间（ISO 8601） |

```json
{
  "os": "Linux-6.18-x86_64 (WSL2)",
  "python": "3.11.9",
  "command": "python -m market_game_sim.cli --stage formal --scenario S-FM-01",
  "recorded_at": "2026-09-17T09:00:00+08:00"
}
```

### owner-session-manifest.json

顶层对象：`schema_version`（当前恒为 `1`）与 `sessions`（数组）。数组内每个会话
对象的 `session_id` 必须全清单唯一：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `session_id` | string | 非空，全清单唯一 |
| `stage` | string | `"training"` 或 `"formal"` |
| `scenario_id` | string | 非空 |
| `status` | string | 场景级状态：`"complete"` 或 `"excluded"` |
| `seed` | integer | 场景种子 |
| `started_at` / `ended_at` | string | 非空时间戳（ISO 8601） |
| `events_sha256` | string | 该会话事件流文件原始字节的 sha256，64 位十六进制 |

```json
{
  "schema_version": 1,
  "sessions": [
    {
      "session_id": "owner-training-01",
      "stage": "training",
      "scenario_id": "S-TR-01",
      "status": "complete",
      "seed": 20260901,
      "started_at": "2026-09-17T09:00:00+08:00",
      "ended_at": "2026-09-17T09:30:00+08:00",
      "events_sha256": "b1946ac92492d2347c6235b4d2611184e0f2a3c9e15d1f7a9d3e4f6a8b2c5d70"
    }
  ]
}
```

### owner-evidence-index.json

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `schema_version` | integer | 恒为 `1` |
| `study_status` | string | `"complete"` / `"incomplete-study"` / `"zero-sample"` |
| `stop_reason` | string | `study_status != "complete"` 时必填且非空；complete 时可省 |
| `sessions_total` | integer | 必须等于 manifest 会话总数 |
| `training_total` | integer | 必须等于 manifest 中 `stage=training` 的会话数 |
| `formal_total` | integer | 必须等于 manifest 中 `stage=formal` 的会话数 |
| `manifest_sha256` | string | `owner-session-manifest.json` 文件原始字节的 sha256 |
| `sessions` | array | 每项 `{session_id, stage, status}`，与 manifest.sessions 逐条完全一致 |

`study_status` 与样本数强绑定（`training` 可为 0..6）：

| study_status | 判定条件 |
| --- | --- |
| `complete` | `formal_total == 24` 且 `training_total == 6` |
| `incomplete-study` | `0 < formal_total < 24` |
| `zero-sample` | `formal_total == 0` |

其余组合（如 formal 超过 24，或 formal==24 但 training!=6）不构成合法研究状态，
校验必失败。`status=excluded` 的会话仍占用场景池名额，计入对应 stage 计数。

```json
{
  "schema_version": 1,
  "study_status": "incomplete-study",
  "stop_reason": "所有者时间受限，按冻结顺序停在 S-FM-10，不补跑、不外推",
  "sessions_total": 16,
  "training_total": 6,
  "formal_total": 10,
  "manifest_sha256": "3f7a1c92d2347c6235b4d2611184e0f2a3c9e15d1f7a9d3e4f6a8b2c5d70b194",
  "sessions": [
    {
      "session_id": "owner-training-01",
      "stage": "training",
      "status": "complete"
    }
  ]
}
```

## 校验规则清单（tools/validate_owner_evidence.py 实现）

1. 三份文件存在且 JSON 可解析；
2. manifest：`session_id` 全清单唯一；`stage`/`status` 枚举合法；
   `events_sha256` 为 64 位十六进制；`seed`/时间戳等字段类型合法；
3. index：`sessions_total`/`training_total`/`formal_total` 与 manifest 一致；
4. index：`study_status` 与样本数一致（见上表）；非 `complete` 必须给出非空
   `stop_reason`；
5. index：`manifest_sha256` 等于 manifest 文件实际 sha256（原始文件字节）；
6. index：`sessions` 的 `(session_id, stage, status)` 三元组与 manifest 逐条
   完全一致。
