"""Human commands translated onto the existing order-event production path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_game_sim.book.simulator import BookLevel, run_simulation
from market_game_sim.ledger.account import Account

HUMAN_AGENT_ID = "human"
MAX_ORDER_QUANTITY = 1_000
MAX_ACTIVE_ORDERS = 8


@dataclass(frozen=True, slots=True)
class HumanCommandResult:
    accepted: bool
    reason_code: str
    event_ids: tuple[str, ...]


class HumanAdapter:
    """Rebuild a deterministic market and route commands through matching.py."""

    def __init__(
        self,
        *,
        run_id: str = "interactive",
        initial_price_ticks: int = 10_000,
        mult: int = 1,
    ) -> None:
        self.run_id = run_id
        self.initial_price_ticks = initial_price_ticks
        self.mult = mult
        self._commands: list[tuple[str, dict[str, Any], int, int]] = []
        self.records: list[dict[str, Any]] = []
        self.accounts: dict[str, Account] = {}
        self.book = None
        self._rebuild()

    def place_order(
        self, payload: dict[str, Any], timestamp: int, input_seq: int
    ) -> HumanCommandResult:
        error = self._validate_order(payload)
        if error is not None:
            return HumanCommandResult(False, error, ())
        active = self._human_active_order_ids()
        if payload["order_id"] in self._known_order_ids():
            return HumanCommandResult(False, "INVALID_INPUT", ())
        if payload["order_type"] == "LIMIT" and len(active) >= MAX_ACTIVE_ORDERS:
            return HumanCommandResult(False, "RISK_REJECTED", ())
        return self._append_and_rebuild("PLACE_ORDER", payload, timestamp, input_seq)

    def cancel_order(
        self, payload: dict[str, Any], timestamp: int, input_seq: int
    ) -> HumanCommandResult:
        if set(payload) != {"order_id"} or not isinstance(payload.get("order_id"), str):
            return HumanCommandResult(False, "INVALID_INPUT", ())
        if payload["order_id"] not in self._human_active_order_ids():
            return HumanCommandResult(False, "UNKNOWN_ORDER", ())
        return self._append_and_rebuild("CANCEL_ORDER", payload, timestamp, input_seq)

    def _append_and_rebuild(
        self, action: str, payload: dict[str, Any], timestamp: int, input_seq: int
    ) -> HumanCommandResult:
        self._commands.append((action, dict(payload), timestamp, input_seq))
        self._rebuild()
        intent_id = f"human-intent-{input_seq}"
        arrival_index = next(
            (
                index
                for index, item in enumerate(self.records)
                if item.get("event_type") == "ORDER_ARRIVAL" and item.get("intent_id") == intent_id
            ),
            None,
        )
        if arrival_index is None:
            return HumanCommandResult(False, "INTERNAL_ABORT", ())
        arrival = self.records[arrival_index]
        decision = next(
            item
            for item in self.records
            if item.get("event_type") == "AGENT_DECIDE" and item.get("input_seq") == input_seq
        )
        produced = [decision, arrival]
        for item in self.records[arrival_index + 1 :]:
            if item.get("event_type") == "ORDER_ARRIVAL":
                break
            produced.append(item)
        event_ids = tuple(item["event_id"] for item in produced if "event_id" in item)
        if not arrival.get("accepted", False):
            reason = arrival.get("reject_reason")
            return HumanCommandResult(
                False,
                "RISK_REJECTED" if reason == "INSUFFICIENT_MARGIN" else "INVALID_INPUT",
                event_ids,
            )
        return HumanCommandResult(True, "OK", event_ids)

    def _rebuild(self) -> None:
        accounts = {
            HUMAN_AGENT_ID: Account(agent_id=HUMAN_AGENT_ID, wallet_units=1_000_000),
            "maker": Account(agent_id="maker", wallet_units=100_000_000),
        }
        levels = [
            BookLevel("BUY", "maker-bid", "maker", self.initial_price_ticks - 10, 10_000),
            BookLevel("SELL", "maker-ask", "maker", self.initial_price_ticks + 10, 10_000),
        ]
        events: list[dict[str, Any]] = []
        for action, payload, timestamp, input_seq in self._commands:
            decision_id = f"human-decision-{input_seq}"
            intent = {
                "intent_id": f"human-intent-{input_seq}",
                "action": "SUBMIT" if action == "PLACE_ORDER" else "CANCEL",
                "side": payload.get("side"),
                "order_type": payload.get("order_type"),
                "price_ticks": payload.get("price_ticks"),
                "quantity_units": payload.get("quantity_units"),
            }
            events.append(
                {
                    "event_type": "AGENT_DECIDE",
                    "timestamp": timestamp + 1,
                    "agent_id": HUMAN_AGENT_ID,
                    "rule_id": "human",
                    "input_seq": input_seq,
                    "intents": [intent],
                    "observation_event_id": "e2_0",
                    "decision_evidence": {
                        "schema_version": 1,
                        "goal_model_id": "human",
                        "goal_model_version": 1,
                        "desired_position_units": 0,
                        "executable_position_units": 0,
                        "constraint_binding": False,
                        "constraint_reason": None,
                        "trigger_provenance": "ENDOGENOUS_AGENT",
                        "observation_event_id": "e2_0",
                        "cursor_from_event_id": "e2_0",
                        "cursor_to_event_id": "e2_0",
                    },
                    "internal_state": {"input_seq": input_seq},
                }
            )
            if action == "PLACE_ORDER":
                events.append(
                    {
                        "event_type": "ORDER_ARRIVAL",
                        "timestamp": timestamp + 2,
                        "agent_id": HUMAN_AGENT_ID,
                        "order_id": payload["order_id"],
                        "action": "SUBMIT",
                        "side": payload["side"],
                        "order_type": payload["order_type"],
                        "price_ticks": payload["price_ticks"],
                        "quantity_units": payload["quantity_units"],
                        "origin": "AGENT",
                        "intent_id": f"human-intent-{input_seq}",
                        "decision_event_id": decision_id,
                        "submitted_at": timestamp,
                    }
                )
            else:
                events.append(
                    {
                        "event_type": "ORDER_ARRIVAL",
                        "timestamp": timestamp + 2,
                        "agent_id": HUMAN_AGENT_ID,
                        "order_id": f"cancel-{input_seq}",
                        "action": "CANCEL",
                        "target_order_id": payload["order_id"],
                        "side": None,
                        "order_type": None,
                        "price_ticks": None,
                        "quantity_units": None,
                        "origin": "AGENT",
                        "intent_id": f"human-intent-{input_seq}",
                        "decision_event_id": decision_id,
                        "submitted_at": timestamp,
                    }
                )
        self.records, self.book = run_simulation(
            levels,
            events,
            initial_price_ticks=self.initial_price_ticks,
            accounts=accounts,
            mult=self.mult,
            max_transactions=2 + len(events),
            run_id=self.run_id,
        )
        decisions = [item for item in self.records if item.get("event_type") == "AGENT_DECIDE"]
        arrivals = [item for item in self.records if item.get("event_type") == "ORDER_ARRIVAL"]
        for decision, arrival in zip(decisions, arrivals, strict=True):
            arrival["decision_event_id"] = decision["event_id"]
        self.accounts = accounts

    def _human_active_order_ids(self) -> set[str]:
        if self.book is None:
            return set()
        return {
            order.order_id
            for side in ("BUY", "SELL")
            for _, queue in self.book._side_refs(side)[0].items()  # type: ignore[attr-defined]
            for order in queue
            if order.agent_id == HUMAN_AGENT_ID and order.quantity_units > 0
        }

    def _known_order_ids(self) -> set[str]:
        return {
            payload["order_id"]
            for action, payload, _, _ in self._commands
            if action == "PLACE_ORDER"
        }

    @staticmethod
    def _validate_order(payload: dict[str, Any]) -> str | None:
        required = {"order_id", "side", "order_type", "quantity_units", "price_ticks"}
        if set(payload) != required:
            return "INVALID_INPUT"
        if not isinstance(payload["order_id"], str) or not payload["order_id"]:
            return "INVALID_INPUT"
        if payload["side"] not in {"BUY", "SELL"}:
            return "INVALID_INPUT"
        if payload["order_type"] not in {"LIMIT", "MARKET"}:
            return "INVALID_INPUT"
        qty = payload["quantity_units"]
        if type(qty) is not int or not 1 <= qty <= MAX_ORDER_QUANTITY:
            return "INVALID_INPUT"
        price = payload["price_ticks"]
        if payload["order_type"] == "MARKET":
            if price is not None:
                return "INVALID_INPUT"
        elif type(price) is not int or price <= 0:
            return "INVALID_INPUT"
        return None
