"""0.4.2 T1127（SC-605 / AC-609）：跨种子基线、功效分析与预注册文件。

顺序是硬约束（spec SC-605、§5 不变量）：

1. ``power``：在 :data:`POWER_SEEDS` 上跑载体 C 的无人类基线，得到四个指标的跨种子标准差
   ``σ_b`` 与功效报告 ``docs/experiments/0.4.2-power-baseline.json``；
2. owner 读功效报告后登记逐指标最小可检出效应（MDE）；
3. ``preregister``：把功效报告哈希、``σ_b``、MDE、``N``、有效配对下限、开环回放种子清单与
   **预注册时已存在的全部处理会话**（封口与未封口都算，不得挑选）的内容哈希写进单一文件
   ``docs/experiments/0.4.2-preregistration.json``，先于任何正式配对提交；
4. 提交后把文件的 sha256 钉进 :data:`PREREGISTRATION_SHA256`。配对入口
   （:func:`begin_pairing`）只读该文件：缺失、未钉住、哈希不一致、功效报告被改、或处理会话
   不在其中时一律 fail closed。

功效近似（owner 2026-10-16 裁决）：以 ``√2 · σ_b`` 作为配对差值标准差的上界（假设同种子两臂
指标相关 ``ρ ≥ 0``），``N = ⌈((z₀.₉₅ + z₀.₈₀) · √2 · σ_b / MDE)²⌉``，逐指标计算后取最大值。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import statistics
import sys
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from market_game_sim.experiment.perturbation import carrier, session
from market_game_sim.metrics.stability_effect import METRIC_IDS, METRICS_DICTIONARY_VERSION

ROOT = pathlib.Path(__file__).resolve().parents[4]
POWER_REPORT_PATH = ROOT / "docs" / "experiments" / "0.4.2-power-baseline.json"
#: 逐种子基线结果的续跑缓存（``artifacts/`` 不入库）：一次全窗口运行要十分钟以上、单进程
#: 峰值内存 10 GB 以上，进程被中断时已完成的种子不重跑。
POWER_CACHE_DIR = ROOT / "artifacts" / "0.4.2-power-cache"
PREREGISTRATION_PATH = ROOT / "docs" / "experiments" / "0.4.2-preregistration.json"
SCHEMA_VERSION = 1

#: 功效基线的 20 个种子（与原场种子 7、开环种子互不相交）。
POWER_SEEDS: tuple[int, ...] = tuple(range(1001, 1021))

#: 预注册文件提交后在这里钉住其 sha256；``None`` 表示尚未预注册，配对入口拒绝运行。
PREREGISTRATION_SHA256: str | None = None

Z_95 = 1.6448536269514722
Z_80 = 0.8416212335729143
#: 功效表给出的 MDE 档位（以 σ_b 为单位），供 owner 登记时参考。
MDE_TABLE_MULTIPLES = (0.25, 0.5, 0.75, 1.0, 1.5)

# 稳定原因码。
PREREGISTRATION_MISSING = "PREREGISTRATION_MISSING"
PREREGISTRATION_NOT_PINNED = "PREREGISTRATION_NOT_PINNED"
PREREGISTRATION_DRIFT = "PREREGISTRATION_DRIFT"
PREREGISTRATION_INVALID = "PREREGISTRATION_INVALID"
POWER_REPORT_DRIFT = "POWER_REPORT_DRIFT"
TREATMENT_NOT_PREREGISTERED = "TREATMENT_NOT_PREREGISTERED"

_PREREG_KEYS = frozenset(
    {
        "schema_version",
        "evidence_class",
        "run_mode",
        "metrics_dictionary_version",
        "carrier",
        "power_report_sha256",
        "power_seeds",
        "sigma_b",
        "mde",
        "n_by_metric",
        "n_required",
        "min_valid_pairs",
        "open_loop_seeds",
        "treatment_sessions",
        "statistics",
    }
)


class PreregistrationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def file_sha256(path: str | pathlib.Path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def _dump(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------- #
# 1. 跨种子基线与功效报告
# --------------------------------------------------------------------------- #


def required_n(sigma_b: float, mde: float) -> int:
    """单个指标所需的有效配对数（保守近似，``σ_d ≤ √2 · σ_b``）。"""
    if mde <= 0:
        raise PreregistrationError(PREREGISTRATION_INVALID, "MDE 必须为正")
    if sigma_b == 0:
        return 1
    return math.ceil(((Z_95 + Z_80) * math.sqrt(2) * sigma_b / mde) ** 2)


def _baseline_point(seed: int) -> dict[str, Any]:
    from market_game_sim.experiment.perturbation.paired import run_baseline

    run = run_baseline(carrier.carrier_roster(seed))
    m = run.measurement
    return {
        "seed": seed,
        "roster_id": run.roster_id,
        "window_start_ns": run.window_start_ns,
        "aborted": run.aborted,
        "advances": run.advances,
        "degenerate": list(m.degenerate) if m is not None else ["WINDOW_NOT_ESTABLISHED"],
        "metrics": dict(m.metrics) if m is not None else None,
    }


def power_report(points: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """由逐种子基线测量得出 ``σ_b`` 与功效表；退化种子不进 ``σ_b``，如实列出。"""
    valid = [p for p in points if not p["degenerate"]]
    sigma_b: dict[str, float | None] = {}
    for metric in METRIC_IDS:
        values = [float(p["metrics"][metric]) for p in valid]
        sigma_b[metric] = statistics.stdev(values) if len(values) >= 2 else None
    table = {
        metric: {
            str(k): required_n(sigma, k * sigma) if sigma else None for k in MDE_TABLE_MULTIPLES
        }
        for metric, sigma in sigma_b.items()
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_class": "experiment-preview",
        "metrics_dictionary_version": METRICS_DICTIONARY_VERSION,
        "carrier": {
            "count": carrier.CARRIER_COUNT,
            "sensitivity_x1000": carrier.CARRIER_SENSITIVITY_X1000,
            "disclaimer": carrier.CARRIER_DISCLAIMER,
        },
        "seeds": [p["seed"] for p in points],
        "per_seed": [dict(p) for p in points],
        "valid_seeds": len(valid),
        "sigma_b": sigma_b,
        "power": {
            "rule": "N = ceil(((z0.95 + z0.80) * sqrt(2) * sigma_b / MDE)^2), max over metrics",
            "assumption": "rho >= 0 between arms on the same seed, so sigma_d <= sqrt(2) * sigma_b",
            "z_0.95": Z_95,
            "z_0.80": Z_80,
            "n_by_mde_in_sigma_b": table,
        },
    }


def _cached_point(args: tuple[int, pathlib.Path | None]) -> dict[str, Any]:
    """一个种子的基线点；缓存命中（且清单标识仍一致）即不重跑，跑完立即落盘。"""
    seed, cache_dir = args
    path = None if cache_dir is None else cache_dir / f"seed-{seed}.json"
    if path is not None and path.is_file():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("roster_id") == carrier.carrier_roster(seed).roster_id:
            return cached
    point = _baseline_point(seed)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(_dump(point), encoding="utf-8")
        tmp.replace(path)  # 原子替换：中断时不会留下半份结果
    return point


def run_power_baseline(
    seeds: Sequence[int] = POWER_SEEDS,
    *,
    jobs: int = 1,
    cache_dir: pathlib.Path | None = None,
) -> list[dict[str, Any]]:
    work = [(seed, cache_dir) for seed in seeds]
    if jobs <= 1:
        return [_cached_point(item) for item in work]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(_cached_point, work))


# --------------------------------------------------------------------------- #
# 2. 预注册文件
# --------------------------------------------------------------------------- #


def collect_sessions(directory: str | pathlib.Path) -> list[dict[str, Any]]:
    """目录下**全部**会话文件（不得挑选）；任何一份不合格即拒绝预注册。"""
    out = []
    for path in sorted(pathlib.Path(directory).glob("*.jsonl")):
        check = session.load_session(path)
        if not check.ok:
            raise PreregistrationError(
                PREREGISTRATION_INVALID, f"{path.name}: {check.reason_code} {check.detail}"
            )
        header = check.header
        assert header is not None
        out.append(
            {
                "file": path.name,
                "session_id": header["session_id"],
                "content_hash": check.content_hash,
                "status": check.status,
                "original_seed": header["seed"],
                "roster_id": header["roster_id"],
                "actions": len(check.actions),
            }
        )
    if not out:
        raise PreregistrationError(PREREGISTRATION_INVALID, f"{directory} 下没有会话文件")
    return out


def build_preregistration(
    power: Mapping[str, Any],
    power_sha256: str,
    sessions: Sequence[Mapping[str, Any]],
    mde: Mapping[str, float],
    *,
    open_loop_seeds: Sequence[int],
    min_valid_pairs: int | None = None,
) -> dict[str, Any]:
    if set(mde) != set(METRIC_IDS):
        raise PreregistrationError(PREREGISTRATION_INVALID, f"MDE 必须覆盖 {METRIC_IDS}")
    sigma_b = power["sigma_b"]
    if any(sigma_b[m] is None for m in METRIC_IDS):
        raise PreregistrationError(
            PREREGISTRATION_INVALID, "功效报告缺 σ_b（有效基线种子不足 2 个）"
        )
    n_by_metric = {m: required_n(float(sigma_b[m]), float(mde[m])) for m in METRIC_IDS}
    n_required = max(n_by_metric.values())
    floor = n_required if min_valid_pairs is None else min_valid_pairs
    if floor < 2:
        raise PreregistrationError(PREREGISTRATION_INVALID, "有效配对下限至少为 2")
    seeds = list(open_loop_seeds)
    used = set(power["seeds"]) | {int(s["original_seed"]) for s in sessions}
    if len(set(seeds)) != len(seeds) or used & set(seeds):
        raise PreregistrationError(
            PREREGISTRATION_INVALID, "开环种子须互不重复，且与功效种子、原场种子不相交"
        )
    if len(seeds) < floor:
        raise PreregistrationError(PREREGISTRATION_INVALID, "开环种子数少于有效配对下限")
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_class": "experiment-preview",
        "run_mode": "interactive",
        "metrics_dictionary_version": METRICS_DICTIONARY_VERSION,
        "carrier": dict(power["carrier"]),
        "power_report_sha256": power_sha256,
        "power_seeds": list(power["seeds"]),
        "sigma_b": dict(sigma_b),
        "mde": {m: float(mde[m]) for m in METRIC_IDS},
        "n_by_metric": n_by_metric,
        "n_required": n_required,
        "min_valid_pairs": floor,
        "open_loop_seeds": seeds,
        "treatment_sessions": [dict(s) for s in sessions],
        "statistics": {
            "effect": "median of per-seed differences (human - baseline)",
            "interval": "paired bootstrap percentile",
            "ci_level": 0.90,
            "n_resamples": 10_000,
            "bootstrap_seed": 0,
        },
    }


# --------------------------------------------------------------------------- #
# 3. 配对入口守卫
# --------------------------------------------------------------------------- #


def begin_pairing(
    path: str | pathlib.Path = PREREGISTRATION_PATH,
    *,
    pinned_sha256: str | None = None,
    power_report_path: str | pathlib.Path = POWER_REPORT_PATH,
) -> tuple[dict[str, Any], str]:
    """配对入口唯一的预注册读取点：返回 ``(预注册, sha256)``，任何不一致都 fail closed。"""
    target = pathlib.Path(path)
    if not target.is_file():
        raise PreregistrationError(
            PREREGISTRATION_MISSING, f"{target} 不存在：预注册先于任何正式配对"
        )
    pinned = PREREGISTRATION_SHA256 if pinned_sha256 is None else pinned_sha256
    if pinned is None:
        raise PreregistrationError(PREREGISTRATION_NOT_PINNED, "预注册文件的 sha256 尚未钉住")
    actual = file_sha256(target)
    if actual != pinned:
        raise PreregistrationError(PREREGISTRATION_DRIFT, f"sha256 为 {actual}，钉住的是 {pinned}")
    prereg = json.loads(target.read_text(encoding="utf-8"))
    if set(prereg) != _PREREG_KEYS or prereg.get("schema_version") != SCHEMA_VERSION:
        raise PreregistrationError(PREREGISTRATION_INVALID, "字段集或版本不符")
    if file_sha256(power_report_path) != prereg["power_report_sha256"]:
        raise PreregistrationError(POWER_REPORT_DRIFT, "功效报告在预注册之后被改动")
    return prereg, actual


def verify_preregistration(
    recorded_sha256: str, path: str | pathlib.Path = PREREGISTRATION_PATH
) -> None:
    """写出配对结果之前再核一次：运行期间预注册不得变化。"""
    if file_sha256(path) != recorded_sha256:
        raise PreregistrationError(PREREGISTRATION_DRIFT, "配对运行期间预注册文件被改动")


def require_treatment(prereg: Mapping[str, Any], check: session.SessionCheck) -> dict[str, Any]:
    """处理会话必须是预注册收录的那一份（按内容哈希）。"""
    for entry in prereg["treatment_sessions"]:
        if check.ok and entry["content_hash"] == check.content_hash:
            return dict(entry)
    raise PreregistrationError(
        TREATMENT_NOT_PREREGISTERED, f"会话内容哈希 {check.content_hash} 不在预注册中"
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m market_game_sim.experiment.perturbation.preregistration"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    power = sub.add_parser("power", help="跑 20 个种子的无人类基线并写功效报告")
    power.add_argument("--jobs", type=int, default=1)
    power.add_argument(
        "--cache-dir", default=str(POWER_CACHE_DIR), help="逐种子结果缓存，被中断后续跑不重跑"
    )
    power.add_argument("--out", default=str(POWER_REPORT_PATH))
    prereg = sub.add_parser("preregister", help="登记 MDE 并写预注册文件（先于任何正式配对）")
    prereg.add_argument("--sessions-dir", required=True)
    prereg.add_argument(
        "--mde", nargs=4, type=float, required=True, metavar=METRIC_IDS, help="四个指标的 MDE"
    )
    prereg.add_argument("--open-loop-seeds", type=int, nargs="+", required=True)
    prereg.add_argument("--min-valid-pairs", type=int)
    prereg.add_argument("--power-report", default=str(POWER_REPORT_PATH))
    prereg.add_argument("--out", default=str(PREREGISTRATION_PATH))
    args = parser.parse_args(argv)

    if args.command == "power":
        report = power_report(
            run_power_baseline(jobs=args.jobs, cache_dir=pathlib.Path(args.cache_dir))
        )
        pathlib.Path(args.out).write_text(_dump(report), encoding="utf-8")
        print(f"power report: {args.out} (valid seeds {report['valid_seeds']}/{len(POWER_SEEDS)})")
        return 0
    out = pathlib.Path(args.out)
    if out.exists():
        print(f"{out} already exists: a preregistration is never rewritten", file=sys.stderr)
        return 2
    power_path = pathlib.Path(args.power_report)
    built = build_preregistration(
        json.loads(power_path.read_text(encoding="utf-8")),
        file_sha256(power_path),
        collect_sessions(args.sessions_dir),
        dict(zip(METRIC_IDS, args.mde, strict=True)),
        open_loop_seeds=args.open_loop_seeds,
        min_valid_pairs=args.min_valid_pairs,
    )
    out.write_text(_dump(built), encoding="utf-8")
    print(
        f"preregistration: {out}\nsha256: {file_sha256(out)}  -> pin it in PREREGISTRATION_SHA256"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
