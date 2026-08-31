"""T215: resumable execution of the frozen formal flagship experiment.

The runner executes one complete paired seed block at a time.  A block is
eight primary runs (two goal models x four L/M cells) plus the eight frozen
TI-2 deterministic reruns.  Only a complete block is checkpointed, so an
interruption can at worst repeat the current block.

The command writes raw, ignored evidence below ``artifacts/formal/T215``::

    python -m market_game_sim.showcase.formal

Use ``--max-new-blocks N`` to bound one invocation.  Re-running the same
command resumes from verified checkpoints.  Partial progress is formal-run
material but is explicitly ineligible for a research conclusion; T216 owns
the evidence index and conditional conclusion after the frozen stopping rule
has been reached.
"""

from __future__ import annotations

import argparse
import dataclasses
import gzip
import hashlib
import json
import pathlib
import sys
from typing import Any

from market_game_sim import __version__
from market_game_sim.evidence.evidence_guard import guard_evidence_class
from market_game_sim.experiment.factorial import (
    CELL_IDS,
    MODEL_IDS,
    TECHNICAL_INVALID_CODES,
    FactorialPlanBinding,
    analyze_flagship_results,
    audit_deterministic_rerun,
    event_summary_sha256,
    load_factorial_plan,
    validate_flagship_configs,
)
from market_game_sim.experiment.runner import RunResult, run_one
from market_game_sim.metrics.liquidation import LiquidationMetrics, RunClassification
from market_game_sim.showcase.preview import (
    DEFAULT_PLAN,
    _combined_config_hash,
    build_preview_configs,
)

EVIDENCE_CLASS = "formal-research"
PRODUCER = "0.1.5 T215"
DEFAULT_OUT = pathlib.Path("artifacts/formal/T215")

CHECKPOINT_SCHEMA_VERSION = 2
CHECKPOINT_DIR_NAME = "checkpoints"
PROGRESS_NAME = "progress.json"
ANALYSIS_NAME = "analysis.json"
RUN_MANIFEST_NAME = "run-manifest.json"


