"""0.1.5 T206/T207: per-agent public-tape cursor consumption + EWMA (代理策略 §1-§2).

Every agent consumes the global public tape (``world["public_tape"]``, an
ordered list of public fills maintained by the kernel) through its own
cursor: the half-open interval ``(last_seen_market_event_id,
market_data_event_id]`` of fills since the last observation.  Consumption
happens **before** the cursor advances; on any mid-consumption failure the
cursor keeps its old value and a retry re-consumes the same interval
(design.md §5), so interval consumption must be a pure function of the tape.

The per-agent EWMA anchor (代理策略 §2) is updated from the consumed fills:
``anchor <- alpha*price + (1-alpha)*anchor`` with ``alpha = 1 - 2^(-1/tau)``,
``tau`` in fills.  The update is deterministic (Decimal, 28-digit, 代理策略
§9) and idempotent per interval -- replaying the same fills from the same
anchor yields the same anchor, which is what makes a retry safe.
"""

from __future__ import annotations

from bisect import bisect_right
from decimal import Decimal

#: The bootstrap ACCOUNT snapshot's r0 (event-schema.md §4.6.3) precedes
#: every business fill, so consuming from ``(INITIAL_CURSOR, first]``
#: includes all fills since genesis.
INITIAL_CURSOR_EVENT_ID = "e1_0"


def event_id_rank(event_id: str) -> tuple[int, int]:
    """Parse ``e{txn}_{idx}`` into its numeric ordering key (KR-003)."""
    txn_s, _, idx_s = event_id[1:].partition("_")
    return int(txn_s), int(idx_s)


def _fill_rank(fill: dict) -> tuple[int, int]:
    """Ordering key of a tape entry; raises on a malformed/absent event id."""
    return event_id_rank(fill["event_id"])


def tape_interval(
    tape: list[dict],
    cursor_from_event_id: str,
    cursor_to_event_id: str,
) -> list[dict]:
    """Fills in the half-open interval ``(from, to]`` of the public tape.

    ``from`` is exclusive, ``to`` is inclusive (代理策略 §1).  The tape is
    ordered by commit time == event-id rank, so the interval is a contiguous
    slice and both endpoints are found by binary search.

    A linear scan here is quadratic over a run: the tape grows with every
    fill, and every agent consumes through it once per observation, so the
    per-observation cost grew with the number of trades so far (measured: 30
    agents, work per logical second flat, wall clock per event +42% over 60
    logical seconds; at 2200 logical seconds the live market broke the
    NFR-501 budget at 0.549 s/s).  ``O(n)`` -> ``O(log n + k)`` with ``k``
    the interval size keeps the cost proportional to the *new* fills, which
    is what an observation actually consumes.

    The binary search only touches ``O(log n)`` entries, so -- unlike the
    former full scan -- it cannot by itself notice a corrupt entry elsewhere
    on the tape.  The returned slice is therefore validated entry by entry:
    consumption stays fail-closed on a malformed ``event_id`` (the rollback
    path in tests/integration/test_tape_cursor.py depends on it), and an
    out-of-order tape -- which would silently break the slice's premise --
    raises instead of returning a quietly wrong interval.
    """
    from_rank = event_id_rank(cursor_from_event_id)
    to_rank = event_id_rank(cursor_to_event_id)
    start = bisect_right(tape, from_rank, key=_fill_rank)
    end = bisect_right(tape, to_rank, lo=start, key=_fill_rank)
    interval = tape[start:end]
    for fill in interval:
        rank = _fill_rank(fill)
        if not from_rank < rank <= to_rank:
            raise ValueError(
                f"public tape is out of order: {fill['event_id']} is outside "
                f"({cursor_from_event_id}, {cursor_to_event_id}]"
            )
    return interval


def ewma_alpha(half_life_in_trades: int) -> Decimal:
    """``alpha = 1 - 2^(-1/tau)`` (代理策略 §2), Decimal 28-digit.

    ``tau`` (half-life) is in fills.  ``2^(-1/tau)`` is computed as
    ``exp(ln(2) * (-1/tau))`` because the stdlib Decimal ``**`` does not
    accept a Decimal exponent (代理策略 §9 mandates Decimal precision).
    """
    if half_life_in_trades <= 0:
        raise ValueError("half_life_in_trades must be positive")
    tau = Decimal(half_life_in_trades)
    ln2 = Decimal(2).ln()
    decay = (ln2 * (Decimal(-1) / tau)).exp()
    return Decimal(1) - decay


def update_ewma(
    ewma_value_units: int | None,
    ewma_sample_count: int,
    fills: list[dict],
    half_life_in_trades: int,
) -> tuple[int | None, int]:
    """Incrementally update a per-agent EWMA anchor over ``fills``.

    ``anchor <- alpha*price + (1-alpha)*anchor`` applied in fill order,
    **rounded to the nearest integer tick after EACH fill** (R018-C010: a
    batch-end-only rounding makes the anchor depend on how the fill sequence
    is partitioned into observation batches -- per-fill rounding is
    partition-invariant, so replaying the same fills in any batch split
    yields the same anchor; ADR-001 ROUND_HALF_EVEN via
    ``Decimal.to_integral_value``).  ``ewma_value_units=None`` means no
    anchor yet -- the first fill seeds it.  Returns the updated
    ``(value, count)``; the update is a pure function of its inputs, so a
    retry over the same fills is idempotent.
    """
    if half_life_in_trades <= 0:
        return ewma_value_units, ewma_sample_count
    alpha = ewma_alpha(half_life_in_trades)
    one_minus = Decimal(1) - alpha
    value: Decimal | None = Decimal(ewma_value_units) if ewma_value_units is not None else None
    count = ewma_sample_count
    for fill in fills:
        price = Decimal(fill["price_ticks"])
        value = price if value is None else alpha * price + one_minus * value
        count += 1
        # Per-fill rounding (R018-C010): the anchor is integer at every step,
        # so the next fill (in this call or a later batch) starts from the
        # same rounded value regardless of batch boundaries.
        value = value.to_integral_value(rounding="ROUND_HALF_EVEN")
    if value is None:
        return None, count
    return int(value), count
