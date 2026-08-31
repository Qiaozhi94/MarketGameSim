"""T217 gate R4 formal result bundle tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from market_game_sim import __version__
from market_game_sim.experiment.factorial import (
    CELL_IDS,
    ENDPOINT_FAMILIES,
    MODEL_IDS,
    event_summary_sha256,
    load_factorial_plan,
    validate_flagship_configs,
)
from market_game_sim.experiment.runner import run_one
from market_game_sim.replay.reader import read_log
from market_game_sim.showcase.evidence_index import EvidenceIndexError
from market_game_sim.showcase.formal import (
    _checkpoint_body,
    _read_checkpoint,
    _source_tree_sha256,
    _write_checkpoint,
)
from market_game_sim.showcase.manifest import validate_showcase_manifest
from market_game_sim.showcase.preview import build_preview_configs
from market_game_sim.showcase.r4 import (
    COMPARISON_NAME,
    EVIDENCE_COPY_NAME,
    LOG_NAME,
    MANIFEST_NAME,
    MAX_REPLAY_BYTES,
    REPLAY_NAME,
    REQUIRED_SUMMARY_SECTIONS,
    RUN_DOC_NAME,
    SUMMARY_NAME,
    R4BundleError,
    generate_r4_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE_INDEX = ROOT / "docs" / "experiments" / "0.1.5-evidence-index.json"
REAL_PLAN = ROOT / "docs" / "experiments" / "0.1.5-factorial-plan.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def r4_inputs(tmp_path):
    index = json.loads(SOURCE_INDEX.read_text(encoding="utf-8"))
    index["seed_plan"].update(
        {
            "evidence_sufficient": True,
            "stopping_rule_reached": True,
            "seed_pool_exhausted": False,
        }
    )
    index["code"]["package_version"] = __version__
    index["code"]["source_tree_sha256"] = _source_tree_sha256()
    evidence = tmp_path / "formal"
    checkpoints = evidence / "checkpoints"
    checkpoints.mkdir(parents=True)

    for artifact in index["source_artifacts"]:
        path = evidence / artifact["artifact"]
        path.write_text(f"synthetic {artifact['artifact']}", encoding="utf-8")
        artifact["path"] = path.as_posix()
        artifact["sha256"] = _sha256(path)

    binding = load_factorial_plan(REAL_PLAN)
    selected_seed = index["seed_plan"]["valid_seeds"][0]
    selected_path = checkpoints / f"seed-{selected_seed}.json.gz"
    configs = build_preview_configs(selected_seed, binding)
    config_hashes = validate_flagship_configs(configs, binding)
    results = {model_id: {} for model_id in MODEL_IDS}
    audit_hashes = {model_id: {} for model_id in MODEL_IDS}
    for model_id in MODEL_IDS:
        for cell_id in CELL_IDS:
            result = run_one(configs[model_id][cell_id])
            results[model_id][cell_id] = result
            audit_hashes[model_id][cell_id] = event_summary_sha256(result)
    _write_checkpoint(
        selected_path,
        _checkpoint_body(
            seed=selected_seed,
            binding=binding,
            config_hashes=config_hashes,
            results=results,
            audit_hashes=audit_hashes,
        ),
    )

    for entry in index["checkpoints"]:
        seed = int(entry["seed"])
        path = checkpoints / f"seed-{seed}.json.gz"
        if seed != selected_seed:
            path.write_bytes(f"synthetic checkpoint {seed}".encode())
        entry["path"] = path.as_posix()
        entry["sha256"] = _sha256(path)
    index_path = tmp_path / "evidence-index.json"
    _write_json(index_path, index)
    return index_path, selected_path


def test_r4_bundle_has_fixed_formal_artifact_set(tmp_path, r4_inputs):
    index_path, _ = r4_inputs
    result = generate_r4_bundle(tmp_path / "R4", evidence_index_path=index_path)
    out = result["out_dir"]
    for name in (
        COMPARISON_NAME,
        EVIDENCE_COPY_NAME,
        LOG_NAME,
        REPLAY_NAME,
        SUMMARY_NAME,
        RUN_DOC_NAME,
        MANIFEST_NAME,
    ):
        assert (out / name).is_file(), f"missing R4 artifact: {name}"
    manifest = json.loads((out / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["gate"] == "R4"
    assert manifest["evidence_class"] == "formal-research"
    assert manifest["seed_plan"]["n_seeds"] == 128
    assert len(manifest["artifacts"]) == 6
    validate_showcase_manifest(manifest)
    for entry in manifest["artifacts"]:
        assert (
            entry["hash"]
            == hashlib.blake2b((out / entry["path"]).read_bytes(), digest_size=32).hexdigest()
        )


def test_r4_summary_reports_all_formal_effects_and_boundaries(tmp_path, r4_inputs):
    index_path, _ = r4_inputs
    result = generate_r4_bundle(tmp_path / "R4", evidence_index_path=index_path)
    text = result["summary"].read_text(encoding="utf-8")
    for section in REQUIRED_SUMMARY_SECTIONS:
        assert section in text
    assert text.count("| crash |") == 12
    assert text.count("| surge |") == 12
    assert text.count("| liquidity_drought |") == 12
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for family_id in ENDPOINT_FAMILIES:
        assert f"- 判定：`{index['endpoint_results'][family_id]['status']}`" in text
    assert "不等于接受 H0" in text
    assert "不构成结果导向挑选" in text


def test_r4_replay_is_offline_bounded_and_readable(tmp_path, r4_inputs):
    index_path, _ = r4_inputs
    result = generate_r4_bundle(tmp_path / "R4", evidence_index_path=index_path)
    replay = result["replay"]
    assert replay.stat().st_size <= MAX_REPLAY_BYTES
    html = replay.read_text(encoding="utf-8")
    assert "replay-data" in html
    assert "fetch(" not in html
    assert "http://" not in html
    assert "https://" not in html
    log = read_log(result["log"])
    assert log.run_id == "exp-s40000"
    assert len(log.events) > 0


def test_r4_generation_is_byte_deterministic(tmp_path, r4_inputs):
    index_path, _ = r4_inputs
    first = generate_r4_bundle(
        tmp_path / "a", evidence_index_path=index_path, rebuild_command="rebuild-r4"
    )
    second = generate_r4_bundle(
        tmp_path / "b", evidence_index_path=index_path, rebuild_command="rebuild-r4"
    )
    for name in (
        COMPARISON_NAME,
        EVIDENCE_COPY_NAME,
        LOG_NAME,
        REPLAY_NAME,
        SUMMARY_NAME,
        RUN_DOC_NAME,
        MANIFEST_NAME,
    ):
        assert (first["out_dir"] / name).read_bytes() == (second["out_dir"] / name).read_bytes()


def test_r4_rejects_non_formal_index(tmp_path, r4_inputs):
    index_path, _ = r4_inputs
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["evidence_class"] = "experiment-preview"
    _write_json(index_path, index)
    with pytest.raises(EvidenceIndexError, match="evidence_class"):
        generate_r4_bundle(tmp_path / "R4", evidence_index_path=index_path)


def test_r4_rejects_representative_ti2_audit_drift(tmp_path, r4_inputs):
    index_path, checkpoint_path = r4_inputs
    body = _read_checkpoint(checkpoint_path)
    body["audit_event_summary_sha256"][MODEL_IDS[0]][CELL_IDS[0]] = "0" * 64
    _write_checkpoint(checkpoint_path, body)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    selected = next(entry for entry in index["checkpoints"] if entry["seed"] == "40000")
    selected["sha256"] = _sha256(checkpoint_path)
    _write_json(index_path, index)
    with pytest.raises(R4BundleError, match="TI-2 rerun digest"):
        generate_r4_bundle(tmp_path / "R4", evidence_index_path=index_path)
