"""0.4.1 T964 (FR-502 / IR-501 / AC-502): TraderStrategy protocol, tiered info sets, registry.

Both sides of every gate: a registered family resolves and decides; an
unregistered id fails closed with ``UNKNOWN_STRATEGY_FAMILY``; each tier sees
exactly its fields and a set carrying a field above its tier is rejected.
A static check pins the L2 boundary: the package imports no ledger / matching /
kernel / event-log module.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from market_game_sim.agent import strategy_layer
from market_game_sim.agent.goal import (
    AgentInternalStateV1,
    AgentPreferences,
    BookTop,
    CompletedBar,
    InformationSetV1,
    OwnAccountView,
    PublicTrade,
)
from market_game_sim.agent.strategy_layer import (
    ACTION_NO_ACTION,
    ACTION_ORDER_INTENT,
    ACTION_TARGET_POSITION,
    PROTOCOL_VERSION,
    ExternalSignal,
    InformationTier,
    OrderIntentSpec,
    StrategyDecision,
    StrategyLayerError,
    StrategyRegistry,
    TieredInformationSet,
    TraderStrategy,
    crop_information_set,
    get_strategy,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]
LAYER_SRC = ROOT / "src" / "market_game_sim" / "agent" / "strategy_layer"

STATE = AgentInternalStateV1(
    schema_version=1,
    last_seen_market_event_id="",
    ewma_value_units=None,
    ewma_sample_count=0,
)
PREFS = AgentPreferences(risk_appetite_x1000=1000)


def _l1_info() -> InformationSetV1:
    return InformationSetV1(
        schema_version=1,
        cursor_from_event_id="e0",
        cursor_to_event_id="e2",
        public_trades=[
            PublicTrade(price_ticks=100, quantity_units=1, timestamp=1),
            PublicTrade(price_ticks=101, quantity_units=2, timestamp=2),
        ],
        completed_bars=[
            CompletedBar(open=100, high=101, low=100, close=101, volume=3, trade_count=2)
        ],
        book_top=BookTop(best_bid=100, best_ask=102, valuation_mark_half_ticks=202),
        own_account=OwnAccountView(wallet_units=1000, position_units=0, entry_notional_units=0),
    )


SIGNAL = ExternalSignal(source_id="fixed_seq", signal_version="v1", value={"alpha": 1})


class _Fixed(TraderStrategy):
    """Minimal family: target = its tier number, tagged as itself."""

    def __init__(self, family_id: str, tier: InformationTier) -> None:
        self.family_id = family_id
        self.info_tier = tier

    def decide(self, info, state, prefs):
        return StrategyDecision(
            family_id=self.family_id,
            info_tier=self.info_tier,
            action=ACTION_TARGET_POSITION,
            updated_state=state,
            target_position_units=int(info.tier),
        )


# --------------------------------------------------------------------------- #
# Registry: positive and fail-closed paths
# --------------------------------------------------------------------------- #


def test_registered_family_resolves_and_decides():
    reg = StrategyRegistry()
    fam = _Fixed("trend_probe", InformationTier.I2)
    reg.register(fam)
    assert reg.get("trend_probe") is fam
    assert "trend_probe" in reg
    info = crop_information_set(_l1_info(), InformationTier.I2, observed_at=5)
    decision = reg.decide("trend_probe", info, STATE, PREFS)
    assert decision.family_id == "trend_probe"
    assert decision.info_tier is InformationTier.I2
    assert decision.target_position_units == 2
    assert decision.protocol_version == PROTOCOL_VERSION


def test_unregistered_family_fails_closed_with_stable_code():
    reg = StrategyRegistry()
    reg.register(_Fixed("known", InformationTier.I0))
    with pytest.raises(StrategyLayerError) as exc:
        reg.get("unknown_family")
    assert exc.value.code == "UNKNOWN_STRATEGY_FAMILY"
    with pytest.raises(StrategyLayerError) as exc:
        reg.decide("unknown_family", None, STATE, PREFS)  # type: ignore[arg-type]
    assert exc.value.code == "UNKNOWN_STRATEGY_FAMILY"


def test_native_families_are_registered_and_unknown_ids_fail_closed():
    """0.4.1 T966: importing the bridge registers the four native families.

    ``goal_belief`` is deliberately absent: it is a roster family that rides the
    goal-model registry, not a ``TraderStrategy``.
    """
    from market_game_sim.agent.strategy_layer import bridge  # noqa: F401

    assert strategy_layer.default_registry().family_ids() == (
        "market_maker_v2",
        "mean_reversion",
        "sentiment_noise",
        "trend_following",
    )
    with pytest.raises(StrategyLayerError) as exc:
        get_strategy("goal_belief")
    assert exc.value.code == "UNKNOWN_STRATEGY_FAMILY"


def test_multiple_families_coexist_and_resolve_in_assembly_order():
    reg = StrategyRegistry()
    fams = [
        _Fixed("mm_v2", InformationTier.I0),
        _Fixed("noise", InformationTier.I1),
        _Fixed("trend", InformationTier.I2),
        _Fixed("quant", InformationTier.I3),
    ]
    for f in fams:
        reg.register(f)
    assert reg.family_ids() == ("mm_v2", "noise", "quant", "trend")
    order = ["trend", "mm_v2", "trend", "quant", "noise"]
    resolved = reg.resolve(order)
    assert [s.family_id for s in resolved] == order
    # each family decides on its own tier without crossing wires
    for f in fams:
        info = crop_information_set(
            _l1_info(),
            f.info_tier,
            observed_at=1,
            external_signals=[SIGNAL] if f.info_tier is InformationTier.I3 else None,
        )
        d = reg.decide(f.family_id, info, STATE, PREFS)
        assert (d.family_id, d.target_position_units) == (f.family_id, int(f.info_tier))


def test_resolve_names_every_unknown_id_in_one_error():
    reg = StrategyRegistry()
    reg.register(_Fixed("known", InformationTier.I0))
    with pytest.raises(StrategyLayerError) as exc:
        reg.resolve(["known", "typo_a", "known", "typo_b"])
    assert exc.value.code == "UNKNOWN_STRATEGY_FAMILY"
    assert "typo_a" in str(exc.value) and "typo_b" in str(exc.value)


def test_duplicate_registration_rejected():
    reg = StrategyRegistry()
    reg.register(_Fixed("dup", InformationTier.I0))
    with pytest.raises(StrategyLayerError) as exc:
        reg.register(_Fixed("dup", InformationTier.I1))
    assert exc.value.code == "DUPLICATE_STRATEGY_FAMILY"
    assert reg.get("dup").info_tier is InformationTier.I0  # first one kept


@pytest.mark.parametrize("bad_id", ["", "Bad", "1x", "has-dash", None])
def test_invalid_family_id_rejected(bad_id):
    reg = StrategyRegistry()
    with pytest.raises(StrategyLayerError) as exc:
        reg.register(_Fixed(bad_id, InformationTier.I0))  # type: ignore[arg-type]
    assert exc.value.code == "INVALID_STRATEGY"


def test_non_strategy_and_bad_tier_rejected():
    reg = StrategyRegistry()
    with pytest.raises(StrategyLayerError) as exc:
        reg.register(object())  # type: ignore[arg-type]
    assert exc.value.code == "INVALID_STRATEGY"
    with pytest.raises(StrategyLayerError) as exc:
        reg.register(_Fixed("tierless", 2))  # type: ignore[arg-type]
    assert exc.value.code == "INVALID_STRATEGY"


def test_protocol_version_mismatch_rejected():
    fam = _Fixed("old", InformationTier.I0)
    fam.protocol_version = PROTOCOL_VERSION + 1
    with pytest.raises(StrategyLayerError) as exc:
        StrategyRegistry().register(fam)
    assert exc.value.code == "PROTOCOL_VERSION_MISMATCH"


def test_decide_rejects_info_cropped_to_another_tier():
    reg = StrategyRegistry()
    reg.register(_Fixed("low", InformationTier.I0))
    richer = crop_information_set(_l1_info(), InformationTier.I2, observed_at=1)
    with pytest.raises(StrategyLayerError) as exc:
        reg.decide("low", richer, STATE, PREFS)
    assert exc.value.code == "INFO_TIER_MISMATCH"


def test_decide_rejects_mislabelled_decision():
    class _Liar(_Fixed):
        def decide(self, info, state, prefs):
            return StrategyDecision(
                family_id="someone_else",
                info_tier=self.info_tier,
                action=ACTION_NO_ACTION,
                updated_state=state,
            )

    reg = StrategyRegistry()
    reg.register(_Liar("liar", InformationTier.I0))
    info = crop_information_set(_l1_info(), InformationTier.I0, observed_at=1)
    with pytest.raises(StrategyLayerError) as exc:
        reg.decide("liar", info, STATE, PREFS)
    assert exc.value.code == "DECISION_FAMILY_MISMATCH"


# --------------------------------------------------------------------------- #
# Tiered information sets
# --------------------------------------------------------------------------- #

_EXPECTED_VISIBLE = {
    InformationTier.I0: set(),
    InformationTier.I1: {"public_trades"},
    InformationTier.I2: {"public_trades", "completed_bars"},
    InformationTier.I3: {"public_trades", "completed_bars", "external_signals"},
}


@pytest.mark.parametrize("tier", list(InformationTier))
def test_each_tier_exposes_only_its_fields(tier):
    signals = [SIGNAL] if tier is InformationTier.I3 else None
    info = crop_information_set(_l1_info(), tier, observed_at=7, external_signals=signals)
    assert info.book_top is not None and info.own_account.wallet_units == 1000
    for fname in ("public_trades", "completed_bars", "external_signals"):
        visible = getattr(info, fname) is not None
        assert visible == (fname in _EXPECTED_VISIBLE[tier]), (tier, fname)
    if tier >= InformationTier.I1:
        assert len(info.public_trades) == 2
    if tier >= InformationTier.I2:
        assert len(info.completed_bars) == 1
    if tier is InformationTier.I3:
        assert info.external_signals == (SIGNAL,)


def test_constructing_a_set_above_its_tier_is_rejected():
    trades = (PublicTrade(price_ticks=100, quantity_units=1, timestamp=1),)
    with pytest.raises(StrategyLayerError) as exc:
        TieredInformationSet(
            tier=InformationTier.I0,
            observed_at=0,
            book_top=None,
            own_account=OwnAccountView(0, 0, 0),
            public_trades=trades,
        )
    assert exc.value.code == "INFO_TIER_VIOLATION"


def test_set_missing_a_field_its_tier_requires_is_rejected():
    with pytest.raises(StrategyLayerError) as exc:
        TieredInformationSet(
            tier=InformationTier.I1,
            observed_at=0,
            book_top=None,
            own_account=OwnAccountView(0, 0, 0),
        )
    assert exc.value.code == "INVALID_INFO_SET"


def test_external_signals_below_i3_is_a_violation_not_a_silent_drop():
    with pytest.raises(StrategyLayerError) as exc:
        crop_information_set(
            _l1_info(), InformationTier.I2, observed_at=0, external_signals=[SIGNAL]
        )
    assert exc.value.code == "INFO_TIER_VIOLATION"


def test_cropping_does_not_mutate_the_l1_set():
    l1 = _l1_info()
    crop_information_set(l1, InformationTier.I0, observed_at=0)
    assert len(l1.public_trades) == 2 and len(l1.completed_bars) == 1


def test_external_signal_requires_source_and_version():
    with pytest.raises(StrategyLayerError) as exc:
        ExternalSignal(source_id="src", signal_version="")
    assert exc.value.code == "INVALID_EXTERNAL_SIGNAL"
    frozen = ExternalSignal(source_id="src", signal_version="v2", value={"a": 1})
    with pytest.raises(TypeError):
        frozen.value["a"] = 2  # type: ignore[index]


# --------------------------------------------------------------------------- #
# Output contract
# --------------------------------------------------------------------------- #


def test_decision_payload_must_match_action():
    ok_intent = OrderIntentSpec(side="BUY", order_type="LIMIT", quantity_units=1, price_ticks=100)
    ok = StrategyDecision(
        family_id="f",
        info_tier=InformationTier.I0,
        action=ACTION_ORDER_INTENT,
        updated_state=STATE,
        order_intent=ok_intent,
    )
    assert ok.order_intent is ok_intent
    no_action = StrategyDecision(
        family_id="f",
        info_tier=InformationTier.I0,
        action=ACTION_NO_ACTION,
        updated_state=STATE,
        reason_code="WARMUP",
    )
    assert no_action.target_position_units is None and no_action.order_intent is None
    for kwargs in (
        {"action": ACTION_TARGET_POSITION},  # missing target
        {"action": ACTION_NO_ACTION, "target_position_units": 1},  # stray payload
        {"action": ACTION_ORDER_INTENT, "target_position_units": 1},  # wrong payload
        {"action": "hold"},  # unknown action
    ):
        with pytest.raises(StrategyLayerError) as exc:
            StrategyDecision(
                family_id="f", info_tier=InformationTier.I0, updated_state=STATE, **kwargs
            )
        assert exc.value.code == "INVALID_DECISION", kwargs


def test_decision_protocol_version_is_pinned():
    with pytest.raises(StrategyLayerError) as exc:
        StrategyDecision(
            family_id="f",
            info_tier=InformationTier.I0,
            action=ACTION_NO_ACTION,
            updated_state=STATE,
            protocol_version=PROTOCOL_VERSION + 1,
        )
    assert exc.value.code == "PROTOCOL_VERSION_MISMATCH"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"side": "HOLD", "order_type": "MARKET", "quantity_units": 1},
        {"side": "BUY", "order_type": "STOP", "quantity_units": 1},
        {"side": "BUY", "order_type": "MARKET", "quantity_units": 0},
        {"side": "BUY", "order_type": "LIMIT", "quantity_units": 1},
        {"side": "SELL", "order_type": "MARKET", "quantity_units": 1, "price_ticks": 100},
    ],
)
def test_invalid_order_intents_rejected(kwargs):
    with pytest.raises(StrategyLayerError) as exc:
        OrderIntentSpec(**kwargs)
    assert exc.value.code == "INVALID_ORDER_INTENT"


def test_valid_market_and_limit_intents_accepted():
    assert OrderIntentSpec(side="SELL", order_type="MARKET", quantity_units=3).price_ticks is None
    assert OrderIntentSpec("BUY", "LIMIT", 1, 99).price_ticks == 99


# --------------------------------------------------------------------------- #
# L2 boundary (design §2): no ledger / matching / kernel / event-log imports
# --------------------------------------------------------------------------- #

FORBIDDEN_PACKAGES = ("ledger", "book", "kernel", "eventlog", "hook")


def _imported_modules(path: pathlib.Path) -> set[str]:
    mods: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def _violations(mods: set[str]) -> set[str]:
    return {
        m
        for m in mods
        for pkg in FORBIDDEN_PACKAGES
        if m == f"market_game_sim.{pkg}" or m.startswith(f"market_game_sim.{pkg}.")
    }


def test_strategy_layer_imports_no_l1_engine_module():
    files = sorted(LAYER_SRC.rglob("*.py"))
    assert files, "strategy_layer package missing"
    for path in files:
        assert not _violations(_imported_modules(path)), path


def test_boundary_check_flags_an_l1_import():
    # Negative control: the same check does flag a module that imports L1.
    roster = ROOT / "src" / "market_game_sim" / "experiment" / "roster.py"
    assert _violations(_imported_modules(roster))
