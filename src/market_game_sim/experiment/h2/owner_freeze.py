"""0.3.2 E1 冻结的 owner 轨参数与证据契约（tasks T929）。

ADR-006/Q-401 把四项 owner 冻结参数（时间压缩比、K 线周期集合、时点采样粒度、
场景市场时间跨度）留给本里程碑 E1 拍板。本模块是**增量**冻结记录：0.3.1 的
``protocol.owner_decision_contract()`` 内容哈希已被正式归档锁绑定（see
``artifacts.verify_formal_bindings``），因此本里程碑的冻结值落在独立模块与新
证据目录（``docs/experiments/owner-n-of-1/``）中，绝不回写旧合同。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from market_game_sim.replay.kline import OWNER_KLINE_PERIODS_NS

FREEZE_SCHEMA_VERSION = 1
FROZEN_AT = "2026-09-18"

# 时间压缩比：采集 1:1 实时；自由模拟允许加速（ADR-006）。
TIME_COMPRESSION = "1:1"

# 时点采样粒度：1 逻辑秒（与 0.3.1 窗口合同 logical_ns_per_window 对齐）。
SAMPLING_INTERVAL_NS = 1_000_000_000

# 场景市场时间跨度：60 逻辑秒 = windows_per_scenario(60) × logical_ns_per_window(1s)。
SCENARIO_MARKET_SPAN_NS = 60_000_000_000


def owner_freeze_contract() -> dict[str, Any]:
    """E1 冻结参数的规范 JSON 形态（供页面、采样器与 artifact 引用）。"""

    return {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "frozen_at": FROZEN_AT,
        "time_compression": TIME_COMPRESSION,
        "kline_periods_ns": list(OWNER_KLINE_PERIODS_NS),
        "sampling_interval_ns": SAMPLING_INTERVAL_NS,
        "scenario_market_span_ns": SCENARIO_MARKET_SPAN_NS,
    }


def owner_freeze_hash() -> str:
    """冻结参数的规范内容哈希（blake2b，与仓库 config 哈希口径一致）。"""

    payload = json.dumps(
        owner_freeze_contract(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=32).hexdigest()
