"""T103 (FR-019): Per-frame state sequence (E1 input).

A frame is the complete state after a committed transaction.  The bootstrap
is the two contiguous SNAPSHOT transactions (ACCOUNT at ``transaction_seq=b``,
BOOK at ``b+1``, per event-schema §4.6.3's decidable snapshot rule): frame 0 is
the state after the BOOK snapshot commits; frame k is the state after
``transaction_seq = b + k`` (when the bootstrap barrier is fully enforced,
``b = 2`` and this is ``k + 2``).  A run with ``T`` committed transactions
(``T >= b + 1``) yields ``T - b`` frames.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from market_game_sim.replay.downsample import DownsampleRule
from market_game_sim.replay.state import (
    RebuiltState,
    ReplayAccount,
    ReserveConfig,
    apply_event,
    new_state,
)

ACCOUNT_FIELDS = (
    "agent_id",
    "wallet_units",
    "position_units",
    "entry_notional_units",
    "reserved_units",
    "realized_pnl_units",
    "state",
    "margin_ratio_bp",
    "liquidation_generation",
    "chain_id",
    "chain_depth",
)


@dataclass
class Frame:
    """A single reconstructed frame."""

    frame_index: int
    transaction_seq: int
    timestamp: int = 0
    last_ticks: int | None = None
    accounts: dict[str, dict[str, Any]] = field(default_factory=dict)
    exchange: dict[str, int] = field(default_factory=dict)
    book: dict[str, list[dict[str, int]]] = field(default_factory=dict)


def _margin_ratio_bp(acc: ReplayAccount, last_ticks: int | None, mult: int) -> int | None:
    if last_ticks is None or acc.position_units == 0:
        return None
    notional = abs(acc.position_units) * last_ticks * mult
    if notional == 0:
        return None
    risk_equity = acc.wallet_units + (
        acc.position_units * last_ticks * mult - acc.entry_notional_units
    )
    return risk_equity * 10000 // notional


def _project_accounts(state: RebuiltState, mult: int) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for aid, acc in sorted(state.accounts.items()):
        out[aid] = {
            "agent_id": aid,
            "wallet_units": acc.wallet_units,
            "position_units": acc.position_units,
            "entry_notional_units": acc.entry_notional_units,
            "reserved_units": acc.reserved_units,
            "realized_pnl_units": acc.realized_pnl_units,
            "state": acc.state,
            "margin_ratio_bp": _margin_ratio_bp(acc, state.last_ticks, mult),
            "liquidation_generation": acc.liquidation_generation,
            "chain_id": acc.chain_id,
            "chain_depth": acc.chain_depth,
        }
    return out


def _project_book(state: RebuiltState) -> dict[str, list[dict[str, int]]]:
    bids: dict[int, list[int]] = {}
    asks: dict[int, list[int]] = {}
    for order in state.book_orders.values():
        if order.remaining_qty <= 0 or order.price_ticks is None:
            continue
        levels = bids if order.side == "BUY" else asks
        levels.setdefault(order.price_ticks, []).append(order.remaining_qty)

    def levels_to_list(levels: dict[int, list[int]], reverse: bool) -> list[dict[str, int]]:
        prices = sorted(levels.keys(), reverse=reverse)
        return [
            {
                "price_ticks": p,
                "quantity_units": sum(levels[p]),
                "order_count": len(levels[p]),
            }
            for p in prices
        ]

    return {
        "bids": levels_to_list(bids, reverse=True),
        "asks": levels_to_list(asks, reverse=False),
    }


def build_frame(
    state: RebuiltState, frame_index: int, transaction_seq: int, mult: int, timestamp: int = 0
) -> Frame:
    return Frame(
        frame_index=frame_index,
        transaction_seq=transaction_seq,
        timestamp=timestamp,
        last_ticks=state.last_ticks,
        accounts=_project_accounts(state, mult),
        exchange={"fee_cash_units": state.fee_cash_units, "risk_pnl_units": state.risk_pnl_units},
        book=_project_book(state),
    )


def _build_frames(
    events: list[dict[str, Any]],
    mult: int,
    *,
    fee_bps_cap: int = 0,
    initial_price_ticks: int = 10000,
    agent_initial_bp: dict[str, int] | None = None,
    downsample: DownsampleRule | None = None,
) -> list[Frame]:
    """Build the per-frame sequence from EVENT records (internal, test-facing).

    ``mult`` (and the optional reserved config) are not derivable from the
    log (ADR-001 forbids float derivation); they are threaded in to recompute
    the derived ``margin_ratio_bp`` / ``reserved_units`` fields per frame.

    ``downsample`` (when given) filters frames DURING reconstruction with the
    same ``frame_index`` modulo predicate as :func:`apply_downsample`, so the
    sampled product never materializes the full frame list (round-2 review
    F-E).  The E1 path always calls with ``downsample=None``.

    Frame 0 is the state once the bootstrap BOOK snapshot is committed (the
    point where both ACCOUNT + BOOK snapshots are present); frame k follows
    transaction ``bootstrap_txn + k`` (``bootstrap_txn`` = the BOOK snapshot's
    ``transaction_seq``; equals 2 when the bootstrap barrier is fully
    enforced, matching the spec's ``frame k = txn k + 2``).
    """
    by_txn: dict[int, list[dict[str, Any]]] = {}
    for e in events:
        by_txn.setdefault(e["transaction_seq"], []).append(e)

    state = new_state()
    state.reserve = ReserveConfig(
        mult=mult,
        fee_bps_cap=fee_bps_cap,
        initial_price_ticks=initial_price_ticks,
        agent_initial_bp=dict(agent_initial_bp or {}),
    )
    frames: list[Frame] = []
    bootstrap_txn: int | None = None

    for txn_seq in sorted(by_txn.keys()):
        txn_timestamp = 0
        for event in by_txn[txn_seq]:
            apply_event(state, event)
            ev_ts = event.get("timestamp", 0)
            if isinstance(ev_ts, int):
                txn_timestamp = max(txn_timestamp, ev_ts)
            if (
                bootstrap_txn is None
                and event.get("event_type") == "SNAPSHOT"
                and event.get("snapshot_type") == "BOOK"
            ):
                bootstrap_txn = txn_seq
        if bootstrap_txn is not None and txn_seq >= bootstrap_txn:
            frame_index = txn_seq - bootstrap_txn
            if downsample is not None and (
                (frame_index - downsample.offset) % downsample.keep_every != 0
            ):
                continue
            frames.append(
                build_frame(
                    state,
                    frame_index=frame_index,
                    transaction_seq=txn_seq,
                    mult=mult,
                    timestamp=txn_timestamp,
                )
            )

    return frames


def build_frames_from_log(log, mult: int, **kwargs) -> list[Frame]:
    """Build frames from a :class:`market_game_sim.replay.reader.LogData`."""
    return _build_frames(log.events, mult, **kwargs)
