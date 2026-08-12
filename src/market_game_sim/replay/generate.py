"""T201 (FR-019): Replay generation entry point + CLI.

``build_replay(log_path, out_path, *, downsample=None)`` reads a log, builds
per-frame state and K-lines, renders a single-file HTML, and writes it
atomically (no partial ``.html``).  CLI:

    python -m market_game_sim.replay.generate --log <path> --out <out.html> [--downsample N]
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

from market_game_sim.replay.downsample import DownsampleRule
from market_game_sim.replay.frames import _build_frames
from market_game_sim.replay.html import render_replay_html
from market_game_sim.replay.kline import DEFAULT_BAR_NS, build_klines
from market_game_sim.replay.reader import LogError, read_log

DEFAULT_KLINE_PERIOD_NS = DEFAULT_BAR_NS


def build_replay(
    log_path: str | pathlib.Path,
    out_path: str | pathlib.Path,
    *,
    downsample: DownsampleRule | None = None,
    kline_period_ns: int = DEFAULT_KLINE_PERIOD_NS,
) -> None:
    """Generate a single-file HTML replay from ``log_path`` to ``out_path``.

    Raises :class:`LogError` on TI-4/TI-5 logs or any read failure;
    :class:`ValueError` on an invalid ``kline_period_ns`` (<= 0) or a
    downsample rule that matches zero frames (the page would have no frame
    to render).
    """
    if (
        not isinstance(kline_period_ns, int)
        or isinstance(kline_period_ns, bool)
        or kline_period_ns <= 0
    ):
        raise ValueError(f"kline_period_ns must be a positive integer, got {kline_period_ns!r}")
    log = read_log(log_path)
    cfg = log.config
    frames = _build_frames(
        log.events,
        mult=cfg.mult,
        fee_bps_cap=cfg.fee_bps_cap,
        initial_price_ticks=cfg.initial_price_ticks,
        agent_initial_bp=cfg.agent_initial_bp,
        downsample=downsample,
    )
    if not frames:
        if downsample is not None:
            raise ValueError(
                f"downsample rule '{downsample.describe()}' matches zero frames; "
                "refusing to render an empty replay"
            )
        raise ValueError("log produced zero frames; refusing to render an empty replay")
    klines = build_klines(
        log.events,
        period_ns=kline_period_ns,
        initial_price_ticks=cfg.initial_price_ticks,
    )
    downsample_desc = downsample.describe() if downsample is not None else None

    html_str = render_replay_html(
        log,
        frames,
        klines,
        initial_price_ticks=cfg.initial_price_ticks,
        mult=cfg.mult,
        downsample_desc=downsample_desc,
    )
    _atomic_write(out_path, html_str)


def _atomic_write(path: str | pathlib.Path, content: str) -> None:
    out = pathlib.Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m market_game_sim.replay.generate")
    parser.add_argument("--log", required=True, help="path to event log JSONL")
    parser.add_argument("--out", required=True, help="output .html path")
    parser.add_argument(
        "--downsample",
        type=int,
        default=None,
        metavar="N",
        help="keep every N-th frame (optional, N>=1)",
    )
    parser.add_argument(
        "--kline-period-ns",
        type=int,
        default=DEFAULT_KLINE_PERIOD_NS,
        metavar="NS",
        help="K-line bar period in nanoseconds (default: 60s)",
    )
    args = parser.parse_args(argv)

    if args.downsample is not None:
        try:
            rule = DownsampleRule(keep_every=args.downsample)
        except ValueError as exc:
            print(f"replay failed: invalid --downsample: {exc}", file=sys.stderr)
            return 2
    else:
        rule = None

    try:
        build_replay(args.log, args.out, downsample=rule, kline_period_ns=args.kline_period_ns)
    except LogError as exc:
        print(f"replay failed: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"replay failed: invalid argument: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
