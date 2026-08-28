"""T603 (SC-006): Independent event log verifier.

Reconstructs book + account state from an event log WITHOUT importing
``kernel/`` or ``ledger/`` — proving the log is self-contained.

Termination discrimination: structural first (TI-5), then semantic (TI-4).

0.1.2 extensions (T506 / KPI-006):
- WRITE_OFF_POSTING handling (was skipped)
- MARGIN_CALL field validation
- exchange_risk_pnl in C2
- Causal chain coverage check (AGENT + LIQUIDATION)

0.1.2 extension (T503 / KPI-009):
- PnL bridge residual check (metrics.bridge.bridge_trade is a pure function
  of posting/valuation-mark data, not a kernel/ledger reconstruction, so
  importing it does not compromise the "self-contained" property above).
  Asserted in the SAME verification pass as KPI-006/C1/C2, per the
  acceptance-vectors.md contract requirement that KPI-009 not be a separate,
  in-process-only code path.
"""

from __future__ import annotations

import json
import pathlib
from collections import defaultdict
from typing import Any

from market_game_sim.metrics.bridge import bridge_trade


def verify_log(path: str | pathlib.Path, mult: int = 1000) -> dict[str, Any]:
    p = pathlib.Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"success": False, "error": "TI-5", "detail": str(exc)}

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return {"success": False, "error": "TI-5", "detail": "fewer than 2 lines"}

    records: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        try:
            r = json.loads(line)
        except json.JSONDecodeError as exc:
            return {"success": False, "error": "TI-5", "detail": f"line {i + 1}: {exc}"}
        records.append(r)

    if records[0].get("record_kind") != "RUN_HEADER":
        return {"success": False, "error": "TI-5", "detail": "first is not RUN_HEADER"}
    if records[-1].get("record_kind") != "RUN_TRAILER":
        return {"success": False, "error": "TI-5", "detail": "last is not RUN_TRAILER"}

    # record_count lives in RUN_TRAILER (§6.2), not RUN_HEADER
    rc_trailer = records[-1].get("record_count")
    if rc_trailer is not None and rc_trailer != len(lines):
        return {
            "success": False,
            "error": "TI-5",
            "detail": f"record_count {rc_trailer} != {len(lines)}",
        }

    trailer = records[-1]
    if trailer.get("terminated") == "ABORTED":
        return {
            "success": False,
            "error": "TI-4",
            "detail": f"abort_code={trailer.get('abort_code')}",
        }

    events = [r for r in records if r.get("record_kind") == "EVENT"]
    acc_state, risk_pnl, book_state, causal_err = _rebuild(events)
    if causal_err:
        return {"success": False, "error": "TI-5", "detail": f"causal: {causal_err}"}

    c1 = sum(a["position_units"] for a in acc_state.values())
    if c1 != 0:
        return {"success": False, "error": "TI-5", "detail": f"C1 breach: Σ={c1}"}

    c2_err = _check_c2(acc_state, events, risk_pnl)
    if c2_err:
        return {"success": False, "error": "TI-5", "detail": f"C2: {c2_err}"}

    kpi006 = _check_kpi006(events)
    if kpi006:
        return {"success": False, "error": "TI-5", "detail": f"KPI-006: {kpi006}"}

    kpi009 = _check_kpi009_bridge(events, mult)
    if kpi009:
        return {"success": False, "error": "TI-5", "detail": f"KPI-009: {kpi009}"}

    by_txn: dict[int, list[int]] = defaultdict(list)
    for e in events:
        by_txn[e["transaction_seq"]].append(e["record_index"])
    for txn_seq, idxs in sorted(by_txn.items()):
        if idxs[0] != 0:
            return {"success": False, "error": "TI-5", "detail": f"txn {txn_seq}: first != 0"}
        if any(idxs[i] + 1 != idxs[i + 1] for i in range(len(idxs) - 1)):
            return {"success": False, "error": "TI-5", "detail": f"txn {txn_seq}: gap/disorder"}

    return {
        "success": True,
        "termination": trailer.get("terminated"),
        "last_committed_transaction_seq": trailer.get("last_committed_transaction_seq"),
        "event_count": len(events),
        "account_count": len(acc_state),
        "c1_pass": c1 == 0,
        "causal_chain_pass": causal_err is None,
        "kpi006_agent_covered": _origin_covered(events, "AGENT"),
        "kpi006_liquidation_covered": _origin_covered(events, "LIQUIDATION"),
        "kpi009_bridge_ok": True,
    }


