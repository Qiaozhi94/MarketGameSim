"""T220 / AC-011 / AC-012: R5 clean-checkout delivery entry."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from market_game_sim.showcase.evidence_index import EvidenceIndexError
from market_game_sim.showcase.manifest import validate_showcase_manifest
from market_game_sim.showcase.r2 import REBUILD_COMMAND as R2_REBUILD_COMMAND
from market_game_sim.showcase.r2 import generate_r2_bundle
from market_game_sim.showcase.r5 import (
    BUNDLE_FILES,
    DOC_REPLAY_NAME,
    DOC_REPORT_NAME,
    MAX_REPLAY_BYTES,
    generate_r5_delivery,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_INDEX = ROOT / "docs" / "experiments" / "0.1.5-evidence-index.json"
README_LABELS = {
    "正式总结报告",
    "代表性离线回放",
    "限制与失效边界",
    "正式 evidence index",
}


def _blake2b(path: Path) -> str:
    return hashlib.blake2b(path.read_bytes(), digest_size=32).hexdigest()


def _readme_delivery_links(readme: Path) -> dict[str, str]:
    links = dict(re.findall(r"\[([^]]+)]\(([^)]+)\)", readme.read_text(encoding="utf-8")))
    return {label: links[label] for label in README_LABELS}


def _assert_delivery(root: Path) -> None:
    bundle = root / "artifacts" / "showcase" / "R5"
    docs = root / "docs" / "experiments"
    assert {path.name for path in bundle.iterdir() if path.is_file()} == set(BUNDLE_FILES)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    validate_showcase_manifest(manifest)
    assert manifest["gate"] == "R5"
    assert manifest["evidence_class"] == "formal-research"
    assert manifest["seed_plan"]["n_seeds"] == 128
    for entry in manifest["artifacts"]:
        assert _blake2b(bundle / entry["path"]) == entry["hash"]

    links = _readme_delivery_links(root / "README.md")
    assert set(links) == README_LABELS
    for target in links.values():
        path_text, _, anchor = target.partition("#")
        path = root / path_text
        assert path.is_file(), f"README delivery link is broken: {target}"
        assert path.resolve().is_relative_to(root.resolve())
        if anchor:
            assert f"## {anchor}" in path.read_text(encoding="utf-8")

    report = (docs / DOC_REPORT_NAME).read_text(encoding="utf-8")
    assert "## 限制与失效边界" in report
    assert "## 版本签收" in report
    assert "formal-research" in report
    replay = docs / DOC_REPLAY_NAME
    assert replay.stat().st_size <= MAX_REPLAY_BYTES
    html = replay.read_text(encoding="utf-8")
    assert "replay-data" in html
    assert "fetch(" not in html
    assert "http://" not in html
    assert "https://" not in html


def test_single_command_generates_r5_bundle_and_repository_delivery(tmp_path):
    result = generate_r5_delivery(
        tmp_path / "artifacts" / "showcase" / "R5",
        evidence_index_path=EVIDENCE_INDEX,
        docs_dir=tmp_path / "docs" / "experiments",
        rebuild_command="rebuild-r5",
    )
    assert result["representative_seed"] == 30_000
    assert result["replay"].stat().st_size <= MAX_REPLAY_BYTES
    assert set(BUNDLE_FILES) == {path.name for path in result["out_dir"].iterdir()}


def test_r2_has_a_concrete_single_command(tmp_path):
    result = generate_r2_bundle(tmp_path / "R2")
    run_doc = result["run_doc"].read_text(encoding="utf-8")
    manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))
    assert R2_REBUILD_COMMAND in run_doc
    assert "<config.yaml>" not in run_doc
    assert manifest["gate"] == "R2"
    assert manifest["evidence_class"] == "engineering-demonstration"


def test_r5_generation_is_byte_deterministic(tmp_path):
    first = generate_r5_delivery(
        tmp_path / "a" / "bundle",
        evidence_index_path=EVIDENCE_INDEX,
        docs_dir=tmp_path / "a" / "docs",
        rebuild_command="rebuild-r5",
    )
    second = generate_r5_delivery(
        tmp_path / "b" / "bundle",
        evidence_index_path=EVIDENCE_INDEX,
        docs_dir=tmp_path / "b" / "docs",
        rebuild_command="rebuild-r5",
    )
    for name in BUNDLE_FILES:
        assert (first["out_dir"] / name).read_bytes() == (second["out_dir"] / name).read_bytes()
    for name in (DOC_REPORT_NAME, DOC_REPLAY_NAME):
        assert (first["docs_dir"] / name).read_bytes() == (second["docs_dir"] / name).read_bytes()


def test_r5_rejects_non_formal_evidence(tmp_path):
    index = json.loads(EVIDENCE_INDEX.read_text(encoding="utf-8"))
    index["evidence_class"] = "experiment-preview"
    bad_index = tmp_path / "bad-index.json"
    bad_index.write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(EvidenceIndexError, match="evidence_class"):
        generate_r5_delivery(
            tmp_path / "bundle",
            evidence_index_path=bad_index,
            docs_dir=tmp_path / "docs",
        )


def test_clean_checkout_command_needs_no_artifacts_and_all_readme_links_work(tmp_path):
    checkout = tmp_path / "checkout"

    def ignore(_directory: str, names: list[str]) -> set[str]:
        ignored = {".git", ".pytest_cache", ".ruff_cache", "__pycache__", "artifacts"}
        return set(names) & ignored

    shutil.copytree(ROOT, checkout, ignore=ignore)
    docs = checkout / "docs" / "experiments"
    for name in (DOC_REPORT_NAME, DOC_REPLAY_NAME):
        (docs / name).unlink(missing_ok=True)
    assert not (checkout / "artifacts").exists()
    index = json.loads((docs / "0.1.5-evidence-index.json").read_text(encoding="utf-8"))
    assert any(not (checkout / entry["path"]).exists() for entry in index["source_artifacts"])

    env = os.environ.copy()
    env["PYTHONPATH"] = str(checkout / "src")
    completed = subprocess.run(
        [sys.executable, "-m", "market_game_sim.showcase.r5"],
        cwd=checkout,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    _assert_delivery(checkout)
