"""T501: Regime hook interface (v0.1 / D-1).

Call points (撮合 §5):
1. ``validate_order`` — admission check before matching (0.1.1 stub, always pass)
2. ``session_state``  — trading session state (24/7 for crypto perp)
3. ``settlement_rule``— settlement mechanism (instant for crypto perp)
4. ``margin_rule``    — margin check (0.1.1 stub, always pass)
5. ``price_bound``    — price limits (none for crypto perp)

Hooks can only **reject** (return False/accepted=False) or **delay**;
they must NOT rewrite order fields.
"""

from __future__ import annotations

from typing import Any, Protocol

from market_game_sim.ledger.account import Account


class RegimeHook(Protocol):
    """Injectable institutional rules.

    The five call points below correspond to 撮合 §5 steps 1-7.
    """

    def validate_order(
        self,
        event: dict[str, Any],
        account: Account | None,
        book: Any,
        config: Any,
    ) -> tuple[bool, str | None]:
        """Admission gate (撮合 §5 step 1).

        Returns ``(accepted, reject_reason)``.  ``False`` means the order
        is rejected and the transaction produces only r0 (accepted=false).
        """
        ...

    def session_state(self, timestamp_ns: int, config: Any) -> str:
        """Trading session state (撮合 §5 step 0 — pre-admission gate).

        Returns one of ``"OPEN"`` / ``"CLOSED"`` / ``"HALTED"``.
        """
        ...

    def settlement_rule(self, event: dict[str, Any], config: Any) -> dict[str, Any]:
        """Settlement rule for a matched fill.

        Returns a dict with at least ``{"method": "INSTANT" | "DELAYED" | ...}``.
        For 0.1.1 (instant settlement) the fill is applied inline.
        """
        ...

    def margin_rule(
        self,
        account: Account,
        position_delta: int,
        price_ticks: int,
        config: Any,
        reserved_after: int,
    ) -> tuple[bool, str | None]:
        """Margin gate (撮合 §5 step 3).

        Returns ``(pass, reject_reason)``.  For 0.1.1 this is a stub
        (always True); 0.1.2 replaces it with the real check.
        """
        ...

    def price_bound(self, price_ticks: int, config: Any) -> tuple[int | None, int | None]:
        """Price limits (撮合 §5 step 6 — risk check context).

        Returns ``(lower, upper)`` in ticks.  ``None`` means no bound.
        For crypto perp regime both are ``None`` (no limits).
        """
        ...
