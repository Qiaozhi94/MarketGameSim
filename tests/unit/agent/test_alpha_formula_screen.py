"""0.4.1 T974 (FR-504 / AC-508): Alpha101 formula screener.

Positive side: real Alpha101 pure time-series formulas pass.  Negative side:
formulas with ``rank`` / ``IndNeutralize`` / ``cap`` (and industry inputs,
unknown operators/inputs, bad arity, bad syntax) are rejected with a stable
reason code, and the assembly gate raises instead of passing them through.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from market_game_sim.agent import alpha_screen as a
from market_game_sim.agent.alpha_screen import (
    AlphaScreenError,
    require_accepted,
    screen_formula,
    screen_formulas,
)

# Real Alpha101 formulas (Kakushadze 2015) that use only time-series operators.
PURE_TIME_SERIES = {
    "alpha006": "(-1 * correlation(open, volume, 10))",
    "alpha009": (
        "((0 < ts_min(delta(close, 1), 5)) ? delta(close, 1) : "
        "((ts_max(delta(close, 1), 5) < 0) ? delta(close, 1) : (-1 * delta(close, 1))))"
    ),
    "alpha012": "(sign(delta(volume, 1)) * (-1 * delta(close, 1)))",
    "alpha021": (
        "((((sum(close, 8) / 8) + stddev(close, 8)) < (sum(close, 2) / 2)) ? (-1 * 1) : "
        "(((sum(close, 2) / 2) < ((sum(close, 8) / 8) - stddev(close, 8))) ? 1 : "
        "(((1 < (volume / adv20)) || ((volume / adv20) == 1)) ? 1 : (-1 * 1))))"
    ),
    "alpha023": "(((sum(high, 20) / 20) < high) ? (-1 * delta(high, 2)) : 0)",
    "alpha041": "(((high * low)^0.5) - vwap)",
    "alpha053": "(-1 * delta((((close - low) - (high - close)) / (close - low)), 9))",
    "alpha054": "((-1 * ((low - close) * (open^5))) / ((low - high) * (close^5)))",
    "alpha101": "((close - open) / ((high - low) + .001))",
}

# Real Alpha101 formulas that must be rejected, with the expected left-most code.
REJECTED = {
    "alpha001": (
        "(rank(Ts_ArgMax(SignedPower(((returns < 0) ? stddev(returns, 20) : close), 2.), 5))"
        " - 0.5)",
        a.CROSS_SECTIONAL_OPERATOR,
    ),
    "alpha003": ("(-1 * correlation(rank(open), rank(volume), 10))", a.CROSS_SECTIONAL_OPERATOR),
    "alpha004": ("(-1 * Ts_Rank(rank(low), 9))", a.CROSS_SECTIONAL_OPERATOR),
    "alpha058": (
        "(-1 * Ts_Rank(decay_linear(correlation(IndNeutralize(vwap, IndClass.sector), "
        "volume, 3.92795), 7.89291), 5.50322))",
        a.CROSS_SECTIONAL_OPERATOR,
    ),
}


@pytest.mark.parametrize("name", sorted(PURE_TIME_SERIES))
def test_pure_time_series_alpha_accepted(name: str) -> None:
    result = screen_formula(PURE_TIME_SERIES[name])
    assert result.accepted, result.detail
    assert result.reason_code is None
    assert result.violations == ()
    assert require_accepted(PURE_TIME_SERIES[name]) == result


@pytest.mark.parametrize("name", sorted(REJECTED))
def test_cross_sectional_alpha_rejected(name: str) -> None:
    formula, code = REJECTED[name]
    result = screen_formula(formula)
    assert not result.accepted
    assert result.reason_code == code
    with pytest.raises(AlphaScreenError) as exc:
        require_accepted(formula)
    assert exc.value.code == code


def test_alpha058_reports_every_violation_in_source_order() -> None:
    result = screen_formula(REJECTED["alpha058"][0])
    codes = [(v.code, v.name) for v in result.violations]
    assert codes == [
        (a.CROSS_SECTIONAL_OPERATOR, "indneutralize"),
        (a.INDUSTRY_INPUT, "indclass.sector"),
    ]


@pytest.mark.parametrize(
    ("formula", "code", "name"),
    [
        ("(returns * cap)", a.MARKET_CAP_INPUT, "cap"),
        ("(close / CAP)", a.MARKET_CAP_INPUT, "cap"),
        ("(close - IndClass.industry)", a.INDUSTRY_INPUT, "indclass.industry"),
        ("scale(delta(close, 1))", a.CROSS_SECTIONAL_OPERATOR, "scale"),
        ("RANK(close)", a.CROSS_SECTIONAL_OPERATOR, "rank"),
        ("indneutralize(close, IndClass.subindustry)", a.CROSS_SECTIONAL_OPERATOR, "indneutralize"),
        ("ts_skew(close, 10)", a.UNKNOWN_OPERATOR, "ts_skew"),
        ("close(5)", a.UNKNOWN_OPERATOR, "close"),
        ("(close - fundamental_value)", a.UNKNOWN_INPUT, "fundamental_value"),
        ("delta", a.UNKNOWN_INPUT, "delta"),
        ("delta(close)", a.ARITY_MISMATCH, "delta"),
        ("correlation(open, volume, 10, 1)", a.ARITY_MISMATCH, "correlation"),
    ],
)
def test_rejected_with_stable_code(formula: str, code: str, name: str) -> None:
    result = screen_formula(formula)
    assert not result.accepted
    assert result.reason_code == code
    assert result.violations[0].name == name


@pytest.mark.parametrize(
    "formula",
    [
        "",
        "   ",
        "(close - open",
        "close - open)",
        "delta(close, 1",
        "close +",
        "a ? b",
        "close $ open",
        "correlation(open,, 10)",
        "close open",
    ],
)
def test_syntax_error_rejected(formula: str) -> None:
    result = screen_formula(formula)
    assert not result.accepted
    assert result.reason_code == a.SYNTAX_ERROR
    with pytest.raises(AlphaScreenError) as exc:
        require_accepted(formula)
    assert exc.value.code == a.SYNTAX_ERROR


def test_non_string_formula_fails_closed() -> None:
    result = screen_formula(None)  # type: ignore[arg-type]
    assert not result.accepted
    assert result.reason_code == a.SYNTAX_ERROR


def test_excessive_nesting_fails_closed_without_recursion_error() -> None:
    formula = "(" * 5000 + "close" + ")" * 5000
    result = screen_formula(formula)
    assert result.reason_code == a.SYNTAX_ERROR
    assert "nested" in result.detail


def test_case_and_whitespace_insensitive() -> None:
    compact = "(-1*CORRELATION(Open,VOLUME,10))"
    spaced = "  ( -1 *\n\tcorrelation ( open ,  volume , 10 ) )  "
    r1, r2 = screen_formula(compact), screen_formula(spaced)
    assert r1.accepted and r2.accepted
    assert r1.operators == r2.operators == frozenset({"correlation"})
    assert r1.inputs == r2.inputs == frozenset({"open", "volume"})


def test_deep_nesting_within_limit_accepted() -> None:
    formula = "close"
    for _ in range(20):
        formula = f"delay(abs({formula}), 1)"
    assert screen_formula(formula).accepted


def test_batch_screen_preserves_order_and_mixes_results() -> None:
    batch = [
        PURE_TIME_SERIES["alpha012"],
        REJECTED["alpha003"][0],
        "(returns * cap)",
        PURE_TIME_SERIES["alpha101"],
        "(close - open",
        PURE_TIME_SERIES["alpha041"],
    ]
    results = screen_formulas(batch)
    assert len(results) == len(batch)
    assert [r.formula for r in results] == batch
    assert [r.reason_code for r in results] == [
        None,
        a.CROSS_SECTIONAL_OPERATOR,
        a.MARKET_CAP_INPUT,
        None,
        a.SYNTAX_ERROR,
        None,
    ]
    # Screening is pure: re-screening gives identical results.
    assert screen_formulas(batch) == results
    assert screen_formulas(iter(batch)) == results


# --------------------------------------------------------------------------- #
# Frozen corpus: all 101 formulas of arXiv:1601.00991, spec Q-502
# --------------------------------------------------------------------------- #

CORPUS = json.loads(Path(__file__).with_name("alpha101_corpus.json").read_text(encoding="utf-8"))
CORPUS_FORMULAS: list[str] = CORPUS["formulas"]

# The numbers spec Q-502 freezes.  They are literals here on purpose: if the
# screener's verdict moves, spec and test must be updated together.
FROZEN_ACCEPTED = (6, 7, 9, 12, 21, 23, 24, 26, 35, 41, 43, 46, 49, 51, 53, 54, 84, 101)
FROZEN_CODE_COUNTS = {
    a.CROSS_SECTIONAL_OPERATOR: 83,
    a.INDUSTRY_INPUT: 18,
    a.MARKET_CAP_INPUT: 1,
}


def test_frozen_corpus_holds_the_whole_paper() -> None:
    assert len(CORPUS_FORMULAS) == 101
    for i, formula in enumerate(CORPUS_FORMULAS, 1):
        assert formula.strip() == formula and formula, f"Alpha#{i} is blank or padded"
        assert formula.isascii(), f"Alpha#{i} carries non-ASCII text"
        assert formula.count("(") == formula.count(")"), f"Alpha#{i} has unbalanced parens"


def test_frozen_corpus_agrees_with_the_hand_written_cases() -> None:
    """The two data sets in this file must not drift apart."""
    hand_written = {name: text for name, text in PURE_TIME_SERIES.items()}
    hand_written.update({name: text for name, (text, _) in REJECTED.items()})
    for name, text in sorted(hand_written.items()):
        number = int(name.removeprefix("alpha"))
        assert " ".join(text.split()) == CORPUS_FORMULAS[number - 1], name


def test_screening_the_corpus_reproduces_the_frozen_verdicts() -> None:
    results = screen_formulas(CORPUS_FORMULAS)
    accepted = tuple(n for n, r in enumerate(results, 1) if r.accepted)
    assert accepted == FROZEN_ACCEPTED
    assert accepted == tuple(CORPUS["expected_accepted"])

    reason_codes = {str(n): r.reason_code for n, r in enumerate(results, 1) if not r.accepted}
    assert reason_codes == CORPUS["expected_reason_codes"]

    violation_codes = {
        str(n): sorted({v.code for v in r.violations})
        for n, r in enumerate(results, 1)
        if not r.accepted
    }
    assert violation_codes == CORPUS["expected_violation_codes"]


def test_frozen_counts_match_spec_q502() -> None:
    results = screen_formulas(CORPUS_FORMULAS)
    assert len(FROZEN_ACCEPTED) == 18
    assert sum(1 for r in results if not r.accepted) == 83

    counts: dict[str, int] = {}
    for result in results:
        for code in {v.code for v in result.violations}:
            counts[code] = counts.get(code, 0) + 1
    assert counts == FROZEN_CODE_COUNTS
    assert counts == CORPUS["expected_code_counts"]


def test_accepted_subset_is_free_of_cross_sectional_constructs() -> None:
    """Positive side of the freeze: the 18 really are pure time-series."""
    for number in FROZEN_ACCEPTED:
        result = require_accepted(CORPUS_FORMULAS[number - 1])
        assert result.operators <= set(a.TIME_SERIES_OPERATORS), number
        assert not result.operators & a.CROSS_SECTIONAL_OPERATORS, number
        assert not result.inputs & (a.MARKET_CAP_INPUTS | a.INDUSTRY_INPUTS), number


def test_rejected_subset_fails_the_assembly_gate() -> None:
    """Negative side: every other formula raises, carrying its frozen code."""
    rejected = [n for n in range(1, 102) if n not in FROZEN_ACCEPTED]
    assert len(rejected) == 83
    for number in rejected:
        with pytest.raises(AlphaScreenError) as excinfo:
            require_accepted(CORPUS_FORMULAS[number - 1])
        assert excinfo.value.code == CORPUS["expected_reason_codes"][str(number)]