class FormalRunError(RuntimeError):
    """The formal run request or a persisted checkpoint is invalid."""


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _source_tree_sha256() -> str:
    """Bind formal evidence to every Python source file used by the package."""
    package_root = pathlib.Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(package_root.rglob("*.py"), key=lambda item: item.as_posix()):
        relative = path.relative_to(package_root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _guard_out_dir(out_dir: str | pathlib.Path) -> pathlib.Path:
    out = pathlib.Path(out_dir)
    resolved = out.resolve()
    for ancestor in (resolved, *resolved.parents):
        if ancestor.name == "experiments" and ancestor.parent.name == "docs":
            raise FormalRunError(
                f"refusing to write T215 raw checkpoints into {out.as_posix()}: "
                "docs/experiments/ is the committed delivery area owned by T220"
            )
    return out


def _checkpoint_path(out: pathlib.Path, seed: int) -> pathlib.Path:
    return out / CHECKPOINT_DIR_NAME / f"seed-{seed}.json.gz"


def _result_payload(result: RunResult) -> dict[str, Any]:
    return {
        "seed": result.seed,
        "terminated": result.terminated,
        "abort_code": result.abort_code,
        "events": result.events,
        "book_last_ticks": result.book_last_ticks,
        "classification": dataclasses.asdict(result.classification),
        "group_label": result.group_label,
        "event_summary_sha256": event_summary_sha256(result),
    }


def _analysis_result(payload: dict[str, Any]) -> RunResult:
    expected = {
        "seed",
        "terminated",
        "abort_code",
        "events",
        "book_last_ticks",
        "classification",
        "group_label",
        "event_summary_sha256",
    }
    if set(payload) != expected:
        raise FormalRunError(
            "checkpoint result fields mismatch: "
            f"missing={sorted(expected - set(payload))}, extra={sorted(set(payload) - expected)}"
        )
    if not isinstance(payload["events"], list):
        raise FormalRunError("checkpoint result.events must be a list")
    digest = event_summary_sha256(
        RunResult(
            seed=payload["seed"],
            terminated=payload["terminated"],
            abort_code=payload["abort_code"],
            events=payload["events"],
            book_last_ticks=payload["book_last_ticks"],
            accounts={},
            liquidation_metrics=LiquidationMetrics(),
            classification=RunClassification(**payload["classification"]),
            group_label=payload["group_label"],
        )
    )
    if digest != payload["event_summary_sha256"]:
        raise FormalRunError("checkpoint event digest mismatch")

    # Factorial inference only consumes trade prices/times, the final run
    # timestamp, and the stored classification.  Keep those exact inputs in
    # memory while the complete raw event stream remains in the checkpoint.
    events = [event for event in payload["events"] if event.get("event_type") == "TRADE_SETTLE"]
    final_timestamp = max(
        (
            event.get("timestamp", 0)
            for event in payload["events"]
            if type(event.get("timestamp", 0)) is int
        ),
        default=0,
    )
    events.append({"event_type": "RUN_BOUNDARY", "timestamp": final_timestamp})
    return RunResult(
        seed=payload["seed"],
        terminated=payload["terminated"],
        abort_code=payload["abort_code"],
        events=events,
        book_last_ticks=payload["book_last_ticks"],
        accounts={},
        liquidation_metrics=LiquidationMetrics(),
        classification=RunClassification(**payload["classification"]),
        group_label=payload["group_label"],
    )


def _write_checkpoint(path: pathlib.Path, body: dict[str, Any]) -> None:
    body_bytes = _canonical_json(body)
    envelope = {"body": body, "body_sha256": _sha256_bytes(body_bytes)}
    encoded = _canonical_json(envelope)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with open(temp, "wb") as raw:
        # mtime=0 keeps identical checkpoint contents byte-identical.
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
            stream.write(encoded)
        raw.flush()
    temp.replace(path)


def _read_checkpoint(path: pathlib.Path) -> dict[str, Any]:
    try:
        with gzip.open(path, "rb") as stream:
            envelope = json.loads(stream.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FormalRunError(f"cannot read checkpoint {path}: {exc}") from exc
    if not isinstance(envelope, dict) or set(envelope) != {"body", "body_sha256"}:
        raise FormalRunError(f"checkpoint envelope fields are invalid: {path}")
    body = envelope["body"]
    if _sha256_bytes(_canonical_json(body)) != envelope["body_sha256"]:
        raise FormalRunError(f"checkpoint body digest mismatch: {path}")
    if not isinstance(body, dict):
        raise FormalRunError(f"checkpoint body must be an object: {path}")
    return body


def _block_exclusion_codes(results: dict[str, dict[str, RunResult]]) -> list[str]:
    codes: set[str] = set()
    for model_id in MODEL_IDS:
        for cell_id in CELL_IDS:
            classification = results[model_id][cell_id].classification
            if classification.is_technical_invalid:
                code = classification.technical_invalid_code
                if code not in TECHNICAL_INVALID_CODES:
                    raise FormalRunError(f"unknown technical-invalid code {code!r}")
                codes.add(code)
    return sorted(codes)


def _checkpoint_body(
    *,
    seed: int,
    binding: FactorialPlanBinding,
    config_hashes: dict[str, dict[str, str]],
    results: dict[str, dict[str, RunResult]],
    audit_hashes: dict[str, dict[str, str]],
    code_version: str = __version__,
    source_tree_sha256: str | None = None,
) -> dict[str, Any]:
    if source_tree_sha256 is None:
        source_tree_sha256 = _source_tree_sha256()
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "producer": PRODUCER,
        "code_version": code_version,
        "source_tree_sha256": source_tree_sha256,
        "evidence_class": EVIDENCE_CLASS,
        "run_family": "SPONTANEOUS",
        "plan": binding.report_reference(),
        "seed": seed,
        "config_hashes": config_hashes,
        "exclusion_codes": _block_exclusion_codes(results),
        "primary_runs": {
            model_id: {cell_id: _result_payload(results[model_id][cell_id]) for cell_id in CELL_IDS}
            for model_id in MODEL_IDS
        },
        "audit_event_summary_sha256": audit_hashes,
    }


def _validate_checkpoint_body(
    body: dict[str, Any],
    *,
    seed: int,
    binding: FactorialPlanBinding,
    config_hashes: dict[str, dict[str, str]],
    expected_code_version: str = __version__,
    expected_source_tree_sha256: str | None = None,
) -> dict[str, dict[str, RunResult]]:
    if expected_source_tree_sha256 is None:
        expected_source_tree_sha256 = _source_tree_sha256()
    expected = {
        "schema_version",
        "producer",
        "code_version",
        "source_tree_sha256",
        "evidence_class",
        "run_family",
        "plan",
        "seed",
        "config_hashes",
        "exclusion_codes",
        "primary_runs",
        "audit_event_summary_sha256",
    }
    if set(body) != expected:
        raise FormalRunError(f"checkpoint {seed} fields do not match schema")
    fixed = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "producer": PRODUCER,
        "code_version": expected_code_version,
        "source_tree_sha256": expected_source_tree_sha256,
        "evidence_class": EVIDENCE_CLASS,
        "run_family": "SPONTANEOUS",
        "plan": binding.report_reference(),
        "seed": seed,
        "config_hashes": config_hashes,
    }
    for field, expected_value in fixed.items():
        if body[field] != expected_value:
            raise FormalRunError(
                f"checkpoint {seed}.{field} drifted: expected {expected_value!r}, "
                f"got {body[field]!r}"
            )
    primary = body["primary_runs"]
    if not isinstance(primary, dict) or set(primary) != set(MODEL_IDS):
        raise FormalRunError(f"checkpoint {seed}.primary_runs model set is invalid")
    results: dict[str, dict[str, RunResult]] = {}
    for model_id in MODEL_IDS:
        cells = primary[model_id]
        if not isinstance(cells, dict) or set(cells) != set(CELL_IDS):
            raise FormalRunError(f"checkpoint {seed}.{model_id} cell set is invalid")
        results[model_id] = {cell_id: _analysis_result(cells[cell_id]) for cell_id in CELL_IDS}
        for cell_id, result in results[model_id].items():
            if result.seed != seed or result.group_label != cell_id:
                raise FormalRunError(
                    f"checkpoint {seed}.{model_id}.{cell_id} seed/group label mismatch"
                )
    if body["exclusion_codes"] != _block_exclusion_codes(results):
        raise FormalRunError(f"checkpoint {seed}.exclusion_codes does not match its runs")
    audit_hashes = body["audit_event_summary_sha256"]
    if not isinstance(audit_hashes, dict) or set(audit_hashes) != set(MODEL_IDS):
        raise FormalRunError(f"checkpoint {seed} audit model set is invalid")
    for model_id in MODEL_IDS:
        if not isinstance(audit_hashes[model_id], dict) or set(audit_hashes[model_id]) != set(
            CELL_IDS
        ):
            raise FormalRunError(f"checkpoint {seed}.{model_id} audit cell set is invalid")
        for cell_id in CELL_IDS:
            primary_digest = body["primary_runs"][model_id][cell_id]["event_summary_sha256"]
            audit_mismatch = audit_hashes[model_id][cell_id] != primary_digest
            is_ti2 = (
                results[model_id][cell_id].classification.is_technical_invalid
                and results[model_id][cell_id].classification.technical_invalid_code == "TI-2"
            )
            if audit_mismatch != is_ti2:
                raise FormalRunError(
                    f"checkpoint {seed}.{model_id}.{cell_id} TI-2 digest/classification mismatch"
                )
    return results


