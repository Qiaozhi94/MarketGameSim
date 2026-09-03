"""Closed, immutable projections of committed interactive state."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol

from market_game_sim.interactive.session import SessionView
from market_game_sim.interactive.types import ReasonCode, SessionState
from market_game_sim.replay.kline import DEFAULT_BAR_NS, build_klines
from market_game_sim.replay.state import RebuiltState, ReserveConfig, apply_event, new_state


class CommittedRecordSource(Protocol):
    """The narrow EventKernel surface accepted by the projector."""

    @property
    def committed_records(self) -> list[dict]: ...


@dataclass(frozen=True, slots=True)
class BookLevelView:
    price_ticks: int
    quantity_units: int
    order_count: int


@dataclass(frozen=True, slots=True)
class CompletedBarView:
    start_ns: int
    open: int
    high: int
    low: int
    close: int
    volume: int
    trade_count: int


@dataclass(frozen=True, slots=True)
class PublicTradeView:
    event_id: str
    timestamp: int
    price_ticks: int
    quantity_units: int
    taker_side: str


@dataclass(frozen=True, slots=True)
class MarketObservation:
    last_ticks: int | None
    best_bid: int | None
    best_ask: int | None
    bids: tuple[BookLevelView, ...]
    asks: tuple[BookLevelView, ...]
    public_trades: tuple[PublicTradeView, ...]
    completed_bars: tuple[CompletedBarView, ...]


@dataclass(frozen=True, slots=True)
class ActiveOrderView:
    order_id: str
    side: str
    price_ticks: int
    quantity_units: int


@dataclass(frozen=True, slots=True)
class HumanAccountObservation:
    wallet_units: int
    equity_units: int
    position_units: int
    entry_notional_units: int
    reserved_units: int
    margin_ratio_bp: int | None
    state: str
    active_orders: tuple[ActiveOrderView, ...]


@dataclass(frozen=True, slots=True)
class InputResultObservation:
    input_seq: int
    accepted: bool
    reason_code: ReasonCode
    assigned_timestamp: int | None
    event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InteractiveObservation:
    schema_version: int
    session_id: str
    session_state: SessionState
    snapshot_revision: int
    logical_timestamp: int | None
    market: MarketObservation
    account: HumanAccountObservation
    recent_input_results: tuple[InputResultObservation, ...]


class ObservationProjector:
    """Build the human-visible subset from a committed kernel boundary."""

    def __init__(
        self,
        *,
        human_agent_id: str,
        initial_price_ticks: int,
        mult: int = 1000,
        max_depth: int = 10,
        bar_ns: int = DEFAULT_BAR_NS,
        max_recent_results: int = 20,
    ) -> None:
        if not isinstance(human_agent_id, str) or not human_agent_id:
            raise ValueError("human_agent_id must be a non-empty string")
        for name, value in (
            ("initial_price_ticks", initial_price_ticks),
            ("mult", mult),
            ("bar_ns", bar_ns),
            ("max_recent_results", max_recent_results),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if type(max_depth) is not int or not 1 <= max_depth <= 10:
            raise ValueError("max_depth must be an integer from 1 to 10")
        if mult % 2:
            raise ValueError("mult must be even for half-tick equity")
        self._human_agent_id = human_agent_id
        self._initial_price_ticks = initial_price_ticks
        self._mult = mult
        self._max_depth = max_depth
        self._bar_ns = bar_ns
        self._max_recent_results = max_recent_results

    def project(
        self,
        *,
        session: SessionView,
        committed_source: CommittedRecordSource,
        recent_input_results: Sequence[Mapping[str, Any]] = (),
        after_event_id: str | None = None,
    ) -> InteractiveObservation:
        """Copy one closed view; speculative kernel queue state is unreachable."""

        records = self._visible_records(committed_source.committed_records, session)
        state = self._rebuild_committed_state(records)
        account = state.accounts.get(self._human_agent_id)
        if account is None:
            raise ValueError("human account is missing from committed state")
        trade_records = self._trade_records_after(records, after_event_id)
        market = self._project_market(state, records, trade_records, session.logical_timestamp)
        account_view = self._project_account(state, market)
        input_results = tuple(
            self._project_input_result(item)
            for item in recent_input_results[-self._max_recent_results :]
        )
        return InteractiveObservation(
            schema_version=1,
            session_id=session.session_id,
            session_state=session.state,
            snapshot_revision=session.snapshot_revision,
            logical_timestamp=session.logical_timestamp,
            market=market,
            account=account_view,
            recent_input_results=input_results,
        )

    def _rebuild_committed_state(self, records: tuple[dict, ...]) -> RebuiltState:
        state = new_state()
        state.reserve = ReserveConfig(
            mult=self._mult,
            initial_price_ticks=self._initial_price_ticks,
        )
        for record in records:
            if record.get("event_type") == "SNAPSHOT" and record.get("snapshot_type") == "BOOK":
                payload = record.get("payload", {})
                if payload.get("bids") or payload.get("asks"):
                    raise ValueError("interactive sessions require an empty bootstrap book")
            apply_event(state, record)
        return state

    @staticmethod
    def _visible_records(records: Sequence[dict], session: SessionView) -> tuple[dict, ...]:
        logical_timestamp = session.logical_timestamp
        if logical_timestamp is None:
            return ()
        if type(logical_timestamp) is not int or logical_timestamp < 0:
            raise ValueError("session logical_timestamp must be non-negative or None")
        return tuple(
            record
            for record in records
            if type(record.get("timestamp")) is int and record["timestamp"] <= logical_timestamp
        )

    @staticmethod
    def _trade_records_after(
        records: tuple[dict, ...], after_event_id: str | None
    ) -> tuple[dict, ...]:
        start = 0
        if after_event_id is not None:
            for index, record in enumerate(records):
                if record.get("event_id") == after_event_id:
                    start = index + 1
                    break
            else:
                raise ValueError(f"after_event_id {after_event_id!r} is not committed and visible")
        return tuple(
            record for record in records[start:] if record.get("event_type") == "TRADE_SETTLE"
        )

    def _project_market(
        self,
        state: RebuiltState,
        records: tuple[dict, ...],
        trade_records: tuple[dict, ...],
        logical_timestamp: int | None,
    ) -> MarketObservation:
        bids: dict[int, list[int]] = {}
        asks: dict[int, list[int]] = {}
        for order in state.book_orders.values():
            if order.remaining_qty <= 0 or order.price_ticks is None:
                continue
            levels = bids if order.side == "BUY" else asks
            levels.setdefault(order.price_ticks, []).append(order.remaining_qty)

        def level_views(
            levels: dict[int, list[int]], *, reverse: bool
        ) -> tuple[BookLevelView, ...]:
            return tuple(
                BookLevelView(
                    price_ticks=price,
                    quantity_units=sum(levels[price]),
                    order_count=len(levels[price]),
                )
                for price in sorted(levels, reverse=reverse)[: self._max_depth]
            )

        bid_views = level_views(bids, reverse=True)
        ask_views = level_views(asks, reverse=False)
        completed = []
        if logical_timestamp is not None:
            boundary = {"event_type": "OBSERVATION_BOUNDARY", "timestamp": logical_timestamp}
            completed = build_klines(
                [*records, boundary],
                period_ns=self._bar_ns,
                initial_price_ticks=self._initial_price_ticks,
            )
        return MarketObservation(
            last_ticks=state.last_ticks,
            best_bid=bid_views[0].price_ticks if bid_views else None,
            best_ask=ask_views[0].price_ticks if ask_views else None,
            bids=bid_views,
            asks=ask_views,
            public_trades=tuple(self._public_trade(item) for item in trade_records),
            completed_bars=tuple(
                CompletedBarView(
                    start_ns=bar.start_ns,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    trade_count=bar.trade_count,
                )
                for bar in completed
            ),
        )

    def _project_account(
        self, state: RebuiltState, market: MarketObservation
    ) -> HumanAccountObservation:
        account = state.accounts[self._human_agent_id]
        risk_mark = state.last_ticks or self._initial_price_ticks
        if market.best_bid is not None and market.best_ask is not None:
            valuation_mark_half_ticks = market.best_bid + market.best_ask
        elif state.last_ticks is not None:
            valuation_mark_half_ticks = state.last_ticks * 2
        else:
            valuation_mark_half_ticks = self._initial_price_ticks * 2
        unrealized = (
            account.position_units * valuation_mark_half_ticks * (self._mult // 2)
            - account.entry_notional_units
        )
        notional = abs(account.position_units) * risk_mark * self._mult
        risk_equity = (
            account.wallet_units
            + account.position_units * risk_mark * self._mult
            - account.entry_notional_units
        )
        active_orders = tuple(
            ActiveOrderView(
                order_id=order_id,
                side=order.side,
                price_ticks=order.price_ticks,
                quantity_units=order.remaining_qty,
            )
            for order_id, order in sorted(state.book_orders.items())
            if order.agent_id == self._human_agent_id
            and order.remaining_qty > 0
            and order.price_ticks is not None
        )
        return HumanAccountObservation(
            wallet_units=account.wallet_units,
            equity_units=account.wallet_units + unrealized,
            position_units=account.position_units,
            entry_notional_units=account.entry_notional_units,
            reserved_units=account.reserved_units,
            margin_ratio_bp=risk_equity * 10_000 // notional if notional else None,
            state=account.state,
            active_orders=active_orders,
        )

    @staticmethod
    def _public_trade(item: Mapping[str, Any]) -> PublicTradeView:
        return PublicTradeView(
            event_id=str(item["event_id"]),
            timestamp=int(item["timestamp"]),
            price_ticks=int(item["price_ticks"]),
            quantity_units=int(item["quantity_units"]),
            taker_side=str(item.get("taker_side", "")),
        )

    @staticmethod
    def _project_input_result(item: Mapping[str, Any]) -> InputResultObservation:
        event_ids = item.get("event_ids", ())
        if not isinstance(event_ids, Sequence) or isinstance(event_ids, (str, bytes)):
            raise ValueError("input result event_ids must be a sequence")
        return InputResultObservation(
            input_seq=int(item["input_seq"]),
            accepted=bool(item["accepted"]),
            reason_code=ReasonCode(item["reason_code"]),
            assigned_timestamp=(
                None if item.get("assigned_timestamp") is None else int(item["assigned_timestamp"])
            ),
            event_ids=tuple(str(event_id) for event_id in event_ids),
        )


class CommittedObservationStore:
    """Thread-safe latest-value store implementing ``observe(after_revision)``."""

    def __init__(self) -> None:
        self._latest: InteractiveObservation | None = None
        self._lock = Lock()

    def publish(self, snapshot: InteractiveObservation) -> None:
        if not isinstance(snapshot, InteractiveObservation):
            raise TypeError("snapshot must be an InteractiveObservation")
        with self._lock:
            if (
                self._latest is not None
                and snapshot.snapshot_revision <= self._latest.snapshot_revision
            ):
                raise ValueError("snapshot revision must increase")
            self._latest = snapshot

    def observe(self, after_revision: int | None = None) -> InteractiveObservation | None:
        if after_revision is not None and (type(after_revision) is not int or after_revision < 0):
            raise ValueError("after_revision must be a non-negative integer or None")
        with self._lock:
            if self._latest is None:
                return None
            if after_revision is not None and self._latest.snapshot_revision <= after_revision:
                return None
            return self._latest
