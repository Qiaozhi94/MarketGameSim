"""§2.6 regression: endpoint_samples must participate in the report stats.

Round reviews found experiment/runner.py::build_study_report collected
``endpoint_samples`` (margin_ratio_bp, leverage_bp) at the moment each run
hit an economic endpoint, but only ever used their COUNT
(``n_endpoint_samples``) -- the actual values were computed and discarded,
so Part 1 (endpoint severity) had no margin/leverage characterization
analogous to what Part 2 already provides for the continuous regime.
"""

from __future__ import annotations

from market_game_sim.ledger.account import Account
from market_game_sim.metrics.liquidation import RunClassification
from market_game_sim.metrics.report import (
    _sample_stats,
    build_continuous_part,
    build_endpoint_part,
    build_report,
    build_zero_sum_declaration,
)


def test_sample_stats_empty_list():
    n, mean_m, null_m, mean_l, null_l = _sample_stats([])
    assert (n, mean_m, null_m, mean_l, null_l) == (0, 0.0, 0.0, 0.0, 0.0)


def test_sample_stats_computes_mean_and_null_ratio():
    samples = [(1000, 500), (2000, None), (None, 700)]
    n, mean_m, null_m, mean_l, null_l = _sample_stats(samples)
    assert n == 3
    assert mean_m == 1500.0  # (1000+2000)/2, None excluded
    assert null_m == 1 / 3
    assert mean_l == 600.0  # (500+700)/2
    assert null_l == 1 / 3


def test_sample_stats_all_none_gives_zero_means_full_null():
    samples = [(None, None), (None, None)]
    n, mean_m, null_m, mean_l, null_l = _sample_stats(samples)
    assert n == 2
    assert mean_m == 0.0
    assert null_m == 1.0
    assert mean_l == 0.0
    assert null_l == 1.0


def test_build_endpoint_part_uses_endpoint_samples_for_margin_and_leverage():
    """Positive case: real endpoint_samples must flow through to
    mean_margin_ratio_bp/mean_leverage_bp on the returned EndpointPart."""
    classifications = [RunClassification(is_economic_endpoint=True, breached=True)]
    endpoint_samples = [(200, 8000), (400, 6000)]
    part = build_endpoint_part(classifications, metrics_list=[], endpoint_samples=endpoint_samples)
    assert part.n_samples == 2
    assert part.mean_margin_ratio_bp == 300.0
    assert part.mean_leverage_bp == 7000.0


def test_build_endpoint_part_no_samples_defaults_to_zero():
    """Negative/contrast case: omitting endpoint_samples (or passing an
    empty list) must not crash and must report zeroed-out stats, not
    silently reuse stale/wrong values."""
    classifications = [RunClassification(is_economic_endpoint=False)]
    part = build_endpoint_part(classifications, metrics_list=[])
    assert part.n_samples == 0
    assert part.mean_margin_ratio_bp == 0.0
    assert part.mean_leverage_bp == 0.0


def test_build_report_wires_endpoint_samples_through():
    classifications = [RunClassification(is_economic_endpoint=True, breached=False)]
    endpoint_samples = [(100, 9000)]
    report = build_report(
        classifications, metrics_list=[], valid_samples=[], endpoint_samples=endpoint_samples
    )
    assert report.endpoint.n_samples == 1
    assert report.endpoint.mean_margin_ratio_bp == 100.0
    assert report.endpoint.mean_leverage_bp == 9000.0


def test_build_continuous_part_no_samples_gives_the_no_valid_samples_note():
    part = build_continuous_part([])
    assert part.n_samples == 0
    assert part.valid_sample_note == "no valid samples"


def test_build_continuous_part_low_null_ratio_gives_no_warning_note():
    """Positive case: well-populated samples (null ratio <= 30%) must not
    trigger either warning clause."""
    samples = [(100, 8000), (200, 7000), (300, 6000), (400, 5000)]
    part = build_continuous_part(samples)
    assert part.null_ratio_margin_ratio == 0.0
    assert part.null_ratio_leverage == 0.0
    assert part.valid_sample_note == ""


def test_build_continuous_part_high_margin_null_ratio_warns():
    """Negative/contrast case: >30% of margin_ratio_bp entries null must
    surface in valid_sample_note so a downstream reader doesn't trust a
    mean computed from a starved sample."""
    samples = [(None, 8000), (None, 7000), (None, 6000), (100, 5000)]
    part = build_continuous_part(samples)
    assert part.null_ratio_margin_ratio == 0.75
    assert "margin_ratio null > 30%" in part.valid_sample_note


def test_build_continuous_part_high_leverage_null_ratio_warns():
    samples = [(100, None), (200, None), (300, None), (400, 5000)]
    part = build_continuous_part(samples)
    assert part.null_ratio_leverage == 0.75
    assert "leverage null > 30%" in part.valid_sample_note


def test_build_continuous_part_both_null_ratios_high_warns_for_both():
    samples = [(None, None), (None, None), (None, None), (100, 5000)]
    part = build_continuous_part(samples)
    assert "margin_ratio null > 30%" in part.valid_sample_note
    assert "leverage null > 30%" in part.valid_sample_note


