"""T211/R018-C007: decision-evidence full-chain independent verifier.

Validates the complete observe -> decide -> order -> trade causal chain
plus the DecisionEvidenceV1 hops the 0.1.5 schema adds:

- every ``AGENT_DECIDE.decision_evidence`` cursor boundary must equal the
  referenced ``AGENT_OBSERVE``'s recorded ``cursor_from_event_id`` /
  ``cursor_to_event_id`` (FR-022/FR-025: 成交可回溯至观察);
- every AGENT-sourced ``ORDER_ARRIVAL.decision_event_id`` must resolve to a
  strictly earlier ``AGENT_DECIDE``, whose ``observation_event_id`` resolves
  to a strictly earlier ``AGENT_OBSERVE`` (the full order->decision->observe
  hop, R018-C007);
- ``trigger_provenance`` must be a closed-set value
  (``ENDOGENOUS_AGENT`` / ``LIQUIDATION`` / ``EXOGENOUS_STRESS``);
- a run declared ``SPONTANEOUS`` must never contain ``EXOGENOUS_STRESS``
  (spec §5: fail closed -- such a run is ineligible for research evidence).

The observe->market-data hop is deliberately NOT strictly-ordered here: the
kernel's bootstrap barrier is a documented known gap (§4.6.3) -- the first
observation legitimately references the bootstrap snapshot which may share
an early transaction window.  The verify.py ``_check_kpi006`` covers that
hop for self-contained logs; this verifier covers the decision-evidence hops
and the order/decide/observe references.

Pure function of the event list -- no file I/O -- so it can be wired into
the experiment runner and driven by integration tests.
"""

from __future__ import annotations

from collections.abc import Iterable

_TRIGGER_PROVENANCE_CLOSED_SET = {"ENDOGENOUS_AGENT", "LIQUIDATION", "EXOGENOUS_STRESS"}


class ChainVerificationError(ValueError):
    """Raised when a decision-evidence chain hop fails verification."""


def _log_key(e: dict) -> tuple[int, int, int]:
    return (e["timestamp"], e["transaction_seq"], e["record_index"])


