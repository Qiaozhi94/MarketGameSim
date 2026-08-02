"""T101 tests: immutable integer value objects and division helpers."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from market_game_sim.config.types import (
    Bp,
    Cash,
    Nanos,
    Price,
    Quantity,
    div_ceil,
    div_floor,
    div_round_toward_zero,
    round_fee,
)

# --------------------------------------------------------------------------- #
# Value-object construction
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "cls, attr",
    [
        (Price, "price_ticks"),
        (Quantity, "qty_units"),
        (Cash, "cash_units"),
        (Bp, "bp"),
        (Nanos, "nanos"),
    ],
)
class TestValueObjectConstruction:
    def test_accepts_int(self, cls, attr):
        obj = cls(**{attr: 42})
        assert getattr(obj, attr) == 42

    def test_accepts_zero(self, cls, attr):
        obj = cls(**{attr: 0})
        assert getattr(obj, attr) == 0

    def test_accepts_negative_int(self, cls, attr):
        obj = cls(**{attr: -7})
        assert getattr(obj, attr) == -7

    def test_rejects_float(self, cls, attr):
        with pytest.raises(TypeError, match="forbids float"):
            cls(**{attr: 3.14})

    def test_rejects_float_zero(self, cls, attr):
        with pytest.raises(TypeError, match="forbids float"):
            cls(**{attr: 0.0})

    def test_rejects_string(self, cls, attr):
        with pytest.raises(TypeError, match="requires int"):
            cls(**{attr: "42"})

    def test_rejects_decimal(self, cls, attr):
        with pytest.raises(TypeError, match="requires int"):
            cls(**{attr: Decimal("42")})

    def test_rejects_none(self, cls, attr):
        with pytest.raises(TypeError, match="requires int"):
            cls(**{attr: None})


# --------------------------------------------------------------------------- #
# Immutability
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "cls, attr",
    [
        (Price, "price_ticks"),
        (Quantity, "qty_units"),
        (Cash, "cash_units"),
        (Bp, "bp"),
        (Nanos, "nanos"),
    ],
)
class TestValueObjectImmutability:
    def test_frozen(self, cls, attr):
        obj = cls(**{attr: 10})
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, attr, 20)

    def test_hashable(self, cls, attr):
        a = cls(**{attr: 5})
        b = cls(**{attr: 5})
        c = cls(**{attr: 6})
        assert hash(a) == hash(b)
        assert hash(a) != hash(c)
        assert a == b
        assert a != c


# --------------------------------------------------------------------------- #
# Division helpers
# --------------------------------------------------------------------------- #


class TestDivCeil:
    def test_exact_division(self):
        assert div_ceil(10, 5) == 2

    def test_rounds_up_positive(self):
        assert div_ceil(7, 3) == 3

    def test_rounds_up_negative(self):
        assert div_ceil(-7, 3) == -2

    def test_zero_numerator(self):
        assert div_ceil(0, 5) == 0

    def test_negative_exact(self):
        assert div_ceil(-10, 5) == -2


class TestDivFloor:
    def test_exact_division(self):
        assert div_floor(10, 5) == 2

    def test_rounds_down_positive(self):
        assert div_floor(7, 3) == 2

    def test_rounds_down_negative(self):
        assert div_floor(-7, 3) == -3

    def test_zero_numerator(self):
        assert div_floor(0, 5) == 0


class TestDivRoundTowardZero:
    def test_exact_division(self):
        assert div_round_toward_zero(10, 5) == 2

    def test_truncates_positive(self):
        assert div_round_toward_zero(7, 3) == 2

    def test_truncates_negative(self):
        assert div_round_toward_zero(-7, 3) == -2

    def test_zero_numerator(self):
        assert div_round_toward_zero(0, 5) == 0


# --------------------------------------------------------------------------- #
# Fee rounding (ADR-001 §3)
# --------------------------------------------------------------------------- #


class TestRoundFee:
    """Fee rounding direction is always unfavorable to the agent."""

    def test_positive_bps_exact(self):
        assert round_fee(10_000, 5) == 5

    def test_positive_bps_rounds_up(self):
        assert round_fee(5_000, 5) == 3

    def test_positive_bps_small_notional(self):
        assert round_fee(1, 5) == 1

    def test_negative_bps_exact(self):
        assert round_fee(10_000, -1) == -1

    def test_negative_bps_floors_rebate(self):
        assert round_fee(5_000, -1) == 0

    def test_negative_bps_floors_rebate_larger(self):
        assert round_fee(5_000, -3) == -1

    def test_zero_bps(self):
        assert round_fee(99_999, 0) == 0

    def test_bench_001_maker_fee(self):
        assert round_fee(5_000, -1) == 0

    def test_bench_001_taker_fee(self):
        assert round_fee(5_000, 5) == 3