def _origin_covered(events: list[dict], origin: str) -> bool:
    return any(e.get("event_type") == "ORDER_ARRIVAL" and e.get("origin") == origin for e in events)


def check_causal_references(events: list[dict]) -> str | None:
    """Verify every ``caused_by_event_id`` resolves to a strictly earlier
    event in the log (causal chain integrity, TI-1).  Returns ``None`` when
    OK, else an error detail string.  Pure function of ``events`` -- no file
    I/O -- so callers with an in-memory event list (e.g. the experiment
    runner) can reuse it without going through :func:`verify_log`.
    """
    event_ids: dict[str, tuple[int, int, int]] = {}
    for e in events:
        eid = e.get("event_id", "")
        if eid:
            event_ids[eid] = (e["timestamp"], e["transaction_seq"], e["record_index"])

        caused_by = e.get("caused_by_event_id")
        if caused_by:
            ref = event_ids.get(caused_by)
            if ref is None:
                return f"dangling caused_by_event_id={caused_by}"
            rlk = (e["timestamp"], e["transaction_seq"], e["record_index"])
            if rlk <= ref:
                return f"log_key {rlk} <= ref {ref}"
    return None


def _rebuild(
    events: list[dict],
) -> tuple[dict[str, dict], int, dict[str, dict], str | None]:
    accounts: dict[str, dict[str, int]] = {}
    book_orders: dict[str, dict] = {}
    risk_pnl = 0
    causal_err = check_causal_references(events)

    for e in events:
        et = e.get("event_type", "")

        if et == "SNAPSHOT" and e.get("snapshot_type") == "ACCOUNT":
            for entry in e.get("payload", {}).get("accounts", []):
                aid = entry.get("agent_id", "")
                accounts[aid] = {
                    "wallet_units": entry.get("wallet_units", 0),
                    "position_units": entry.get("position_units", 0),
                    "entry_notional_units": entry.get("entry_notional_units", 0),
                }

        elif et == "TRADE_SETTLE":
            for p in e.get("postings", []):
                if p.get("posting_type") != "TRADE_POSTING":
                    continue
                aid = p.get("agent_id", "")
                if not aid:
                    continue
                if aid not in accounts:
                    accounts[aid] = {
                        "wallet_units": 0,
                        "position_units": 0,
                        "entry_notional_units": 0,
                    }
                a = accounts[aid]
                a["wallet_units"] += p.get("wallet_delta_units", 0)
                a["position_units"] += p.get("position_delta_units", 0)
                a["entry_notional_units"] += p.get("entry_notional_delta_units", 0)
            maker_id = e.get("maker_order_id", "")
            fill_qty = e.get("quantity_units", 0)
            if maker_id in book_orders:
                book_orders[maker_id]["filled"] += fill_qty

        elif et == "MARGIN_CALL":
            for p in e.get("postings", []):
                if p.get("posting_type") == "WRITE_OFF_POSTING":
                    risk_pnl += p.get("risk_pnl_delta_units", 0)
                    if p.get("role") == "ACCOUNT":
                        aid = p.get("agent_id", "")
                        if aid and aid in accounts:
                            accounts[aid]["wallet_units"] += p.get("wallet_delta_units", 0)

        elif et == "ORDER_ARRIVAL" and e.get("action") == "SUBMIT":
            oid = e.get("order_id", "")
            otype = e.get("order_type", "")
            if otype == "LIMIT" and e.get("accepted", True):
                book_orders[oid] = {
                    "side": e.get("side", ""),
                    "price": e.get("price_ticks"),
                    "qty": e.get("quantity_units", 0),
                    "filled": 0,
                    "cancelled": 0,
                }

        elif et == "ORDER_CANCELLED":
            oid = e.get("order_id", "")
            cq = e.get("cancelled_qty_units", 0)
            if oid in book_orders:
                book_orders[oid]["cancelled"] = cq

    if causal_err:
        return accounts, risk_pnl, {}, causal_err

    book: dict[str, dict[int, int]] = {"bids": defaultdict(int), "asks": defaultdict(int)}
    for o in book_orders.values():
        rem = o["qty"] - o["filled"] - o["cancelled"]
        if rem > 0 and o["price"] is not None:
            section = "bids" if o["side"] == "BUY" else "asks"
            book[section][o["price"]] += rem
    book_plain = {
        "bids": dict(sorted(book["bids"].items(), reverse=True)),
        "asks": dict(sorted(book["asks"].items())),
    }

    return accounts, risk_pnl, book_plain, None


