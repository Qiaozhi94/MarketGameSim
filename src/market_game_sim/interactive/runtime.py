"""Transport-independent Phase-2 interactive application service."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import RLock
from typing import Any

from market_game_sim.interactive.adapter import HUMAN_AGENT_ID, HumanAdapter
from market_game_sim.interactive.pacing import IdempotencyConflictError, InputInbox
from market_game_sim.interactive.types import InputAction, ReasonCode, SessionState
from market_game_sim.ledger.account import margin_ratio_bp, risk_equity


@dataclass(frozen=True, slots=True)
class InputResult:
    input_seq: int | None
    accepted: bool
    reason_code: ReasonCode
    assigned_timestamp: int | None
    event_ids: tuple[str, ...]
    snapshot_revision: int


class InteractiveRuntime:
    """Single-writer session API shared by HTTP and integration callers."""

    def __init__(self, session_id: str = "interactive-s7") -> None:
        self.session_id = session_id
        self.state = SessionState.CREATED
        self.snapshot_revision = 0
        self.logical_timestamp = 0
        self._adapter = HumanAdapter(run_id=session_id)
        self._inbox = InputInbox()
        self._results: dict[int, InputResult] = {}
        self._lock = RLock()

    @property
    def adapter(self) -> HumanAdapter:
        return self._adapter

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self.state is not SessionState.CREATED:
                return self.view(error_code=ReasonCode.INVALID_STATE)
            self.state = SessionState.PAUSED
            self.snapshot_revision += 1
            return self.view()

    def place_order(self, command: dict[str, Any]) -> InputResult:
        return self._mutate(InputAction.PLACE_ORDER, command)

    def cancel_order(self, command: dict[str, Any]) -> InputResult:
        return self._mutate(InputAction.CANCEL_ORDER, command)

    def control(self, action: InputAction, client_request_id: str) -> InputResult:
        if action not in {InputAction.PAUSE, InputAction.RESUME, InputAction.STEP, InputAction.END}:
            return self._rejected(None, ReasonCode.INVALID_INPUT)
        return self._mutate(action, {"client_request_id": client_request_id})

    def disconnect(self) -> None:
        """Finish the current atomic mutation, then stop continuous progress."""

        with self._lock:
            if self.state is SessionState.RUNNING:
                self.state = SessionState.PAUSED
                self.snapshot_revision += 1

    def input_result(self, input_seq: int) -> InputResult | None:
        return self._results.get(input_seq)

    def view(self, *, error_code: ReasonCode | None = None) -> dict[str, Any]:
        with self._lock:
            book = self._adapter.book
            account = self._adapter.accounts[HUMAN_AGENT_ID]
            bids = self._levels("BUY", reverse=True)
            asks = self._levels("SELL", reverse=False)
            mark = book.last_ticks or self._adapter.initial_price_ticks
            return {
                "schema_version": 1,
                "session_id": self.session_id,
                "session_state": self.state.value,
                "ui_state": self._ui_state(),
                "snapshot_revision": self.snapshot_revision,
                "logical_timestamp": self.logical_timestamp,
                "error_code": error_code.value if error_code else None,
                "market": {
                    "last_ticks": book.last_ticks,
                    "best_bid": book.best_bid(),
                    "best_ask": book.best_ask(),
                    "bids": bids,
                    "asks": asks,
                    "completed_bars": [],
                },
                "account": {
                    "wallet_units": account.wallet_units,
                    "equity_units": risk_equity(account, mark, self._adapter.mult),
                    "position_units": account.position_units,
                    "entry_notional_units": account.entry_notional_units,
                    "reserved_units": account.reserved_units,
                    "margin_ratio_bp": margin_ratio_bp(account, mark, self._adapter.mult),
                    "state": account.state.value,
                    "active_orders": self._active_orders(),
                },
                "recent_input_results": [
                    self._result_dict(result) for _, result in sorted(self._results.items())[-20:]
                ],
                "boundary_notice": "合成市场 · 无真实资金 · 非交易建议",
            }

    def _mutate(self, action: InputAction, command: dict[str, Any]) -> InputResult:
        with self._lock:
            request_id = command.get("client_request_id")
            payload = {key: value for key, value in command.items() if key != "client_request_id"}
            try:
                pending = self._inbox.submit(request_id, action, payload)
            except IdempotencyConflictError:
                return self._rejected(None, ReasonCode.IDEMPOTENCY_CONFLICT)
            except ValueError as exc:
                code = getattr(exc, "reason_code", ReasonCode.INVALID_INPUT)
                return self._rejected(None, code)
            previous = self._results.get(pending.input_seq)
            if previous is not None:
                return previous
            if self.state in {SessionState.COMPLETED, SessionState.ABORTED, SessionState.CREATED}:
                return self._store(pending.input_seq, False, ReasonCode.INVALID_STATE, None, ())

            timestamp = self.logical_timestamp
            if action is InputAction.PLACE_ORDER:
                try:
                    outcome = self._adapter.place_order(payload, timestamp, pending.input_seq)
                except Exception:
                    self.state = SessionState.ABORTED
                    return self._store(
                        pending.input_seq, False, ReasonCode.INTERNAL_ABORT, None, ()
                    )
                code = ReasonCode(outcome.reason_code)
                return self._store(
                    pending.input_seq, outcome.accepted, code, timestamp, outcome.event_ids
                )
            if action is InputAction.CANCEL_ORDER:
                try:
                    outcome = self._adapter.cancel_order(payload, timestamp, pending.input_seq)
                except Exception:
                    self.state = SessionState.ABORTED
                    return self._store(
                        pending.input_seq, False, ReasonCode.INTERNAL_ABORT, None, ()
                    )
                code = ReasonCode(outcome.reason_code)
                return self._store(
                    pending.input_seq, outcome.accepted, code, timestamp, outcome.event_ids
                )

            valid = (
                (action is InputAction.RESUME and self.state is SessionState.PAUSED)
                or (action is InputAction.PAUSE and self.state is SessionState.RUNNING)
                or (action is InputAction.STEP and self.state is SessionState.PAUSED)
                or action is InputAction.END
            )
            if not valid:
                return self._store(pending.input_seq, False, ReasonCode.INVALID_STATE, None, ())
            if action is InputAction.RESUME:
                self.state = SessionState.RUNNING
            elif action is InputAction.PAUSE:
                self.state = SessionState.PAUSED
            elif action is InputAction.STEP:
                self.logical_timestamp += 1_000_000_000
            else:
                self.state = SessionState.COMPLETED
            return self._store(pending.input_seq, True, ReasonCode.OK, timestamp, ())

    def _store(
        self,
        seq: int,
        accepted: bool,
        code: ReasonCode,
        timestamp: int | None,
        event_ids: tuple[str, ...],
    ) -> InputResult:
        self._inbox.drain()
        self.snapshot_revision += 1
        result = InputResult(seq, accepted, code, timestamp, event_ids, self.snapshot_revision)
        self._results[seq] = result
        return result

    def _rejected(self, seq: int | None, code: ReasonCode) -> InputResult:
        return InputResult(seq, False, code, None, (), self.snapshot_revision)

    @staticmethod
    def _result_dict(result: InputResult) -> dict[str, Any]:
        value = asdict(result)
        value["reason_code"] = result.reason_code.value
        value["event_ids"] = list(result.event_ids)
        return value

    def _levels(self, side: str, *, reverse: bool) -> list[dict[str, int]]:
        levels = (
            self._adapter.book.bid_levels() if side == "BUY" else self._adapter.book.ask_levels()
        )
        return [
            {"price_ticks": price, "quantity_units": qty}
            for price, qty in sorted(levels, reverse=reverse)[:10]
        ]

    def _active_orders(self) -> list[dict[str, Any]]:
        orders = []
        book = self._adapter.book
        for side in ("BUY", "SELL"):
            for queue in book._side_refs(side)[0].values():  # type: ignore[attr-defined]
                for order in queue:
                    if order.agent_id == HUMAN_AGENT_ID and order.quantity_units > 0:
                        orders.append(
                            {
                                "order_id": order.order_id,
                                "side": order.side,
                                "price_ticks": order.price_ticks,
                                "quantity_units": order.quantity_units,
                            }
                        )
        return sorted(orders, key=lambda item: item["order_id"])

    def _ui_state(self) -> str | None:
        if self.state is SessionState.CREATED:
            return "loading"
        if self.state is SessionState.PAUSED:
            return "paused"
        if self.state is SessionState.COMPLETED:
            return "completed"
        if self.state is SessionState.ABORTED:
            return "aborted"
        if self._adapter.book.best_bid() is None and self._adapter.book.best_ask() is None:
            return "empty"
        return None