# ---------------------------------------------------------------------------
# build_zero_sum_declaration (KPI-011, PRD §13.4)
# ---------------------------------------------------------------------------


def _account(agent_id: str, wallet: int, entry: int = 0) -> Account:
    return Account(agent_id=agent_id, wallet_units=wallet, entry_notional_units=entry)


def test_zero_sum_declaration_identity_holds_with_consistent_fees():
    """Positive case: A wins 50, B loses 60, exchange collects 10 in fees --
    residual must be exactly 0 (the identity genuinely holds)."""
    accounts = {"A": _account("A", 1050), "B": _account("B", 940)}
    initial_wallets = {"A": 1000, "B": 1000}
    decl = build_zero_sum_declaration(
        accounts, initial_wallets, exchange_fee_units=10, exchange_risk_pnl_units=0
    )
    assert decl.total_pnl_units == -10
    assert decl.expected_negative_fees_units == -10
    assert decl.residual_units == 0
    assert decl.per_agent_pnl_units == {"A": 50, "B": -60}


def test_zero_sum_declaration_includes_exchange_risk_pnl_in_the_identity():
    """Positive case with a nonzero exchange_risk_pnl_units (e.g. a
    bankruptcy write-off the exchange absorbed): the identity must fold
    it in alongside fees, not just fees alone."""
    accounts = {"A": _account("A", 1030), "B": _account("B", 950)}
    initial_wallets = {"A": 1000, "B": 1000}
    # total_pnl = 30 + (-50) = -20; split between fees (10) and a
    # bankruptcy write-off the exchange absorbed (10).
    decl = build_zero_sum_declaration(
        accounts, initial_wallets, exchange_fee_units=10, exchange_risk_pnl_units=10
    )
    assert decl.total_pnl_units == -20
    assert decl.expected_negative_fees_units == -20
    assert decl.residual_units == 0


def test_zero_sum_declaration_residual_nonzero_when_fees_are_wrong():
    """Negative/contrast case: same account states but the caller passes the
    WRONG exchange_fee_units -- residual must reflect the mismatch (proves
    this isn't a vacuous always-zero computation)."""
    accounts = {"A": _account("A", 1050), "B": _account("B", 940)}
    initial_wallets = {"A": 1000, "B": 1000}
    decl = build_zero_sum_declaration(
        accounts, initial_wallets, exchange_fee_units=5, exchange_risk_pnl_units=0
    )
    assert decl.residual_units == -5


def test_zero_sum_declaration_text_mentions_win_loss_counts():
    accounts = {
        "A": _account("A", 1050),
        "B": _account("B", 940),
        "C": _account("C", 1000),  # flat
    }
    initial_wallets = {"A": 1000, "B": 1000, "C": 1000}
    decl = build_zero_sum_declaration(
        accounts, initial_wallets, exchange_fee_units=10, exchange_risk_pnl_units=0
    )
    assert "1 个代理净亏损" in decl.declaration_text
    assert "1 个代理净盈利" in decl.declaration_text
    assert "不是研究发现" in decl.declaration_text


def test_zero_sum_declaration_missing_initial_wallet_defaults_to_zero():
    """Edge case: an agent with no recorded initial baseline (e.g. a
    bench/shock.py-style synthetic participant) is treated as starting at 0,
    not silently excluded from the sum."""
    accounts = {"ghost": _account("ghost", 100)}
    decl = build_zero_sum_declaration(
        accounts, initial_baseline={}, exchange_fee_units=0, exchange_risk_pnl_units=0
    )
    assert decl.per_agent_pnl_units == {"ghost": 100}


def test_zero_sum_declaration_pre_positioned_account_uses_wallet_minus_entry_baseline():
    """Regression: a bench/leverage_seed.py-style pre-positioned account
    starts with a NONZERO entry_notional (already holding a leveraged
    position at t=0) -- the baseline must be wallet-minus-entry at t=0, not
    just the starting wallet, or the account's pre-existing notional
    exposure gets miscounted as a fabricated loss."""
    # victim starts wallet=5000, position=500 @ entry=100 -> entry_notional=50000
    # (acceptance-vectors.md 案例7 units); baseline = 5000 - 50000 = -45000.
    victim_start = _account("victim", wallet=5000, entry=50000)
    baseline = {"victim": victim_start.wallet_units - victim_start.entry_notional_units}
    # after price moves against it: wallet drops to 3390.8-equivalent (3391,
    # rounding aside), entry reduces to 30000 (partial close per Case 7).
    victim_after = _account("victim", wallet=3391, entry=30000)
    decl = build_zero_sum_declaration(
        {"victim": victim_after}, baseline, exchange_fee_units=0, exchange_risk_pnl_units=0
    )
    # PnL = (3391 - 30000) - (5000 - 50000) = -26609 - (-45000) = 18391
    assert decl.per_agent_pnl_units["victim"] == 18391