def _execute_block(
    seed: int, binding: FactorialPlanBinding
) -> tuple[
    dict[str, dict[str, RunResult]],
    dict[str, dict[str, str]],
    dict[str, dict[str, str]],
]:
    configs = build_preview_configs(seed, binding)
    config_hashes = validate_flagship_configs(configs, binding)
    results: dict[str, dict[str, RunResult]] = {model_id: {} for model_id in MODEL_IDS}
    audit_hashes: dict[str, dict[str, str]] = {model_id: {} for model_id in MODEL_IDS}
    for model_id in MODEL_IDS:
        for cell_id in CELL_IDS:
            primary = run_one(configs[model_id][cell_id])
            audit = run_one(configs[model_id][cell_id])
            audit_hashes[model_id][cell_id] = event_summary_sha256(audit)
            if audit_deterministic_rerun(primary, audit) == "TI-2":
                primary.classification = dataclasses.replace(
                    primary.classification,
                    is_technical_invalid=True,
                    technical_invalid_code="TI-2",
                )
            results[model_id][cell_id] = primary
    return results, config_hashes, audit_hashes


def _write_json(path: pathlib.Path, payload: dict[str, Any]) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)
    return path


def _progress_payload(
    *,
    binding: FactorialPlanBinding,
    executed_seeds: list[int],
    valid_seeds: list[int],
    exclusions: dict[int, list[str]],
    complete: bool,
    exhausted: bool,
    inference_eligible: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "producer": PRODUCER,
        "code_version": __version__,
        "source_tree_sha256": _source_tree_sha256(),
        "run_family": "SPONTANEOUS",
        "evidence_class": EVIDENCE_CLASS,
        "plan": binding.report_reference(),
        "executed_seeds": executed_seeds,
        "valid_seeds": valid_seeds,
        "excluded_seed_blocks": exclusions,
        "minimum_valid_blocks": binding.seed_plan.minimum_valid_blocks,
        "evidence_sufficient": complete,
        "inference_eligible": inference_eligible,
        "stopping_rule_reached": complete or exhausted,
        "seed_pool_exhausted": exhausted,
    }


