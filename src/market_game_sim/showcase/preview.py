"""T214 [成果门:R3] (FR-024/FR-027, AC-006/AC-007): experiment-preview bundle.

One command produces the R3 bundle under ``artifacts/showcase/R3/``::

    python -m market_game_sim.showcase.preview \
        --plan docs/experiments/0.1.5-factorial-plan.json --seeds 2

Pipeline (reuses the frozen T202/T213 layers, no duplication):

  load_factorial_plan -> first K paired blocks of the frozen seed pool
    -> build_preview_configs (8 real configs: 2 goal models x 4 L/M cells,
       validated by validate_flagship_configs before anything runs)
    -> run_one per config -> analyze_flagship_results with a preview
       resample budget -> comparison.json + four-cell x three-endpoint
       tables in summary.md -> representative replay (single offline HTML)
       from the first valid block's linear/LL run -> manifest.json.

The bundle is ``experiment-preview`` by construction: the preview executes
far fewer blocks than the frozen ``minimum_valid_blocks`` (128), so
``evidence_sufficient`` stays false, the summary marks inference as
ineligible, refuses formal-conclusion wording, and carries the mandatory
「不可作结论」 disclaimer.  The generator refuses any attempt to emit it as
``formal-research`` and never writes into ``docs/experiments/`` (that is
R5/T220's job).
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import pathlib
import sys
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from market_game_sim import __version__
from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.config.serialization import serialize_event
from market_game_sim.eventlog.writer import build_run_header
from market_game_sim.evidence.evidence_guard import guard_evidence_class
from market_game_sim.experiment.config import ExperimentConfig, compute_config_hash
from market_game_sim.experiment.factorial import (
    CELL_IDS,
    CONTRASTS,
    ENDPOINT_FAMILIES,
    METRICS,
    MODEL_IDS,
    FactorialPlanBinding,
    FactorialSeedPlan,
    analyze_flagship_results,
    endpoint_observations,
    load_factorial_plan,
    validate_flagship_configs,
)
from market_game_sim.experiment.runner import RunResult, run_one
from market_game_sim.ledger.account import initial_margin_bp_for_tier
from market_game_sim.replay.generate import build_replay
from market_game_sim.rng.distributions import discrete_choice, uniform_range
from market_game_sim.showcase.manifest import (
    build_showcase_manifest,
    write_showcase_manifest,
)
from market_game_sim.showcase.summary import DISCLAIMER, assert_disclaimer_present

EVIDENCE_CLASS = "experiment-preview"
GATE = "R3"
PRODUCER = "0.1.5 T214"

DEFAULT_PLAN = "docs/experiments/0.1.5-factorial-plan.json"
DEFAULT_OUT = pathlib.Path("artifacts/showcase/R3")
PREVIEW_SEEDS = 2
PREVIEW_BOOTSTRAP_RESAMPLES = 200
PREVIEW_SIGN_FLIP_RESAMPLES = 500
PREVIEW_MAX_TRANSACTIONS = 120

#: Fixed bundle file names (design.md §6: RUN.md / manifest.json / replay.html
#: / summary.md, plus the comparison report and the replay source log).
COMPARISON_NAME = "comparison.json"
LOG_NAME = "replay-run.jsonl"
REPLAY_NAME = "replay.html"
SUMMARY_NAME = "summary.md"
RUN_DOC_NAME = "RUN.md"
MANIFEST_NAME = "manifest.json"

BELIEF_AGENT_IDS = ("belief-0", "belief-1")

#: design.md §6: the offline report must show run family, goal model versions,
#: L/M cells, the three endpoint families, exclusion reasons, evidence class
#: and research-claim eligibility -- a section missing makes generation FAIL.
REQUIRED_PREVIEW_SECTIONS = (
    "## 运行族与目标模型",
    "## 四 cell × 三终点比较",
    "## 排除原因",
    "## 研究声明资格",
    "## 边界声明",
)

REFUSAL_STATEMENT = (
    "本报告显式拒绝正式结论措辞：不输出显著性判断、不使用“显著/不显著”表述、"
    "不建立或不否定任何研究声明；表中数字仅为描述性统计。"
)

_PREVIEW_DISCLAIMER_BLOCK = (
    f"> ⚠️ {DISCLAIMER}：本成果包为实验预览（experiment-preview），使用远小于冻结"
    "样本量的小种子计划，仅证明旗舰 2×2 管线可运行并产出可观察的比较表与回放，"
    "不构成任何研究结论、效应量主张或可外推的统计判断。"
)


class PreviewError(ValueError):
    """The preview bundle request is invalid or mis-scoped."""


def _mm_spec() -> AgentSpec:
    """Inventory market maker shared byte-identically by all four cells."""
    return AgentSpec(
        agent_id="mm-0",
        role="inventory_market_maker",
        observe_interval_ns=100_000_000,
        latency_ns=5_000_000,
        is_market_maker=True,
        half_spread_ticks=5,
        quote_size=10_000,
        max_inventory=100_000,
        inventory_skew_k_bp=10_000,
    )


def _belief_spec(model_id: str, seed: int, agent_id: str, is_low_l: bool) -> AgentSpec:
    """Belief agent whose tier/appetite follow the frozen semantic draws."""
    weights = {2: 3334, 3: 3333, 5: 3333} if is_low_l else {10: 3334, 20: 3333, 50: 3333}
    tier, _ = discrete_choice(weights, seed, agent_id, "bench_leverage_tier", 0, 0)
    appetite, _ = uniform_range(
        Decimal(500), Decimal(20_000), seed, agent_id, "risk_appetite", 0, 0
    )
    return AgentSpec(
        agent_id=agent_id,
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=tier,
        initial_bp=initial_margin_bp_for_tier(tier),
        aggressiveness_bp=10_000,
        max_order_qty=10_000,
        goal_model_id=model_id,
        risk_appetite_x1000=int(appetite),
        ewma_half_life_trades=0,  # warmup off so the replay chain can trade
    )


def build_preview_configs(
    seed: int, binding: FactorialPlanBinding
) -> dict[str, dict[str, ExperimentConfig]]:
    """Build the eight paired configs for one seed block of the frozen plan.

    The configs carry the FULL frozen seed plan (that is what the run-family
    matrix and ``validate_flagship_configs`` require); the preview merely
    executes the pool *prefix* of ``binding.seed_plan.pool``.  Construction
    fails closed: the configs are validated before they are returned, so a
    seed outside the frozen pool or a parity violation raises here.
    """
    pool = binding.seed_plan.pool
    seed_plan = {"n_seeds": len(pool), "seeds": list(pool)}
    configs: dict[str, dict[str, ExperimentConfig]] = {}
    for model_id in MODEL_IDS:
        configs[model_id] = {}
        for cell_id in CELL_IDS:
            is_low_l = cell_id[0] == "L"
            is_low_m = cell_id[1] == "L"
            specs = [_mm_spec()]
            for agent_id in BELIEF_AGENT_IDS:
                specs.append(_belief_spec(model_id, seed, agent_id, is_low_l))
            configs[model_id][cell_id] = ExperimentConfig(
                seed=seed,
                max_transactions=PREVIEW_MAX_TRANSACTIONS,
                maint_bp=300 if is_low_m else 700,
                agent_specs=specs,
                run_family="SPONTANEOUS",
                seed_plan=seed_plan,
                l_level="low" if is_low_l else "high",
                m_level="low" if is_low_m else "high",
                group_label=cell_id,
            )
    validate_flagship_configs(configs, binding)
    return configs


def _write_run_log(
    path: pathlib.Path,
    result: RunResult,
    config: ExperimentConfig,
    *,
    run_id: str,
    tick_size: str,
    min_quantity: str,
    cash_unit: str,
) -> None:
    """Serialize one run as RUN_HEADER + EVENT x N + RUN_TRAILER JSONL."""
    header = build_run_header(
        run_id=run_id,
        code_version=__version__,
        config_hash=compute_config_hash(config),
        master_seed=config.seed,
        started_at_wall=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        tick_size=tick_size,
        min_quantity=min_quantity,
        cash_unit=cash_unit,
        mult=config.mult,
        fee_bps_cap=max(config.maker_bps, config.taker_bps, 0),
        initial_price_ticks=config.initial_price_ticks,
        agent_initial_bp={
            s.agent_id: initial_margin_bp_for_tier(s.leverage_tier) for s in config.agent_specs
        },
    )
    max_txn = max(
        (e["transaction_seq"] for e in result.events if "transaction_seq" in e),
        default=2,
    )
    trailer = {
        "record_kind": "RUN_TRAILER",
        "terminated": result.terminated,
        "abort_code": result.abort_code,
        "abort_detail": None,
        "last_committed_transaction_seq": max_txn,
        "record_count": 2 + len(result.events),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(serialize_event(header))
        for record in result.events:
            f.write(serialize_event(record))
        f.write(serialize_event(trailer))


def _cell_endpoint_means(
    results: dict[str, dict[str, list[RunResult]]], valid_seeds: list[int]
) -> dict[str, Any]:
    """Descriptive per-cell occurrence/severity means over valid blocks."""
    valid = set(valid_seeds)
    means: dict[str, Any] = {}
    for family in ENDPOINT_FAMILIES:
        means[family] = {}
        for model_id in MODEL_IDS:
            per_cell: dict[str, Any] = {}
            for cell_id in CELL_IDS:
                runs = [r for r in results[model_id][cell_id] if r.seed in valid]
                if runs:
                    obs = [endpoint_observations(r)[family] for r in runs]
                    occurrence = sum(o.occurrence for o in obs) / len(obs)
                    severity = sum(o.severity for o in obs) / len(obs)
                else:
                    occurrence, severity = 0.0, 0.0
                per_cell[cell_id] = {
                    "occurrence": occurrence,
                    "severity": severity,
                    "n_runs": len(runs),
                }
            means[family][model_id] = per_cell
    return means


def _combined_config_hash(hashes_by_seed: dict[int, dict[str, dict[str, str]]]) -> str:
    """blake2b digest over every per-seed config hash of the preview batch."""
    canonical = json.dumps(hashes_by_seed, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()


def _preview_binding(
    binding: FactorialPlanBinding, executed_seeds: list[int]
) -> FactorialPlanBinding:
    """Re-scope the frozen plan to the executed prefix for the preview only.

    ``analyze_flagship_results`` is fail-closed against a run series that
    stops before the frozen ``minimum_valid_blocks`` while reserve seeds
    remain — that guard protects T215's formal execution.  The preview
    deliberately executes a pool *prefix*, so it analyzes against a binding
    whose seed plan is exactly the executed prefix; the bundle then
    re-scopes every verdict against the FROZEN minimum (``evidence_sufficient:
    false`` / ``inference_eligible: false``) in ``comparison.json`` and the
    summary.  The frozen preregistration reference is carried over unchanged.
    """
    preview_plan = FactorialSeedPlan(
        planned_seeds=tuple(executed_seeds),
        reserve_seeds=(),
        minimum_valid_blocks=len(executed_seeds),
    )
    preview_plan.validate()
    return dataclasses.replace(binding, seed_plan=preview_plan)


def _assert_required_sections(text: str) -> None:
    """Fail closed when the summary lacks a design.md §6 required section."""
    missing = [section for section in REQUIRED_PREVIEW_SECTIONS if section not in text]
    if missing:
        raise PreviewError(
            f"preview summary is missing required sections (design.md §6): {missing}"
        )


def _guard_out_dir(out_dir: str | pathlib.Path) -> pathlib.Path:
    """Refuse any output location inside ``docs/experiments/`` (R5/T220's job)."""
    out = pathlib.Path(out_dir)
    resolved = out.resolve()
    for ancestor in (resolved, *resolved.parents):
        if ancestor.name == "experiments" and ancestor.parent.name == "docs":
            raise PreviewError(
                f"refusing to write the preview bundle into {out.as_posix()}: "
                "docs/experiments/ holds formal evidence and is R5/T220's job"
            )
    return out


def _render_preview_summary(
    *,
    binding: FactorialPlanBinding,
    executed_seeds: list[int],
    valid_seeds: list[int],
    exclusions: dict[int, list[str]],
    analysis: dict[str, Any],
    means: dict[str, Any],
    config_hash: str,
    rebuild_command: str,
    replay_run_id: str,
    replay_model: str,
    replay_cell: str,
) -> str:
    lines: list[str] = []
    lines.append("# Flagship Preview -- Gate R3")
    lines.append("")
    lines.append(f"- **evidence_class**: `{EVIDENCE_CLASS}`")
    lines.append(f"- **gate**: `{GATE}`")
    lines.append(f"- **code_version**: `{__version__}`")
    lines.append(f"- **config_hash**: `{config_hash}`")
    lines.append(f"- **executed_seeds**: `{executed_seeds}`")
    lines.append(f"- **valid_seeds**: `{valid_seeds}`")
    lines.append(f"- **preregistration**: `{binding.preregistration_id}`")
    lines.append(f"- **replay_run_id**: `{replay_run_id}` ({replay_model}/{replay_cell})")
    lines.append("")
    lines.append("## 重建")
    lines.append("")
    lines.append("```bash")
    lines.append(rebuild_command)
    lines.append("```")
    lines.append("")

    lines.append("## 运行族与目标模型")
    lines.append("")
    lines.append(
        "- **运行族**: `SPONTANEOUS`——8 个配置（2 目标模型 × 4 cell）全部声明为"
        " SPONTANEOUS，无任何注入字段；触发来源闭集内不含 `EXOGENOUS_STRESS`。"
    )
    lines.append(
        "- **目标模型**: `risk_budget_linear_v1` 与 `risk_budget_threshold_v1`；"
        "目标层不读取 `L/M`、`leverage_tier`、`initial_bp`、`maint_bp` 或实验臂 ID。"
    )
    lines.append(
        "- **制度处理**: L low `{2x, 3x, 5x}` / high `{10x, 20x, 50x}`；"
        "M low `300bp` / high `700bp`（`maint_bp` 只进入约束层）。"
    )
    lines.append(
        "- **配对设计**: 每个 seed block 内四 cell 共享同一 seed 与逐代理偏好抽签，"
        "仅 `L/M` 编码不同。"
    )
    lines.append("")

    lines.append("## 四 cell × 三终点比较")
    lines.append("")
    lines.append(
        f"下表为 {len(valid_seeds)} 个有效 seed block 上的描述性均值"
        "（occurrence 为 0/1 结局的均值；severity 为各终点家族的连续幅度）。"
    )
    lines.append("")
    for family in ENDPOINT_FAMILIES:
        family_means = means[family]
        lines.append(f"### {family}")
        lines.append("")
        lines.append(
            "| cell | linear occurrence | linear severity"
            " | threshold occurrence | threshold severity |"
        )
        lines.append("|---|---|---|---|---|")
        for cell_id in CELL_IDS:
            linear = family_means[MODEL_IDS[0]][cell_id]
            threshold = family_means[MODEL_IDS[1]][cell_id]
            lines.append(
                f"| {cell_id} | {linear['occurrence']:.3f} (n={linear['n_runs']})"
                f" | {linear['severity']:.4f}"
                f" | {threshold['occurrence']:.3f} (n={threshold['n_runs']})"
                f" | {threshold['severity']:.4f} |"
            )
        lines.append("")
    lines.append(
        "对比效应与不确定性（描述性；完整对比矩阵、置换 p 值与 BH 校正仅存在于"
        " `comparison.json` 的 `factorial_rehearsal` 中，均不可作结论）："
    )
    lines.append("")
    for family in ENDPOINT_FAMILIES:
        family_report = analysis["endpoint_families"][family]
        lines.append(f"### {family} 对比效应")
        lines.append("")
        lines.append("| model | metric | contrast | effect | ci_low | ci_high | n_blocks |")
        lines.append("|---|---|---|---|---|---|---|")
        for model_id in MODEL_IDS:
            for metric in METRICS:
                for contrast in CONTRASTS:
                    effect = family_report["models"][model_id][metric][contrast]
                    lines.append(
                        f"| {model_id} | {metric} | {contrast} | {effect['effect']:.4f}"
                        f" | {effect['ci_low']:.4f} | {effect['ci_high']:.4f}"
                        f" | {effect['n_blocks']} |"
                    )
        lines.append("")
    lines.append("方向不对称（crash − surge occurrence，描述性）：")
    lines.append("")
    lines.append("| model | cell | effect | ci_low | ci_high |")
    lines.append("|---|---|---|---|---|")
    for model_id in MODEL_IDS:
        for cell_id in CELL_IDS:
            asym = analysis["direction_asymmetry"][model_id][cell_id]
            lines.append(
                f"| {model_id} | {cell_id} | {asym['effect']:.4f}"
                f" | {asym['ci_low']:.4f} | {asym['ci_high']:.4f} |"
            )
    lines.append("")

    lines.append("## 排除原因")
    lines.append("")
    if exclusions:
        for seed, codes in sorted(exclusions.items()):
            lines.append(f"- seed `{seed}`：`{','.join(codes)}`（整块 8 个运行全部排除）。")
    else:
        lines.append("- 无整块排除：全部 executed seed block 技术有效。")
    lines.append("")

    lines.append("## 研究声明资格")
    lines.append("")
    lines.append(
        f"- 冻结预注册要求 ≥ {binding.seed_plan.minimum_valid_blocks} 个有效 seed block；"
        f"本预览仅执行 {len(executed_seeds)} 块，`evidence_sufficient=false`。"
    )
    lines.append(
        "- 本成果包的 evidence_class 为 `experiment-preview`：不能建立、支持或否定任何"
        "研究声明；比较表数字仅为描述性统计。"
    )
    lines.append(
        "- 正式结论只能由 R5（T220）以 `formal-research` 证据类、经冻结预注册协议与"
        "多重校正后写入 `docs/experiments/`；本包不进入正式 evidence index。"
    )
    lines.append("")

    lines.append("## 边界声明")
    lines.append("")
    lines.append(_PREVIEW_DISCLAIMER_BLOCK)
    lines.append("")
    lines.append(REFUSAL_STATEMENT)
    lines.append("")
    return "\n".join(lines)


def _render_preview_run_doc(*, rebuild_command: str) -> str:
    return (
        f"# Flagship Preview Bundle -- Gate {GATE}\n"
        "\n"
        "## 重建命令\n"
        "\n"
        "```bash\n"
        f"{rebuild_command}\n"
        "```\n"
        "\n"
        "## 边界声明\n"
        "\n"
        "本成果包为实验预览（evidence_class=experiment-preview），用远小于冻结样本量的"
        "小种子计划演练旗舰 2×2 管线并产出四 cell × 三终点比较表与代表性回放。"
        "它不可作结论，不建立或不否定任何研究声明，不写入 `docs/experiments/` "
        "正式证据索引（那是 R5/T220 的职责）。\n"
        "\n"
        "## 产物\n"
        "\n"
        f"- `{COMPARISON_NAME}` — 四 cell × 三终点比较表（含管线演练的推断字段）\n"
        f"- `{LOG_NAME}` — 代表性回放的事件日志（RUN_HEADER + EVENT × N + RUN_TRAILER）\n"
        f"- `{REPLAY_NAME}` — 单文件离线回放\n"
        f"- `{SUMMARY_NAME}` — 比较表摘要与「不可作结论」声明\n"
        f"- `{MANIFEST_NAME}` — provenance + 产物清单\n"
    )


def generate_preview_bundle(
    out_dir: str | pathlib.Path,
    *,
    plan_path: str | pathlib.Path = DEFAULT_PLAN,
    n_seeds: int = PREVIEW_SEEDS,
    bootstrap_resamples: int = PREVIEW_BOOTSTRAP_RESAMPLES,
    sign_flip_resamples: int = PREVIEW_SIGN_FLIP_RESAMPLES,
    tick_size: str = "0.01",
    min_quantity: str = "0.001",
    cash_unit: str = "0.01",
    rebuild_command: str | None = None,
) -> dict[str, Any]:
    """Produce the full R3 experiment-preview bundle into ``out_dir``.

    Executes ``n_seeds`` paired seed blocks (8 SPONTANEOUS runs each: 2 goal
    models × 4 L/M cells) from the frozen pool prefix, rehearses the frozen
    factorial machinery on them, and writes:

    - ``comparison.json`` — four-cell × three-endpoint comparison with the
      preview re-scoping (``evidence_sufficient=false`` vs the frozen
      minimum) plus the descriptive ``factorial_rehearsal`` report;
    - ``replay-run.jsonl`` + ``replay.html`` — representative offline replay
      of the first valid block's linear/LL run;
    - ``summary.md`` — the required design.md §6 sections with the mandatory
      「不可作结论」 disclaimer and explicit refusal of formal-conclusion
      wording (generation FAILS if either is missing);
    - ``RUN.md`` — rebuild command + boundary statement;
    - ``manifest.json`` — code_version / config_hash (combined over all
      8·n_seeds configs) / executed seed plan / ``evidence_class=experiment-preview``.

    Fail-closed guards: ``n_seeds`` must stay below the frozen
    ``minimum_valid_blocks`` (a formal-size run is T215's job), the output
    must never land in ``docs/experiments/``, and the
    (SPONTANEOUS, experiment-preview) evidence pairing is asserted via the
    T212 evidence guard.  The manifest's ``seed_plan`` states the *executed*
    prefix (the bundle's place in the frozen plan, mirroring T203's
    single-seed convention); the frozen 144-seed pool itself is referenced by
    ``comparison.json``'s preregistration/plan block.
    """
    out = _guard_out_dir(out_dir)
    if type(n_seeds) is not int or n_seeds < 1:
        raise PreviewError(f"n_seeds must be a positive integer, got {n_seeds!r}")
    binding = load_factorial_plan(plan_path)
    if n_seeds >= binding.seed_plan.minimum_valid_blocks:
        raise PreviewError(
            f"preview must execute fewer blocks than the frozen minimum_valid_blocks "
            f"({binding.seed_plan.minimum_valid_blocks}); a formal-size run is T215's job"
        )
    pool = binding.seed_plan.pool
    if n_seeds > len(pool):
        raise PreviewError(f"n_seeds={n_seeds} exceeds the frozen pool size {len(pool)}")
    executed_seeds = list(pool[:n_seeds])

    # T212 evidence guard: only SPONTANEOUS may carry experiment-preview.
    guard_evidence_class("SPONTANEOUS", EVIDENCE_CLASS)

    results: dict[str, dict[str, list[RunResult]]] = {
        model_id: {cell_id: [] for cell_id in CELL_IDS} for model_id in MODEL_IDS
    }
    fingerprints_by_seed: dict[int, dict[str, dict[str, str]]] = {}
    configs_by_seed: dict[int, dict[str, dict[str, ExperimentConfig]]] = {}
    for seed in executed_seeds:
        configs = build_preview_configs(seed, binding)
        fingerprints_by_seed[seed] = validate_flagship_configs(configs, binding)
        configs_by_seed[seed] = configs
        for model_id in MODEL_IDS:
            for cell_id in CELL_IDS:
                result = run_one(configs[model_id][cell_id])
                if result.terminated == "ABORTED":
                    raise PreviewError(
                        f"preview run aborted (seed={seed}, model={model_id}, "
                        f"cell={cell_id}, abort_code={result.abort_code}); "
                        "cannot build a preview bundle from a failed run"
                    )
                results[model_id][cell_id].append(result)

    preview_binding = _preview_binding(binding, executed_seeds)
    initial_price = configs_by_seed[executed_seeds[0]][MODEL_IDS[0]][
        CELL_IDS[0]
    ].initial_price_ticks
    analysis = analyze_flagship_results(
        results,
        preview_binding,
        initial_price_ticks=initial_price,
        bootstrap_resamples=bootstrap_resamples,
        sign_flip_resamples=sign_flip_resamples,
    )
    valid_seeds = list(analysis["seed_plan"]["valid_seeds"])
    exclusions = dict(analysis["seed_plan"]["excluded_seed_blocks"])
    if not valid_seeds:
        raise PreviewError(
            f"every executed seed block was excluded ({exclusions}); a preview bundle "
            "requires at least one technically valid representative run"
        )
    means = _cell_endpoint_means(results, valid_seeds)
    config_hash = _combined_config_hash(fingerprints_by_seed)

    if rebuild_command is None:
        rebuild_command = (
            f"python -m market_game_sim.showcase.preview "
            f"--plan {pathlib.Path(plan_path).as_posix()} --seeds {n_seeds}"
        )

    out.mkdir(parents=True, exist_ok=True)

    first_seed = valid_seeds[0]
    replay_index = executed_seeds.index(first_seed)
    replay_model = MODEL_IDS[0]
    replay_cell = CELL_IDS[0]
    # The kernel stamps every event with run_id=exp-s{seed}; the RUN_HEADER
    # must carry the identical id or the offline reader rejects the log (TI-5).
    replay_run_id = f"exp-s{first_seed}"
    log_path = out / LOG_NAME
    _write_run_log(
        log_path,
        results[replay_model][replay_cell][replay_index],
        configs_by_seed[first_seed][replay_model][replay_cell],
        run_id=replay_run_id,
        tick_size=tick_size,
        min_quantity=min_quantity,
        cash_unit=cash_unit,
    )
    replay_path = out / REPLAY_NAME
    build_replay(log_path, replay_path)

    comparison: dict[str, Any] = {
        "schema_version": 1,
        "evidence_class": EVIDENCE_CLASS,
        "gate": GATE,
        "producer": PRODUCER,
        "plan": binding.report_reference(),
        "preview": {
            "n_seeds": len(executed_seeds),
            "executed_seeds": executed_seeds,
            "valid_seeds": valid_seeds,
            "excluded_seed_blocks": exclusions,
            "frozen_minimum_valid_blocks": binding.seed_plan.minimum_valid_blocks,
            "evidence_sufficient": False,
            "inference_eligible": False,
            "refusal": REFUSAL_STATEMENT,
            "bootstrap_resamples": bootstrap_resamples,
            "sign_flip_resamples": sign_flip_resamples,
            "max_transactions_per_run": PREVIEW_MAX_TRANSACTIONS,
        },
        "factorial_rehearsal": {
            "note": (
                "frozen contrast/BH machinery rehearsed on the preview prefix; "
                "every inference field is descriptive-only and ineligible for "
                "formal conclusions"
            ),
            "report": analysis,
        },
        "cell_endpoint_means": means,
    }
    comparison_path = out / COMPARISON_NAME
    comparison_path.write_text(
        json.dumps(comparison, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )

    summary_text = _render_preview_summary(
        binding=binding,
        executed_seeds=executed_seeds,
        valid_seeds=valid_seeds,
        exclusions=exclusions,
        analysis=analysis,
        means=means,
        config_hash=config_hash,
        rebuild_command=rebuild_command,
        replay_run_id=replay_run_id,
        replay_model=replay_model,
        replay_cell=replay_cell,
    )
    assert_disclaimer_present(summary_text)
    _assert_required_sections(summary_text)
    summary_path = out / SUMMARY_NAME
    summary_path.write_text(summary_text, encoding="utf-8")

    run_doc_path = out / RUN_DOC_NAME
    run_doc_path.write_text(
        _render_preview_run_doc(rebuild_command=rebuild_command), encoding="utf-8"
    )

    artifact_entries = [
        {
            "artifact_id": "comparison",
            "path": COMPARISON_NAME,
            "format": "json",
            "producer": PRODUCER,
        },
        {"artifact_id": "replay_log", "path": LOG_NAME, "format": "jsonl", "producer": PRODUCER},
        {"artifact_id": "replay", "path": REPLAY_NAME, "format": "html", "producer": PRODUCER},
        {
            "artifact_id": "summary",
            "path": SUMMARY_NAME,
            "format": "markdown",
            "producer": PRODUCER,
        },
        {
            "artifact_id": "run_doc",
            "path": RUN_DOC_NAME,
            "format": "markdown",
            "producer": PRODUCER,
        },
    ]
    manifest = build_showcase_manifest(
        out,
        artifact_entries,
        code_version=__version__,
        config_hash=config_hash,
        seed=executed_seeds[0],
        seed_plan={"n_seeds": len(executed_seeds), "seeds": executed_seeds},
        evidence_class=EVIDENCE_CLASS,
        gate=GATE,
    )
    write_showcase_manifest(manifest, out / MANIFEST_NAME)

    return {
        "out_dir": out,
        "comparison": comparison_path,
        "log": log_path,
        "replay": replay_path,
        "summary": summary_path,
        "run_doc": run_doc_path,
        "manifest": out / MANIFEST_NAME,
        "executed_seeds": executed_seeds,
        "valid_seeds": valid_seeds,
        "excluded_seed_blocks": exclusions,
        "replay_run_id": replay_run_id,
        "evidence_class": EVIDENCE_CLASS,
        "gate": GATE,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m market_game_sim.showcase.preview")
    parser.add_argument(
        "--plan",
        default=DEFAULT_PLAN,
        help=f"frozen factorial plan JSON (default: {DEFAULT_PLAN})",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help=f"output directory (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        default=PREVIEW_SEEDS,
        help=f"number of paired seed blocks to execute (default: {PREVIEW_SEEDS})",
    )
    parser.add_argument(
        "--bootstrap-resamples",
        type=int,
        default=PREVIEW_BOOTSTRAP_RESAMPLES,
        help=f"preview bootstrap budget (default: {PREVIEW_BOOTSTRAP_RESAMPLES})",
    )
    parser.add_argument(
        "--sign-flip-resamples",
        type=int,
        default=PREVIEW_SIGN_FLIP_RESAMPLES,
        help=f"preview sign-flip budget (default: {PREVIEW_SIGN_FLIP_RESAMPLES})",
    )
    args = parser.parse_args(argv)

    rebuild_command = (
        f"python -m market_game_sim.showcase.preview --plan {args.plan} "
        f"--seeds {args.seeds} --out {args.out}"
    )
    result = generate_preview_bundle(
        args.out,
        plan_path=args.plan,
        n_seeds=args.seeds,
        bootstrap_resamples=args.bootstrap_resamples,
        sign_flip_resamples=args.sign_flip_resamples,
        rebuild_command=rebuild_command,
    )
    print(f"flagship preview bundle written to {result['out_dir']}")
    print(
        f"  evidence_class={EVIDENCE_CLASS} executed_seeds={result['executed_seeds']} "
        f"valid_seeds={result['valid_seeds']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
