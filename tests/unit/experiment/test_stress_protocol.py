"""T210: StressProtocolV1 + four-cell identical path (AC-004 / DR-501).

Covers (FR-023 / AC-004 / TR-502):
- the protocol shape matches the frozen StressProtocolV1 contract;
- reads_run_outcome is forced false (ADR-003 §3.2);
- four cells must be event-for-event identical, and any mismatch fails the
  whole paired evidence (positive and negative cases);
- EXOGENOUS_STRESS provenance is the closed-set marker for STRESS triggers.
"""

from __future__ import annotations

import pytest

from market_game_sim.experiment.stress_protocol import (
    StressEvent,
    StressProtocolError,
    StressProtocolV1,
    validate_four_cell_same_path,
    validate_stress_exogenous_provenance,
)


def _protocol(events: tuple[StressEvent, ...]) -> StressProtocolV1:
    return StressProtocolV1(protocol_id="p1", events=events)


def _one_event_protocol() -> StressProtocolV1:
    return _protocol(
        (
            StressEvent(
                "MARKET_ORDER",
                timestamp_ns=1_000,
                params={"side": "SELL", "quantity_units": 100},
            ),
        )
    )


def test_protocol_shape_matches_frozen_contract():
    p = _one_event_protocol()
    d = p.to_dict()
    assert set(d) == {"schema_version", "protocol_id", "events", "reads_run_outcome"}
    assert d["schema_version"] == 1
    assert d["reads_run_outcome"] is False
    assert len(d["events"]) == 1
    assert d["events"][0]["event_type"] == "MARKET_ORDER"


def test_protocol_rejects_reads_run_outcome_true():
    with pytest.raises(StressProtocolError, match="reads_run_outcome"):
        StressProtocolV1(
            protocol_id="p1",
            events=(),
            reads_run_outcome=True,
        )


def test_protocol_rejects_negative_timestamp():
    with pytest.raises(StressProtocolError, match="timestamp_ns"):
        _protocol((StressEvent("MARKET_ORDER", timestamp_ns=-1),))


def test_protocol_rejects_wrong_schema_version():
    """R018-C006 (Round 3): schema_version must be exactly 1."""
    with pytest.raises(StressProtocolError, match="schema_version"):
        StressProtocolV1(
            protocol_id="p1",
            events=(),
            schema_version=99,
        )


def test_protocol_rejects_unknown_event_type():
    """R018-C006 (Round 3): event_type must be from the closed set."""
    with pytest.raises(StressProtocolError, match="event_type"):
        _protocol((StressEvent("ALIEN_EVENT", timestamp_ns=1_000),))


def test_protocol_rejects_unknown_params():
    """R018-C006 (Round 3): params keys must be closed per event type."""
    with pytest.raises(StressProtocolError, match="params"):
        _protocol((StressEvent("MARKET_ORDER", timestamp_ns=1_000, params={"smuggle": 1}),))


def test_protocol_accepts_closed_params():
    _protocol(
        (
            StressEvent(
                "MARKET_ORDER", timestamp_ns=1_000, params={"side": "SELL", "quantity_units": 100}
            ),
        )
    )


def test_protocol_rejects_empty_id():
    with pytest.raises(StressProtocolError, match="protocol_id"):
        StressProtocolV1(protocol_id="", events=())


def test_digest_deterministic():
    p1 = _one_event_protocol()
    p2 = _one_event_protocol()
    assert p1.digest() == p2.digest()


def test_digest_differs_when_events_differ():
    a = _protocol(
        (
            StressEvent(
                "MARKET_ORDER", timestamp_ns=1_000, params={"side": "SELL", "quantity_units": 100}
            ),
        )
    )
    b = _protocol(
        (
            StressEvent(
                "MARKET_ORDER", timestamp_ns=1_000, params={"side": "BUY", "quantity_units": 100}
            ),
        )
    )
    assert a.digest() != b.digest()


def _all_four(protocol: StressProtocolV1) -> dict[str, StressProtocolV1]:
    return {
        "L_low_M_low": protocol,
        "L_low_M_high": protocol,
        "L_high_M_low": protocol,
        "L_high_M_high": protocol,
    }


def test_four_cell_identical_path_passes():
    validate_four_cell_same_path(_all_four(_one_event_protocol()))


def test_four_cell_missing_cell_fails():
    protocols = _all_four(_one_event_protocol())
    del protocols["L_high_M_high"]
    with pytest.raises(StressProtocolError, match="missing"):
        validate_four_cell_same_path(protocols)


def test_four_cell_mismatch_fails_whole_evidence():
    protocols = _all_four(_one_event_protocol())
    protocols["L_high_M_high"] = _protocol(
        (
            StressEvent(
                "MARKET_ORDER", timestamp_ns=9_999, params={"side": "BUY", "quantity_units": 100}
            ),
        )
    )
    with pytest.raises(StressProtocolError, match="identical"):
        validate_four_cell_same_path(protocols)


def test_four_cell_rejects_extra_cell():
    """R018-C006: a fifth (unknown) cell breaks the closed four-cell set."""
    protocols = _all_four(_one_event_protocol())
    protocols["L_low_M_extra"] = _one_event_protocol()
    with pytest.raises(StressProtocolError, match="unexpected cells"):
        validate_four_cell_same_path(protocols)


def test_protocol_rejects_missing_required_param():
    """R018-C006 (Round 5): a MARKET_ORDER without quantity_units is invalid."""
    with pytest.raises(StressProtocolError, match="quantity_units"):
        _protocol((StressEvent("MARKET_ORDER", timestamp_ns=1_000, params={"side": "SELL"}),))


def test_protocol_rejects_wrong_param_type():
    """R018-C006 (Round 5): quantity_units must be an int (bool excluded)."""
    with pytest.raises(StressProtocolError, match="quantity_units"):
        _protocol(
            (
                StressEvent(
                    "MARKET_ORDER",
                    timestamp_ns=1_000,
                    params={"side": "SELL", "quantity_units": True},
                ),
            )
        )


def test_protocol_rejects_bad_enum_value():
    """R018-C006 (Round 5): side must be BUY or SELL."""
    with pytest.raises(StressProtocolError, match="side"):
        _protocol(
            (
                StressEvent(
                    "MARKET_ORDER",
                    timestamp_ns=1_000,
                    params={"side": "HOLD", "quantity_units": 100},
                ),
            )
        )


def test_protocol_rejects_nonpositive_quantity():
    """R018-C006 (Round 5): quantity_units must be >= 1."""
    with pytest.raises(StressProtocolError, match="quantity_units"):
        _protocol(
            (
                StressEvent(
                    "MARKET_ORDER",
                    timestamp_ns=1_000,
                    params={"side": "SELL", "quantity_units": 0},
                ),
            )
        )


def test_stress_provenance_requires_exogenous_stress():
    """R018-C006: a STRESS run's protocol-driven decisions must be EXACTLY
    EXOGENOUS_STRESS -- ENDOGENOUS_AGENT / LIQUIDATION are rejected here."""
    good = [{"trigger_provenance": "EXOGENOUS_STRESS"}]
    validate_stress_exogenous_provenance(good)
    for bad_prov in ("ENDOGENOUS_AGENT", "LIQUIDATION", "ALIEN"):
        with pytest.raises(StressProtocolError, match="EXOGENOUS_STRESS"):
            validate_stress_exogenous_provenance([{"trigger_provenance": bad_prov}])