def run_formal_experiment(
    out_dir: str | pathlib.Path = DEFAULT_OUT,
    *,
    plan_path: str | pathlib.Path = DEFAULT_PLAN,
    max_new_blocks: int | None = None,
    bootstrap_resamples: int | None = None,
    sign_flip_resamples: int | None = None,
) -> dict[str, Any]:
    """Execute/resume T215 and analyze only after the frozen stopping rule.

    ``max_new_blocks`` is an operational pause boundary, not a statistical
    stopping rule.  Existing verified checkpoints are always reused.
    Resample overrides exist for tests; the CLI never exposes them.
    """
    out = _guard_out_dir(out_dir)
    if max_new_blocks is not None and (type(max_new_blocks) is not int or max_new_blocks <= 0):
        raise FormalRunError("max_new_blocks must be a positive integer when provided")
    binding = load_factorial_plan(plan_path)
    guard_evidence_class("SPONTANEOUS", EVIDENCE_CLASS)
    binding.seed_plan.validate()
    out.mkdir(parents=True, exist_ok=True)

    known = {_checkpoint_path(out, seed).resolve() for seed in binding.seed_plan.pool}
    actual = set((out / CHECKPOINT_DIR_NAME).glob("seed-*.json.gz"))
    unknown = sorted(str(path) for path in actual if path.resolve() not in known)
    if unknown:
        raise FormalRunError(
            f"checkpoint directory contains seeds outside the frozen pool: {unknown}"
        )

    collected: dict[str, dict[str, list[RunResult]]] = {
        model_id: {cell_id: [] for cell_id in CELL_IDS} for model_id in MODEL_IDS
    }
    all_hashes: dict[int, dict[str, dict[str, str]]] = {}
    executed_seeds: list[int] = []
    valid_seeds: list[int] = []
    exclusions: dict[int, list[str]] = {}
    new_blocks = 0
    saw_gap = False

    for seed in binding.seed_plan.pool:
        configs = build_preview_configs(seed, binding)
        config_hashes = validate_flagship_configs(configs, binding)
        checkpoint = _checkpoint_path(out, seed)
        if checkpoint.exists():
            if saw_gap:
                raise FormalRunError(
                    f"checkpoint gap: seed {seed} exists after an earlier missing frozen seed"
                )
            persisted = _read_checkpoint(checkpoint)
            if persisted.get("schema_version") == CHECKPOINT_SCHEMA_VERSION:
                block = _validate_checkpoint_body(
                    persisted,
                    seed=seed,
                    binding=binding,
                    config_hashes=config_hashes,
                )
            else:
                if max_new_blocks is not None and new_blocks >= max_new_blocks:
                    break
                block, config_hashes, audit_hashes = _execute_block(seed, binding)
                _write_checkpoint(
                    checkpoint,
                    _checkpoint_body(
                        seed=seed,
                        binding=binding,
                        config_hashes=config_hashes,
                        results=block,
                        audit_hashes=audit_hashes,
                    ),
                )
                new_blocks += 1
        else:
            saw_gap = True
            if max_new_blocks is not None and new_blocks >= max_new_blocks:
                break
            block, config_hashes, audit_hashes = _execute_block(seed, binding)
            _write_checkpoint(
                checkpoint,
                _checkpoint_body(
                    seed=seed,
                    binding=binding,
                    config_hashes=config_hashes,
                    results=block,
                    audit_hashes=audit_hashes,
                ),
            )
            new_blocks += 1

        executed_seeds.append(seed)
        all_hashes[seed] = config_hashes
        codes = _block_exclusion_codes(block)
        if codes:
            exclusions[seed] = codes
        else:
            valid_seeds.append(seed)
        for model_id in MODEL_IDS:
            for cell_id in CELL_IDS:
                collected[model_id][cell_id].append(block[model_id][cell_id])
        if len(valid_seeds) == binding.seed_plan.minimum_valid_blocks:
            break

    complete = len(valid_seeds) >= binding.seed_plan.minimum_valid_blocks
    exhausted = len(executed_seeds) == len(binding.seed_plan.pool) and not complete
    progress = _progress_payload(
        binding=binding,
        executed_seeds=executed_seeds,
        valid_seeds=valid_seeds,
        exclusions=exclusions,
        complete=complete,
        exhausted=exhausted,
    )
    progress_path = _write_json(out / PROGRESS_NAME, progress)

    analysis_path: pathlib.Path | None = None
    manifest_path: pathlib.Path | None = None
    if complete or exhausted:
        analysis = analyze_flagship_results(
            collected,
            binding,
            bootstrap_resamples=bootstrap_resamples,
            sign_flip_resamples=sign_flip_resamples,
        )
        inference_eligible = analysis["research_claim_eligibility"] == "eligible"
        progress = _progress_payload(
            binding=binding,
            executed_seeds=executed_seeds,
            valid_seeds=valid_seeds,
            exclusions=exclusions,
            complete=complete,
            exhausted=exhausted,
            inference_eligible=inference_eligible,
        )
        progress_path = _write_json(out / PROGRESS_NAME, progress)
        analysis_payload = {
            "schema_version": 1,
            "producer": PRODUCER,
            "run_family": "SPONTANEOUS",
            "evidence_class": EVIDENCE_CLASS,
            "inference_eligible": inference_eligible,
            "report": analysis,
        }
        analysis_path = _write_json(out / ANALYSIS_NAME, analysis_payload)
        checkpoint_digests = {
            str(seed): _sha256_bytes(_checkpoint_path(out, seed).read_bytes())
            for seed in executed_seeds
        }
        manifest = {
            "schema_version": 1,
            "producer": PRODUCER,
            "code_version": __version__,
            "source_tree_sha256": _source_tree_sha256(),
            "run_family": "SPONTANEOUS",
            "evidence_class": EVIDENCE_CLASS,
            "plan": binding.report_reference(),
            "config_hash": _combined_config_hash(all_hashes),
            "executed_seed_plan": {
                "n_seeds": len(executed_seeds),
                "seeds": executed_seeds,
            },
            "valid_seeds": valid_seeds,
            "excluded_seed_blocks": exclusions,
            "checkpoint_sha256": checkpoint_digests,
            "progress_sha256": _sha256_bytes(progress_path.read_bytes()),
            "analysis_sha256": _sha256_bytes(analysis_path.read_bytes()),
        }
        manifest_path = _write_json(out / RUN_MANIFEST_NAME, manifest)

    return {
        "out_dir": out,
        "progress": progress_path,
        "analysis": analysis_path,
        "manifest": manifest_path,
        "executed_seeds": executed_seeds,
        "valid_seeds": valid_seeds,
        "excluded_seed_blocks": exclusions,
        "new_blocks": new_blocks,
        "complete": complete,
        "exhausted": exhausted,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m market_game_sim.showcase.formal")
    parser.add_argument("--plan", default=DEFAULT_PLAN, help="frozen factorial plan JSON")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="raw T215 evidence directory")
    parser.add_argument(
        "--max-new-blocks",
        type=int,
        default=None,
        help="pause after N newly executed blocks; rerun the command to resume",
    )
    args = parser.parse_args(argv)
    result = run_formal_experiment(
        args.out,
        plan_path=args.plan,
        max_new_blocks=args.max_new_blocks,
    )
    print(
        f"T215 progress: executed={len(result['executed_seeds'])} "
        f"valid={len(result['valid_seeds'])} new={result['new_blocks']} "
        f"complete={result['complete']} out={result['out_dir']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