def _check_c2(
    accounts: dict[str, dict],
    events: list[dict],
    risk_pnl: int,
) -> str | None:
    wallet_sum_0: int | None = None
    fees = 0
    for e in events:
        if e.get("event_type") == "SNAPSHOT" and e.get("snapshot_type") == "ACCOUNT":
            wallet_sum_0 = sum(
                entry.get("wallet_units", 0) for entry in e.get("payload", {}).get("accounts", [])
            )
        elif e.get("event_type") == "TRADE_SETTLE":
            fees += e.get("taker_fee_cash_units", 0) + e.get("maker_fee_cash_units", 0)
    if wallet_sum_0 is None:
        return None
    wme = sum(a["wallet_units"] - a["entry_notional_units"] for a in accounts.values())
    if wme + fees + risk_pnl != wallet_sum_0:
        return f"Σ={wme} + fees={fees} + risk={risk_pnl} ≠ {wallet_sum_0}"
    return None


def _check_kpi009_bridge(events: list[dict], mult: int) -> str | None:
    """Verify KPI-009: PnL bridge residual is exactly 0 for every
    TRADE_POSTING (T503, metrics-dictionary §5.2).  Returns the first
    non-zero-residual detail found, else None.
    """
    for e in events:
        if e.get("event_type") != "TRADE_SETTLE":
            continue
        vm_before_h = e.get("valuation_mark_before_half_ticks", 0)
        vm_after_h = e.get("valuation_mark_after_half_ticks", 0)
        for p in e.get("postings", []):
            if p.get("posting_type") != "TRADE_POSTING":
                continue
            result = bridge_trade(
                posting=p,
                vm_before_half=vm_before_h,
                vm_after_half=vm_after_h,
                trade_price_ticks=e.get("price_ticks", 0),
                position_before_units=p.get("position_after_units", 0)
                - p.get("position_delta_units", 0),
                mult=mult,
            )
            if result["residual"] != 0:
                return (
                    f"trade {e.get('trade_id')} agent {p.get('agent_id')}: "
                    f"residual {result['residual']} != 0"
                )
    return None


def _log_key(e: dict) -> tuple:
    return (e.get("timestamp", 0), e.get("transaction_seq", 0), e.get("record_index", 0))


