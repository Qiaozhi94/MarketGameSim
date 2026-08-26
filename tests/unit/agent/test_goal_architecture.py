"""T204 / ADR-003 acceptance gate 1: the goal layer cannot read institutional fields.

ADR-003 §1 freezes the invariant that goal formation must NOT read
``leverage_tier`` / ``initial_bp`` / ``maint_bp`` / ``L`` / ``M`` / ``arm_id``
(or their code forms ``l_level`` / ``m_level``).  This module enforces it
**statically** by parsing ``agent/goal.py`` with :mod:`ast` and asserting no
forbidden identifier appears as a *code* Name / attribute -- docstring text and
comments are ignored (they explain the boundary; they are not a read).

A negative control proves the check is not a tautology: ``agent/constraint.py``
(the institutional layer) DOES reference those identifiers, and the same check
flags them there.  A construction test proves the goal layer operates with only
the permitted input types (``InformationSetV1`` / ``AgentInternalStateV1`` /
``AgentPreferences``), which structurally carry no institutional fields.
"""

from __future__ import annotations

import ast
import pathlib

from market_game_sim.agent import constraint as constraint_mod
from market_game_sim.agent.goal import (
    AgentInternalStateV1,
    AgentPreferences,
    BookTop,
    InformationSetV1,
    OwnAccountView,
    RiskBudgetLinearV1,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]
GOAL_SRC = ROOT / "src" / "market_game_sim" / "agent" / "goal.py"
CONSTRAINT_SRC = ROOT / "src" / "market_game_sim" / "agent" / "constraint.py"

# Code forms of the institutional / experiment-arm fields forbidden in the goal
# layer (ADR-003 §1; run_family_matrix fields l_level / m_level).  Note ``L``
# and ``M`` are the contract's arm labels; in code they appear as ``l_level``
# / ``m_level``, so those are the identifiers checked here.
FORBIDDEN_IN_GOAL = {
    "leverage_tier",
    "initial_bp",
    "maint_bp",
    "arm_id",
    "l_level",
    "m_level",
}


def _code_identifiers(source_path: pathlib.Path) -> set[str]:
    """Return the set of identifiers appearing as *code* Name / Attribute nodes.

    Docstrings (ast.Expr -> ast.Constant) and comments are NOT Names, so their
    text is excluded -- a docstring that *mentions* ``leverage_tier`` while
    explaining the boundary does not trip the check.  Only actual reads /
    references in code count.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.arg, ast.keyword)):  # function parameters
            names.add(node.arg)
    return names


# --------------------------------------------------------------------------- #
# Positive: goal.py references none of the forbidden identifiers
# --------------------------------------------------------------------------- #


def test_goal_layer_has_no_institutional_field_references():
    """ADR-003 §1: goal formation must not read leverage / margin / arm fields.
    The goal module's *code* must not reference any forbidden identifier."""
    code_names = _code_identifiers(GOAL_SRC)
    leaks = code_names & FORBIDDEN_IN_GOAL
    assert not leaks, (
        f"goal layer leaks institutional fields into goal formation: {sorted(leaks)}; "
        "these must live only in agent/constraint.py (the institutional layer)"
    )


def test_own_account_view_structurally_excludes_institutional_fields():
    """The permitted account view carries ONLY wallet / position / entry --
    no leverage_tier / initial_bp / maint_bp / arm field is even reachable."""
    import dataclasses

    fields = {f.name for f in dataclasses.fields(OwnAccountView)}
    assert fields == {"wallet_units", "position_units", "entry_notional_units"}
    assert not (fields & FORBIDDEN_IN_GOAL)


def test_information_set_and_preferences_expose_no_institutional_fields():
    """The full goal-model input surface carries no institutional field."""
    import dataclasses

    iset_fields = {f.name for f in dataclasses.fields(InformationSetV1)}
    prefs_fields = {f.name for f in dataclasses.fields(AgentPreferences)}
    assert not (iset_fields & FORBIDDEN_IN_GOAL)
    assert prefs_fields == {"risk_appetite_x1000"}


def test_goal_model_runs_with_only_permitted_inputs():
    """Construction test: a goal model decides using ONLY InformationSetV1 /
    AgentInternalStateV1 / AgentPreferences -- proving the goal layer does not
    NEED institutional inputs (ADR-003 §1 acceptance gate 1)."""
    own = OwnAccountView(wallet_units=1_000_000, position_units=0, entry_notional_units=0)
    book = BookTop(best_bid=100, best_ask=100, valuation_mark_half_ticks=200)
    iset = InformationSetV1(
        schema_version=1,
        cursor_from_event_id="",
        cursor_to_event_id="",
        public_trades=(),
        completed_bars=(),
        book_top=book,
        own_account=own,
    )
    state = AgentInternalStateV1(
        schema_version=1,
        last_seen_market_event_id="",
        ewma_value_units=None,
        ewma_sample_count=1000,
        model_private_state={"signal_bp": 2500},
    )
    prefs = AgentPreferences(risk_appetite_x1000=2000)
    decision = RiskBudgetLinearV1().decide(iset, state, prefs)
    assert decision.desired_position_units == 5000  # golden vector linear_long


# --------------------------------------------------------------------------- #
# Negative control: the same check WOULD flag constraint.py (proves the test
# is not a tautology -- the institutional layer legitimately reads these)
# --------------------------------------------------------------------------- #


def test_negative_control_constraint_layer_does_reference_institutional_fields():
    """constraint.py is the institutional layer and MUST be allowed to read
    ``maint_bp`` / ``leverage_tier`` / ``initial_bp``.  If this negative control
    ever passes (constraint.py stops referencing them), the architecture check
    above would be vacuous -- so this test guards the guard."""
    code_names = _code_identifiers(CONSTRAINT_SRC)
    # ConstraintPolicy carries leverage_tier / initial_bp / maint_bp as fields
    # and the QuoteRiskPolicy reads maint_bp; at least these must appear.
    required = {"leverage_tier", "initial_bp", "maint_bp"}
    assert required <= code_names, (
        f"constraint.py must reference institutional fields {sorted(required)}; "
        f"found only {sorted(code_names & required)} -- the goal-layer guard "
        "would no longer be meaningful"
    )


def test_constraint_layer_is_separate_module_from_goal():
    """The constraint layer is a distinct module the goal layer depends on
    (one-way: goal -> constraint enums), never the reverse."""
    import market_game_sim.agent.goal as g

    # goal re-exports the constraint enums (one-way dependency).
    assert g.ConstraintReason is constraint_mod.ConstraintReason
    assert g.TriggerProvenance is constraint_mod.TriggerProvenance
