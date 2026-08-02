"""T502: Crypto perpetual regime — default stub implementation (v0.1 / D-1).

24/7 trading, instant settlement, no price limits, no circuit breakers.
All hooks are pass-through in 0.1.1; 0.1.2 replaces ``margin_rule`` with
the real leverage-tier check.

Hooks only **reject** or **delay** — they never rewrite order fields.
"""

from __future__ import annotations

from typing import Any

from market_game_sim.ledger.account import Account


class CryptoPerpRegime:
    """Default regime for the crypto perpetual market.

    - ``validate_order``: always pass (0.1.1)
    - ``session_state``: always OPEN (24/7)
    - ``settlement_rule``: instant settlement
    - ``margin_rule``: always pass (0.1.1 stub; 0.1.2 replaces)
    - ``price_bound``: no limits (None, None)
    """

    def validate_order(
        self,
        event: dict[str, Any],
        account: Account | None,
        book: Any,
        config: Any,
    ) -> tuple[bool, str | None]:
        return True, None

    def session_state(self, timestamp_ns: int, config: Any) -> str:
        return "OPEN"

    def settlement_rule(
        self, event: dict[str, Any], config: Any
    ) -> dict[str, Any]:
        return {"method": "INSTANT"}

    def margin_rule(
        self,
        account: Account,
        position_delta: int,
        price_ticks: int,
        config: Any,
        reserved_after: int,
    ) -> tuple[bool, str | None]:
        return True, None

    def price_bound(
        self, price_ticks: int, config: Any
    ) -> tuple[int | None, int | None]:
        return None, None
