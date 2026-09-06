"""Regression coverage for the H2 Q-304 feasibility evidence."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "h2_power_feasibility.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("h2_power_feasibility", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_q304_human_participant_plan_is_superseded_but_reproducible():
    evidence = _load_module().build_evidence()
    assert evidence["status"] == "SUPERSEDED_BY_SCOPE_CLARIFICATION"
    assert evidence["historical_planning_status"] == "CONSERVATIVE_GO_AT_CAP"
    assert evidence["decision"]["active_for_current_contract"] is False
    assert evidence["decision"]["participant_cap_meets_target_power"] is True
    assert [row["minimum_participants_for_target_power"] for row in evidence["results"]] == [
        49,
        90,
        130,
    ]


def test_q304_frozen_cap_power_declines_with_correlation():
    evidence = _load_module().build_evidence()
    powers = [row["power_at_participant_cap"] for row in evidence["results"]]
    assert powers == [0.998037, 0.934125, 0.80003]
    assert powers == sorted(powers, reverse=True)


def test_q304_absolute_compensation_is_no_longer_an_open_gate():
    evidence = _load_module().build_evidence()
    assert evidence["evidence_id"] == "H2-Q304-power-feasibility-v4"
    assert evidence["decision"]["next_gate"] == (
        "use H2-dual-track-contract.json and replace this human-participant power model with "
        "paired-seed calibration"
    )


def test_q304_compensation_budget_covers_frozen_population_and_contingency():
    budget = _load_module().build_evidence()["compensation_budget"]
    assert budget == {
        "currency": "USD",
        "base_compensation_per_completer": 22.0,
        "max_bonus_rate": 0.2,
        "max_bonus_per_completer": 4.4,
        "max_compensation_per_completer": 26.4,
        "pilot_participants": 8,
        "max_preassignment_screen_outs": 26,
        "screen_out_compensation_per_person": 2.0,
        "subtotal": 3695.2,
        "contingency_rate": 0.1,
        "required_after_contingency": 4064.72,
        "frozen_reserve": 4100.0,
        "platform_fees_taxes_and_fx_included": False,
        "recruitment_platform": "Prolific",
        "platform_fee_rate": 0.428,
        "platform_fee_on_frozen_reserve": 1754.8,
        "project_funding_required_before_vat_and_fx": 5854.8,
        "project_funding_reserve_before_vat_and_fx": 5900.0,
    }
