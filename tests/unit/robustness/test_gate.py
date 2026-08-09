"""T001 (0.1.2 退出清单): startup admission gate tests.

Positive + negative + multi-record cases per CLAUDE.md: each check has both a
"should pass" and a "should fail-closed" test, and the market-matrix/zero-sum
checks run over multiple seeds.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from market_game_sim.robustness.gate import (
    AdmissionGateError,
    ExitCondition,
    _evidence_target,
    artifact_digest,
    load_exit_index,
    run_gate,
    summarize_matches,
    unmet_conditions,
    verify_evidence_targets,
    verify_run_artifact,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
EXIT_INDEX = REPO_ROOT / "docs" / "experiments" / "0.1.2-exit-evidence-index.json"
RUN_ARTIFACT = REPO_ROOT / "docs" / "experiments" / "0.1.2-e6-demonstration-run.json"
SUMMARY = REPO_ROOT / "docs" / "experiments" / "0.1.2-e6-demonstration-run.md"


def _exit_index_item(cid: str, status: str = "met", evidence: list[str] | None = None) -> dict:
    return {
        "id": cid,
        "description": f"desc {cid}",
        "tasks": [f"T{cid}"],
        "status": status,
        "evidence": evidence or [],
        "notes": None,
    }


def _minimal_run_artifact() -> dict:
    return {
        "comparison": {
            "control_config_hash": "a" * 32,
            "treatment_config_hash": "b" * 32,
            "conditional_conclusion": "conclusion text",
        },
        "control_report": {
            "market_validation": {
                "per_seed": {
                    "1": {
                        "items": {
                            "fat_tails": {
                                "name": "fat_tails",
                                "verdict": "NOT_APPLICABLE",
                                "statistic": None,
                                "p_value": None,
                            }
                        }
                    }
                }
            },
            "zero_sum": {"1": {"residual_units": 0}},
        },
        "treatment_report": {
            "market_validation": {
                "per_seed": {
                    "1": {
                        "items": {
                            "fat_tails": {
                                "name": "fat_tails",
                                "verdict": "NOT_APPLICABLE",
                                "statistic": None,
                                "p_value": None,
                            }
                        }
                    }
                }
            },
            "zero_sum": {"1": {"residual_units": 0}},
        },
    }


# --- load_exit_index -------------------------------------------------------


class TestLoadExitIndex:
    def test_reads_conditions_from_file_not_hardcoded(self, tmp_path):
        p = tmp_path / "index.json"
        p.write_text(
            json.dumps(
                {"items": [_exit_index_item("E1"), _exit_index_item("E2", status="not_met")]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        conds = load_exit_index(p)
        assert [c.id for c in conds] == ["E1", "E2"]
        assert conds[0].status == "met"
        assert conds[1].status == "not_met"

    def test_missing_file_fails_closed(self, tmp_path):
        with pytest.raises(AdmissionGateError):
            load_exit_index(tmp_path / "nope.json")

    def test_malformed_json_fails_closed(self, tmp_path):
        p = tmp_path / "index.json"
        p.write_text("not json{", encoding="utf-8")
        with pytest.raises(AdmissionGateError):
            load_exit_index(p)

    def test_missing_id_fails_closed(self, tmp_path):
        p = tmp_path / "index.json"
        p.write_text(json.dumps({"items": [{"description": "no id"}]}), encoding="utf-8")
        with pytest.raises(AdmissionGateError):
            load_exit_index(p)


# --- _evidence_target ------------------------------------------------------


class TestEvidenceTarget:
    @pytest.mark.parametrize(
        "evidence,expected",
        [
            ("src/a.py::func", "src/a.py"),
            ("tests/unit/t.py::TestCase", "tests/unit/t.py"),
            ("src/pkg/ (a.py, b.py)", "src/pkg"),
            ("benchmarks/f.md §1 (x)", "benchmarks/f.md"),
            ("tools/formal_calibration.py", "tools/formal_calibration.py"),
            ("src/pkg/ (a.py, b.py)", "src/pkg"),
        ],
    )
    def test_extracts_path_token(self, evidence, expected):
        assert _evidence_target(evidence) == expected


# --- unmet_conditions ------------------------------------------------------


class TestUnmetConditions:
    def test_all_met_returns_empty(self):
        conds = [ExitCondition("E1", "d", (), "met", ()), ExitCondition("E2", "d", (), "met", ())]
        assert unmet_conditions(conds) == []

    def test_not_met_and_partially_met_both_reported(self):
        conds = [
            ExitCondition("E1", "d", (), "not_met", ()),
            ExitCondition("E2", "d", (), "partially_met", ()),
            ExitCondition("E3", "d", (), "met", ()),
        ]
        assert unmet_conditions(conds) == ["E1", "E2"]


# --- verify_evidence_targets ----------------------------------------------


class TestVerifyEvidenceTargets:
    def test_existing_targets_ok(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "t.py").write_text("", encoding="utf-8")
        conds = [ExitCondition("E1", "d", (), "met", ("src/a.py::func", "tests/t.py::T"))]
        assert verify_evidence_targets(conds, tmp_path) == []

    def test_missing_target_reported(self, tmp_path):
        conds = [ExitCondition("E1", "d", (), "met", ("src/ghost.py::f",))]
        missing = verify_evidence_targets(conds, tmp_path)
        assert missing == [("E1", "src/ghost.py")]


# --- verify_run_artifact ---------------------------------------------------


class TestVerifyRunArtifact:
    def test_valid_artifact(self):
        conclusion, seeds, verdicts_ok, residuals = verify_run_artifact(_minimal_run_artifact())
        assert conclusion == "conclusion text"
        assert seeds == ["1", "1"]
        assert verdicts_ok is True
        assert residuals == [0, 0]

    def test_missing_comparison_fails_closed(self):
        with pytest.raises(AdmissionGateError):
            verify_run_artifact({})

    def test_empty_conclusion_fails_closed(self):
        art = _minimal_run_artifact()
        art["comparison"]["conditional_conclusion"] = "   "
        with pytest.raises(AdmissionGateError):
            verify_run_artifact(art)

    def test_missing_config_hash_fails_closed(self):
        art = _minimal_run_artifact()
        del art["comparison"]["control_config_hash"]
        with pytest.raises(AdmissionGateError):
            verify_run_artifact(art)

    def test_empty_market_matrix_fails_closed(self):
        art = _minimal_run_artifact()
        art["control_report"]["market_validation"]["per_seed"]["1"]["items"] = {}
        with pytest.raises(AdmissionGateError):
            verify_run_artifact(art)

    def test_invalid_verdict_reported(self):
        art = _minimal_run_artifact()
        art["control_report"]["market_validation"]["per_seed"]["1"]["items"]["fat_tails"][
            "verdict"
        ] = "MAYBE"
        conclusion, seeds, verdicts_ok, residuals = verify_run_artifact(art)
        assert verdicts_ok is False

    def test_missing_zero_sum_fails_closed(self):
        art = _minimal_run_artifact()
        del art["control_report"]["zero_sum"]
        with pytest.raises(AdmissionGateError):
            verify_run_artifact(art)

    def test_non_int_residual_fails_closed(self):
        art = _minimal_run_artifact()
        art["control_report"]["zero_sum"]["1"]["residual_units"] = 0.5
        with pytest.raises(AdmissionGateError):
            verify_run_artifact(art)


# --- summarize_matches -----------------------------------------------------


class TestSummarizeMatches:
    def test_conclusion_in_summary(self):
        assert summarize_matches("结论 X（95% CI）", "前缀 结论X（95%CI） 后缀")

    def test_mismatch_false(self):
        assert not summarize_matches("结论 X", "完全不同的文本")


# --- artifact_digest -------------------------------------------------------


class TestArtifactDigest:
    def test_deterministic(self, tmp_path):
        p = tmp_path / "a.json"
        p.write_text(json.dumps({"b": 2, "a": 1}), encoding="utf-8")
        assert artifact_digest(p) == artifact_digest(p)

    def test_key_order_independent(self, tmp_path):
        p1 = tmp_path / "a.json"
        p2 = tmp_path / "b.json"
        p1.write_text(json.dumps({"b": 2, "a": 1}), encoding="utf-8")
        p2.write_text(json.dumps({"a": 1, "b": 2}), encoding="utf-8")
        assert artifact_digest(p1) == artifact_digest(p2)


# --- run_gate (end-to-end) -------------------------------------------------


class TestRunGate:
    def test_real_artifacts_pass(self):
        result = run_gate(EXIT_INDEX, RUN_ARTIFACT, SUMMARY, REPO_ROOT)
        assert result.unmet == []
        assert result.missing_evidence == []
        assert result.matrix_verdicts_ok is True
        assert result.zero_sum_ok is True
        assert result.conclusion_matches_summary is True
        assert len(result.zero_sum_residuals) >= 10  # 2 groups x 5 seeds
        assert result.artifact_digest

    def test_unmet_condition_fails_closed(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(
            json.dumps({"items": [_exit_index_item("E1", status="not_met")]}),
            encoding="utf-8",
        )
        art = tmp_path / "run.json"
        art.write_text(json.dumps(_minimal_run_artifact()), encoding="utf-8")
        with pytest.raises(AdmissionGateError, match="unmet"):
            run_gate(idx, art, None, tmp_path)

    def test_missing_evidence_fails_closed(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(
            json.dumps({"items": [_exit_index_item("E1", evidence=["src/ghost.py::f"])]}),
            encoding="utf-8",
        )
        art = tmp_path / "run.json"
        art.write_text(json.dumps(_minimal_run_artifact()), encoding="utf-8")
        with pytest.raises(AdmissionGateError, match="missing"):
            run_gate(idx, art, None, tmp_path)

    def test_nonzero_residual_fails_closed(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps({"items": [_exit_index_item("E1")]}), encoding="utf-8")
        art = _minimal_run_artifact()
        art["control_report"]["zero_sum"]["1"]["residual_units"] = 7
        p = tmp_path / "run.json"
        p.write_text(json.dumps(art), encoding="utf-8")
        with pytest.raises(AdmissionGateError, match="residual"):
            run_gate(idx, p, None, tmp_path)

    def test_summary_mismatch_fails_closed(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps({"items": [_exit_index_item("E1")]}), encoding="utf-8")
        p = tmp_path / "run.json"
        p.write_text(json.dumps(_minimal_run_artifact()), encoding="utf-8")
        summary = tmp_path / "summary.md"
        summary.write_text("完全不相关的内容", encoding="utf-8")
        with pytest.raises(AdmissionGateError, match="summary"):
            run_gate(idx, p, summary, tmp_path)