def _check_kpi006(events: list[dict]) -> str | None:
    """Verify KPI-006: every AGENT/EXOGENOUS_STRESS/LIQUIDATION order links to a valid,
    causally-ordered decision chain (event-schema.md §5.1/§5.2).

    ``origin=AGENT``: ORDER_ARRIVAL.decision_event_id -> AGENT_DECIDE ->
    (.observation_event_id) -> AGENT_OBSERVE -> (.market_data_event_id) ->
    some earlier event (the very first observation of a run legitimately
    points at the bootstrap ACCOUNT SNAPSHOT rather than a
    MARKET_DATA_PUBLISH -- see agent/scheduler.py -- so this hop is not
    type-checked, only existence/uniqueness/ordering).

    ``origin=LIQUIDATION``: ORDER_ARRIVAL.decision_event_id -> MARGIN_CALL
    -> (.caused_by_event_id) must resolve within the SAME transaction_seq
    as the MARGIN_CALL, and (.risk_mark_event_id) likewise -- per
    event-schema.md §5.2.  Not type-checked because a margin scan that
    re-flags an already-PENDING_LIQUIDATION account on a transaction with
    zero new trades legitimately sets risk_mark_event_id to that
    transaction's own ORDER_ARRIVAL (record_index 0), not a TRADE_SETTLE
    (book/matching.py::_run_post_batch_risk_check).

    Every hop requires the target event_id to resolve to EXACTLY one event
    (dangling or duplicate-matched references both fail) with a strictly
    smaller log_key (timestamp, transaction_seq, record_index) than the
    referencing event, per SC-006.

    ``origin=EXOGENOUS_STRESS`` follows the AGENT_DECIDE -> AGENT_OBSERVE
    shape, and the decision must explicitly carry matching provenance.
    """
    by_id: dict[str, dict] = {}
    dup_ids: set[str] = set()
    for e in events:
        eid = e.get("event_id", "")
        if not eid:
            continue
        if eid in by_id:
            dup_ids.add(eid)
        else:
            by_id[eid] = e

    def resolve(eid: str) -> tuple[dict | None, str | None]:
        if not eid:
            return None, "empty/missing reference"
        if eid in dup_ids:
            return None, f"{eid} matches multiple events"
        target = by_id.get(eid)
        if target is None:
            return None, f"dangling reference {eid}"
        return target, None

    decision_ids = {e.get("event_id", "") for e in events if e.get("event_type") == "AGENT_DECIDE"}
    mc_ids = {e.get("event_id", "") for e in events if e.get("event_type") == "MARGIN_CALL"}

    for e in events:
        if e.get("event_type") != "ORDER_ARRIVAL":
            continue
        origin = e.get("origin", "")
        dec = e.get("decision_event_id", "")
        oid = e.get("order_id")

        if origin in {"AGENT", "EXOGENOUS_STRESS"}:
            if not decision_ids:
                return "AGENT orders exist but no AGENT_DECIDE in log"
            if dec not in decision_ids:
                return f"AGENT order {oid} missing decision {dec}"
            decide, err = resolve(dec)
            if err:
                return f"AGENT order {oid}: decision_event_id {err}"
            if _log_key(decide) >= _log_key(e):
                return f"AGENT order {oid}: AGENT_DECIDE {dec} not strictly earlier"
            obs_id = decide.get("observation_event_id", "")
            observe, err = resolve(obs_id)
            if err:
                return f"AGENT_DECIDE {dec}: observation_event_id {err}"
            if _log_key(observe) >= _log_key(decide):
                return f"AGENT_DECIDE {dec}: AGENT_OBSERVE {obs_id} not strictly earlier"
            provenance = (decide.get("decision_evidence") or {}).get("trigger_provenance")
            expected = "EXOGENOUS_STRESS" if origin == "EXOGENOUS_STRESS" else "ENDOGENOUS_AGENT"
            # Legacy logs predate DecisionEvidenceV1.  They may omit AGENT
            # provenance, but an explicit value must agree with origin; the
            # new EXOGENOUS_STRESS branch always requires explicit evidence.
            invalid = (
                provenance != expected
                if origin == "EXOGENOUS_STRESS"
                else provenance not in {None, expected}
            )
            if invalid:
                return (
                    f"{origin} order {oid}: AGENT_DECIDE {dec} provenance "
                    f"{provenance!r} != {expected}"
                )
            md_id = observe.get("market_data_event_id", "")
            publish, err = resolve(md_id)
            if err:
                return f"AGENT_OBSERVE {obs_id}: market_data_event_id {err}"
            if _log_key(publish) >= _log_key(observe):
                return f"AGENT_OBSERVE {obs_id}: market_data_event_id {md_id} not strictly earlier"

        if origin == "LIQUIDATION":
            if not mc_ids:
                return "LIQUIDATION orders exist but no MARGIN_CALL in log"
            if dec not in mc_ids:
                return f"LIQUIDATION order {oid} missing MC {dec}"
            mc, err = resolve(dec)
            if err:
                return f"LIQUIDATION order {oid}: decision_event_id {err}"
            if _log_key(mc) >= _log_key(e):
                return f"LIQUIDATION order {oid}: MARGIN_CALL {dec} not strictly earlier"
            parent_id = mc.get("caused_by_event_id", "")
            parent, err = resolve(parent_id)
            if err:
                return f"MARGIN_CALL {dec}: caused_by_event_id {err}"
            if parent.get("transaction_seq") != mc.get("transaction_seq"):
                return (
                    f"MARGIN_CALL {dec}: caused_by_event_id {parent_id} not in same transaction_seq"
                )
            if _log_key(parent) >= _log_key(mc):
                return f"MARGIN_CALL {dec}: caused_by_event_id {parent_id} not strictly earlier"
            rm_id = mc.get("risk_mark_event_id", "")
            risk_mark, err = resolve(rm_id)
            if err:
                return f"MARGIN_CALL {dec}: risk_mark_event_id {err}"
            if risk_mark.get("transaction_seq") != mc.get("transaction_seq"):
                return f"MARGIN_CALL {dec}: risk_mark_event_id {rm_id} not in same transaction_seq"
            if _log_key(risk_mark) >= _log_key(mc):
                return f"MARGIN_CALL {dec}: risk_mark_event_id {rm_id} not strictly earlier"
    return None


def digest_events(records: list[dict]) -> str:
    import hashlib

    h = hashlib.blake2b(digest_size=32)
    for r in records:
        if r.get("record_kind") != "EVENT":
            continue
        h.update(json.dumps(r, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()
