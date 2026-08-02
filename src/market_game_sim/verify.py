"""T603 (SC-006): Independent event log verifier.

Reconstructs book + account state from an event log WITHOUT importing
``kernel/`` or ``ledger/`` — proving the log is self-contained.

Termination discrimination (§5.2): structural first (TI-5), then
semantic (TI-4).  Order must not be reversed.

Book reconstruction follows 事件 Schema §4.7:
  remaining_qty = ORDER_ARRIVAL.qty − ΣTRADE_SETTLE.qty − ΣORDER_CANCELLED.qty
"""

from __future__ import annotations

import json
import pathlib
from collections import defaultdict
from typing import Any


def verify_log(path: str | pathlib.Path) -> dict[str, Any]:
    p = pathlib.Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"success": False, "error": "TI-5", "detail": str(exc)}

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return {"success": False, "error": "TI-5", "detail": "fewer than 2 lines"}

    records: list[dict[str, Any]] = []
    rc_header: int | None = None
    for i, line in enumerate(lines):
        try:
            r = json.loads(line)
        except json.JSONDecodeError as exc:
            return {"success": False, "error": "TI-5", "detail": f"line {i + 1}: {exc}"}
        records.append(r)
        if r.get("record_kind") == "RUN_HEADER":
            rc_header = r.get("record_count")

    if records[0].get("record_kind") != "RUN_HEADER":
        return {"success": False, "error": "TI-5", "detail": "first is not RUN_HEADER"}
    if records[-1].get("record_kind") != "RUN_TRAILER":
        return {"success": False, "error": "TI-5", "detail": "last is not RUN_TRAILER"}
    if rc_header is not None and rc_header != len(lines):
        return {
            "success": False,
            "error": "TI-5",
            "detail": f"record_count {rc_header} != {len(lines)}",
        }

    trailer = records[-1]
    if trailer.get("terminated") == "ABORTED":
        return {
            "success": False,
            "error": "TI-4",
            "detail": f"abort_code={trailer.get('abort_code')}",
        }

    events = [r for r in records if r.get("record_kind") == "EVENT"]
    acc_state, book_state, causal_err = _rebuild(events)
    if causal_err:
        return {"success": False, "error": "TI-5", "detail": f"causal: {causal_err}"}

    c1 = sum(a["position_units"] for a in acc_state.values())
    if c1 != 0:
        return {"success": False, "error": "TI-5", "detail": f"C1 breach: Σ={c1}"}

    c2_err = _check_c2(acc_state, events)
    if c2_err:
        return {"success": False, "error": "TI-5", "detail": f"C2: {c2_err}"}

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
    }


def _rebuild(
    events: list[dict],
) -> tuple[dict[str, dict], dict[str, dict], str | None]:
    accounts: dict[str, dict[str, int]] = {}
    book_orders: dict[str, dict] = {}
    event_ids: dict[str, tuple[int, int, int]] = {}
    causal_err: str | None = None

    for e in events:
        eid = e.get("event_id", "")
        if eid:
            event_ids[eid] = (e["timestamp"], e["transaction_seq"], e["record_index"])

        caused_by = e.get("caused_by_event_id")
        if caused_by:
            ref = event_ids.get(caused_by)
            if ref is None:
                causal_err = f"dangling caused_by_event_id={caused_by}"
            else:
                rlk = (e["timestamp"], e["transaction_seq"], e["record_index"])
                if rlk <= ref:
                    causal_err = f"log_key {rlk} <= ref {ref}"

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
        return accounts, {}, causal_err

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

    return accounts, book_plain, None


def _check_c2(accounts: dict[str, dict], events: list[dict]) -> str | None:
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
    if wme + fees != wallet_sum_0:
        return f"Σ={wme} + fees={fees} ≠ {wallet_sum_0}"
    return None


def digest_events(records: list[dict]) -> str:
    import hashlib

    h = hashlib.blake2b(digest_size=32)
    for r in records:
        if r.get("record_kind") != "EVENT":
            continue
        h.update(json.dumps(r, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()
