"""T101: Immutable integer value objects (ADR-001 §1).

All domain amounts — price, quantity, cash, basis points, time — are carried
as Python ``int`` in minimum units.  ``float`` is forbidden at construction
time; ``decimal.Decimal`` is used only during config parsing (T102) and never
enters a value object.

These types are intentionally minimal: they wrap an ``int``, reject ``float``,
and are frozen.  Arithmetic is done on the raw ``int`` via the exposed
attribute; the wrapper exists to prevent accidental float contamination and
to make unit intent explicit at API boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Integer division helpers (ADR-001 §3 — fee rounding is the sole rounding site)
# --------------------------------------------------------------------------- #


def div_ceil(a: int, b: int) -> int:
    """Ceiling division: quotient rounded toward +∞."""
    return -(-a // b)


def div_floor(a: int, b: int) -> int:
    """Floor division: quotient rounded toward −∞."""
    return a // b


def div_round_toward_zero(a: int, b: int) -> int:
    """Truncation division: quotient rounded toward zero."""
    q, r = divmod(a, b)
    if r != 0 and ((a < 0) != (b < 0)):
        q += 1
    return q


def round_fee(notional_units: int, bps: int) -> int:
    """Fee rounded unfavorably to the agent (ADR-001 §3).

    ``fee = notional × bps / 10 000``.

    * Positive ``bps`` (taker pays): **ceil** → agent pays more.
    * Negative ``bps`` (maker rebate): **ceil** → agent receives less,
      because ``ceil`` of a negative number is the same as flooring the
      (positive) rebate amount.

    Both cases reduce to ``div_ceil(notional × bps, 10 000)``.
    """
    return div_ceil(notional_units * bps, 10_000)


# --------------------------------------------------------------------------- #
# Value objects
# --------------------------------------------------------------------------- #


def _reject_non_int(value: object, type_name: str) -> None:
    if isinstance(value, float):
        raise TypeError(f"{type_name} forbids float construction; pass an int in minimum units")
    if not isinstance(value, int):
        raise TypeError(f"{type_name} requires int, got {type(value).__name__}")


@dataclass(frozen=True)
class Price:
    """Price in tick units (``tick_size``)."""

    price_ticks: int

    def __post_init__(self) -> None:
        _reject_non_int(self.price_ticks, "Price")


@dataclass(frozen=True)
class Quantity:
    """Quantity in minimum-quantity units (``min_quantity``)."""

    qty_units: int

    def __post_init__(self) -> None:
        _reject_non_int(self.qty_units, "Quantity")


@dataclass(frozen=True)
class Cash:
    """Cash amount in minimum-cash units (``cash_unit``)."""

    cash_units: int

    def __post_init__(self) -> None:
        _reject_non_int(self.cash_units, "Cash")


@dataclass(frozen=True)
class Bp:
    """Basis points (万分数, 1 bp = 1/10 000)."""

    bp: int

    def __post_init__(self) -> None:
        _reject_non_int(self.bp, "Bp")


@dataclass(frozen=True)
class Nanos:
    """Logical time in nanoseconds."""

    nanos: int

    def __post_init__(self) -> None:
        _reject_non_int(self.nanos, "Nanos")