def verify_decision_evidence_chain(
    events: Iterable[dict],
    *,
    run_family: str | None = None,
) -> None:
    """Verify the full causal chain plus every AGENT_DECIDE's decision_evidence.

    Raises :class:`ChainVerificationError` on the first violation.  ``events``
    must be the full log (including the observations the decisions reference).
    ``run_family`` optionally declares the run family so the
    SPONTANEOUS-no-EXOGENOUS_STRESS rule can be enforced.
    """
    events_list = list(events)

    # R018-C007: every caused_by_event_id hop (trade->order, cancel->order,
    # margin->order) is validated by the existing independent checker.
    from market_game_sim.verify import check_causal_references

    causal_err = check_causal_references(events_list)
    if causal_err is not None:
        raise ChainVerificationError(f"causal chain broken: {causal_err}")

    by_id: dict[str, dict] = {}
    dup_ids: set[str] = set()
    for e in events_list:
        eid = e.get("event_id", "")
        if not eid:
            continue
        if eid in by_id:
            dup_ids.add(eid)
        else:
            by_id[eid] = e

    def resolve(eid: str) -> dict | None:
        if not eid or eid in dup_ids or eid not in by_id:
            return None
        return by_id[eid]

    # R018-C007: the order -> decide -> observe hop -- a tampered
    # ORDER_ARRIVAL.decision_event_id must fail here, not just the
    # observe->decide hop.
    for e in events_list:
        if e.get("event_type") != "ORDER_ARRIVAL" or e.get("origin") not in {
            "AGENT",
            "EXOGENOUS_STRESS",
        }:
            continue
        dec_id = e.get("decision_event_id", "")
        decide = resolve(dec_id)
        if decide is None:
            raise ChainVerificationError(
                f"ORDER_ARRIVAL {e.get('event_id')} references missing decision {dec_id!r}"
            )
        if _log_key(decide) >= _log_key(e):
            raise ChainVerificationError(
                f"ORDER_ARRIVAL {e.get('event_id')} decision {dec_id} not strictly earlier"
            )
        obs_id = decide.get("observation_event_id", "")
        observe = resolve(obs_id)
        if observe is None:
            raise ChainVerificationError(
                f"AGENT_DECIDE {dec_id} references missing observation {obs_id!r}"
            )
        if _log_key(observe) >= _log_key(decide):
            raise ChainVerificationError(
                f"AGENT_DECIDE {dec_id} observation {obs_id} not strictly earlier"
            )
        provenance = (decide.get("decision_evidence") or {}).get("trigger_provenance")
        expected = (
            "EXOGENOUS_STRESS" if e.get("origin") == "EXOGENOUS_STRESS" else "ENDOGENOUS_AGENT"
        )
        if provenance != expected:
            raise ChainVerificationError(
                f"ORDER_ARRIVAL {e.get('event_id')} origin {e.get('origin')} requires "
                f"decision provenance {expected}, got {provenance!r}"
            )

    for e in events_list:
        if e.get("event_type") != "AGENT_DECIDE":
            continue
        ev = e.get("decision_evidence")
        if ev is None:
            # v1 BENCHMARK / market-maker paths carry path-tagged evidence
            # (event-schema.md §4.5) -- never absent.  A missing field is a
            # producer defect.
            raise ChainVerificationError(
                f"AGENT_DECIDE {e.get('event_id')} has no decision_evidence"
            )

        # R018-C009: the evidence object itself must satisfy the closed
        # DecisionEvidenceV1 schema (fields / types / enums / version).
        from market_game_sim.evidence.evidence_guard import (
            EvidenceClassError,
            validate_decision_evidence_v1,
        )

        try:
            validate_decision_evidence_v1(ev)
        except EvidenceClassError as exc:
            raise ChainVerificationError(
                f"AGENT_DECIDE {e.get('event_id')} invalid decision_evidence: {exc}"
            ) from exc

        provenance = ev.get("trigger_provenance")
        if provenance not in _TRIGGER_PROVENANCE_CLOSED_SET:
            raise ChainVerificationError(
                f"AGENT_DECIDE {e.get('event_id')} has invalid trigger_provenance "
                f"{provenance!r}; must be one of {sorted(_TRIGGER_PROVENANCE_CLOSED_SET)}"
            )

        if run_family == "SPONTANEOUS" and provenance == "EXOGENOUS_STRESS":
            raise ChainVerificationError(
                f"SPONTANEOUS run contains EXOGENOUS_STRESS at AGENT_DECIDE "
                f"{e.get('event_id')}; spontaneous runs must be endogenous"
            )

        obs_id = ev.get("observation_event_id") or e.get("observation_event_id", "")
        observe = by_id.get(obs_id)
        if observe is None:
            raise ChainVerificationError(
                f"AGENT_DECIDE {e.get('event_id')} references missing observation {obs_id!r}"
            )
        if _log_key(observe) >= _log_key(e):
            raise ChainVerificationError(
                f"AGENT_DECIDE {e.get('event_id')} observation {obs_id} not strictly earlier"
            )

        # Cursor boundaries in the evidence must equal the observation's
        # recorded boundaries (design.md §5: evidence carries the cursor that
        # produced it).
        ev_from = ev.get("cursor_from_event_id")
        ev_to = ev.get("cursor_to_event_id")
        obs_from = observe.get("cursor_from_event_id")
        obs_to = observe.get("cursor_to_event_id")
        if ev_from != obs_from:
            raise ChainVerificationError(
                f"AGENT_DECIDE {e.get('event_id')} cursor_from {ev_from!r} != "
                f"observation {obs_id} cursor_from {obs_from!r}"
            )
        if ev_to != obs_to:
            raise ChainVerificationError(
                f"AGENT_DECIDE {e.get('event_id')} cursor_to {ev_to!r} != "
                f"observation {obs_id} cursor_to {obs_to!r}"
            )


__all__ = ["ChainVerificationError", "verify_decision_evidence_chain"]
