"""CLI 分发入口：`python -m market_game_sim.experiment`（design.md §4）。

design.md 的 CLI 合同列出了完整命令族（``protocol validate|freeze|preview``、
``assign|train|run|abort``、``adjudicate|analyze|deliver``），但那是全部 H2 任务
完成后的最终形态。这里只接入已经有实现支撑的子命令；未接入的子命令不占位声明——
一个 ``--help`` 里列出、调用即报错的选项，比"暂不支持"更容易让人以为它能用。

当前已接入：

* ``protocol preview``（T909）：生成 H2-A 成果门的 preview 包。
* ``preview``（T915）：生成 H2-B 成果门的 preview 包（锁定客户端 + 三结果 + 机制）。
* ``protocol validate|freeze``（T916）：校验双层预注册门并生成首样本前正式冻结归档。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROG = "python -m market_game_sim.experiment"


def _protocol_preview(args: argparse.Namespace) -> int:
    from market_game_sim.experiment.h2 import preview

    out = Path(args.out) if args.out else None
    target = preview.generate(out)
    print(f"H2-A preview bundle written to {target}")
    return 0


def _preview(args: argparse.Namespace) -> int:
    from market_game_sim.experiment.h2 import preview_b

    out = Path(args.out) if args.out else None
    target = preview_b.generate(out)
    print(f"H2-B preview bundle written to {target}")
    return 0


def _protocol_validate(args: argparse.Namespace) -> int:
    from market_game_sim.experiment.h2 import formal_freeze

    preregistration = Path(args.preregistration) if args.preregistration else None
    kwargs = {"preregistration_path": preregistration} if preregistration else {}
    frozen = formal_freeze.build_formal_protocol(**kwargs)
    print(f"H2 formal protocol valid: {frozen.protocol_hash}")
    return 0


def _protocol_freeze(args: argparse.Namespace) -> int:
    from market_game_sim.experiment.h2 import formal_freeze

    out = Path(args.out) if args.out else formal_freeze.DEFAULT_OUT
    preregistration = Path(args.preregistration) if args.preregistration else None
    kwargs = {"preregistration_path": preregistration} if preregistration else {}
    target = formal_freeze.freeze_study(out, **kwargs)
    print(f"H2 formal freeze archive written to {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROG)
    subparsers = parser.add_subparsers(dest="command", required=True)

    protocol_parser = subparsers.add_parser("protocol", help="H2 protocol operations")
    protocol_sub = protocol_parser.add_subparsers(dest="protocol_command", required=True)

    protocol_preview_parser = protocol_sub.add_parser(
        "preview", help="generate the H2-A experiment-preview bundle (T909)"
    )
    protocol_preview_parser.add_argument(
        "--out", default=None, help="output directory (default: artifacts/h2/preview)"
    )
    protocol_preview_parser.set_defaults(func=_protocol_preview)

    protocol_validate_parser = protocol_sub.add_parser(
        "validate", help="validate the final H2 preregistration and executable protocol (T916)"
    )
    protocol_validate_parser.add_argument(
        "--preregistration", default=None, help="H2 preregistration markdown"
    )
    protocol_validate_parser.set_defaults(func=_protocol_validate)

    protocol_freeze_parser = protocol_sub.add_parser(
        "freeze", help="archive the pre-sample H2 formal protocol and assignments (T916)"
    )
    protocol_freeze_parser.add_argument(
        "--out", default=None, help="output directory (default: docs/experiments/H2-formal-freeze)"
    )
    protocol_freeze_parser.add_argument(
        "--preregistration", default=None, help="H2 preregistration markdown"
    )
    protocol_freeze_parser.set_defaults(func=_protocol_freeze)

    preview_parser = subparsers.add_parser(
        "preview", help="generate the H2-B experiment-preview bundle (T915)"
    )
    preview_parser.add_argument(
        "--out", default=None, help="output directory (default: artifacts/h2/preview-b)"
    )
    preview_parser.set_defaults(func=_preview)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
