"""0.4.2 T1125（FR-605）：实验载体 C——0.4.3 预注册扫描格 count 6 / sensitivity 150。

载体只由 0.4.3 扫描预注册里登记的固定项组装（``metrics/anchor_scan.config_roster``：默认
装配加价值族、响应函数 ``linear_saturating_v1``），本模块不另写一份参数。每个种子一个
``roster_id``，落盘到 ``docs/experiments/0.4.2-rosters/``，可由 live 市场 ``--roster-file``
打开、内容须仍哈希到文件名。

载体 C 未达 0.4.3 ``QUALIFIED``、SC-502 不稳定，只作载体：凡引用它的报告与 artifact 都要
带 :data:`CARRIER_DISCLAIMER`。

用法::

    python -m market_game_sim.experiment.perturbation.carrier --seeds 7
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Sequence

from market_game_sim.experiment.roster import StrategyRoster, parse_roster, save_roster
from market_game_sim.metrics.anchor_scan import (
    PREREGISTRATION_PATH,
    config_roster,
    load_preregistration,
)

ROOT = pathlib.Path(__file__).resolve().parents[4]
ROSTER_DIR = ROOT / "docs" / "experiments" / "0.4.2-rosters"

#: owner 2026-10-15 选定的载体格（spec FR-605）。
CARRIER_COUNT = 6
CARRIER_SENSITIVITY_X1000 = 150

CARRIER_DISCLAIMER = (
    "载体 C（0.4.3 扫描格 count 6 / sensitivity 150）未达 0.4.3 QUALIFIED，SC-502 不稳定，"
    "只作人类扰动实验的载体，不声明市场真实性"
)


def carrier_roster(seed: int) -> StrategyRoster:
    """载体 C 在 ``seed`` 上的装配清单。"""
    prereg = load_preregistration(ROOT / PREREGISTRATION_PATH)
    return parse_roster(config_roster(prereg, CARRIER_COUNT, CARRIER_SENSITIVITY_X1000, seed))


def save_carriers(seeds: Sequence[int], directory: pathlib.Path = ROSTER_DIR) -> list[pathlib.Path]:
    return [save_roster(carrier_roster(seed), directory) for seed in seeds]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m market_game_sim.experiment.perturbation.carrier"
    )
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--out", default=str(ROSTER_DIR))
    args = parser.parse_args(argv)
    for path in save_carriers(args.seeds, pathlib.Path(args.out)):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
