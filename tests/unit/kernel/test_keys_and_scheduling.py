"""T201/T204/T202/T203: dual keys, priority classes, and scheduling invariants."""

from __future__ import annotations

import pytest

from market_game_sim.kernel.abort import ABORT_CODES, KernelAbort
from market_game_sim.kernel.keys import (
    EVENT_TYPE_PRIORITY_CLASS,
    LogKey,
    PriorityClass,
    QueueKey,
    make_queue_key,
    priority_class_of,
)
from market_game_sim.kernel.scheduling import (
    CLASS_REGRESSION_WHITELIST,
    check_class_regression,
    check_queue_monotonicity,
)


# --------------------------------------------------------------------------- #
# T204: Priority class enum (§3)
# --------------------------------------------------------------------------- #


class TestPriorityClass:
    def test_order_arrival_and_cancelled_share_class_0(self):
        assert priority_class_of("ORDER_ARRIVAL") == PriorityClass.ORDER == 0
        assert priority_class_of("ORDER_CANCELLED") == PriorityClass.ORDER == 0

    def test_trade_settle_and_margin_call_share_class_1(self):
        assert priority_class_of("TRADE_SETTLE") == PriorityClass.SETTLE == 1
        assert priority_class_of("MARGIN_CALL") == PriorityClass.SETTLE == 1

    def test_remaining_classes(self):
        assert priority_class_of("MARKET_DATA_PUBLISH") == PriorityClass.MARKET_DATA == 2
        assert priority_class_of("AGENT_OBSERVE") == PriorityClass.OBSERVE == 3
        assert priority_class_of("AGENT_DECIDE") == PriorityClass.DECIDE == 4
        assert priority_class_of("SNAPSHOT") == PriorityClass.SNAPSHOT == 5

    def test_all_event_types_covered(self):
        assert len(EVENT_TYPE_PRIORITY_CLASS) == 8

    def test_unknown_event_type_raises(self):
        with pytest.raises(ValueError, match="Unknown event_type"):
            priority_class_of("NONEXISTENT")


# --------------------------------------------------------------------------- #
# T201: Dual ordering keys (§1)
# --------------------------------------------------------------------------- #


class TestQueueKey:
    def test_timestamp_dominates(self):
        assert QueueKey(100, 5, 0) < QueueKey(200, 0, 99)

    def test_class_breaks_timestamp_tie(self):
        assert QueueKey(100, 0, 99) < QueueKey(100, 1, 0)

    def test_enqueue_seq_breaks_class_tie(self):
        assert QueueKey(100, 0, 1) < QueueKey(100, 0, 2)

    def test_equal_keys_not_strictly_less(self):
        k = QueueKey(100, 0, 1)
        assert not (k < k)
        assert k <= k

    def test_frozen(self):
        k = QueueKey(100, 0, 1)
        with pytest.raises(Exception):
            k.timestamp = 200  # type: ignore[misc]


class TestLogKey:
    def test_timestamp_dominates(self):
        assert LogKey(100, 99, 50) < LogKey(200, 0, 0)

    def test_transaction_seq_breaks_timestamp_tie(self):
        assert LogKey(100, 1, 99) < LogKey(100, 2, 0)

    def test_record_index_breaks_transaction_tie(self):
        assert LogKey(100, 1, 0) < LogKey(100, 1, 1)

    def test_frozen(self):
        k = LogKey(100, 1, 0)
        with pytest.raises(Exception):
            k.transaction_seq = 2  # type: ignore[misc]


class TestMakeQueueKey:
    def test_builds_correct_key(self):
        qk = make_queue_key(500, "SNAPSHOT", 3)
        assert qk.timestamp == 500
        assert qk.priority_class == 5
        assert qk.enqueue_seq == 3


# --------------------------------------------------------------------------- #
# T202: KR-006 queue monotonicity (§1.1)
# --------------------------------------------------------------------------- #


class TestQueueMonotonicity:
    def test_greater_key_passes(self):
        check_queue_monotonicity(
            QueueKey(100, 0, 2),
            QueueKey(100, 0, 1),
        )

    def test_equal_key_raises(self):
        with pytest.raises(KernelAbort) as exc:
            check_queue_monotonicity(
                QueueKey(100, 0, 1),
                QueueKey(100, 0, 1),
            )
        assert exc.value.abort_code == "QUEUE_KEY_MONOTONICITY"

    def test_lesser_key_raises(self):
        with pytest.raises(KernelAbort) as exc:
            check_queue_monotonicity(
                QueueKey(100, 0, 1),
                QueueKey(100, 0, 2),
            )
        assert exc.value.abort_code == "QUEUE_KEY_MONOTONICITY"

    def test_lesser_timestamp_raises_even_if_seq_higher(self):
        with pytest.raises(KernelAbort):
            check_queue_monotonicity(
                QueueKey(50, 0, 99),
                QueueKey(100, 0, 1),
            )

    def test_detail_contains_both_keys(self):
        with pytest.raises(KernelAbort) as exc:
            check_queue_monotonicity(
                QueueKey(100, 0, 1),
                QueueKey(100, 0, 2),
            )
        assert "100" in str(exc.value)


# --------------------------------------------------------------------------- #
# T203: Class-regression whitelist (§1.2)
# --------------------------------------------------------------------------- #


class TestClassRegression:
    def test_agent_decide_to_order_arrival_passes_with_advance(self):
        check_class_regression("AGENT_DECIDE", "ORDER_ARRIVAL", 100, 101)

    def test_margin_call_to_order_arrival_passes_with_advance(self):
        check_class_regression("MARGIN_CALL", "ORDER_ARRIVAL", 100, 101)

    def test_non_regression_passes(self):
        check_class_regression("ORDER_ARRIVAL", "AGENT_DECIDE", 100, 100)
        check_class_regression("ORDER_ARRIVAL", "TRADE_SETTLE", 100, 100)
        check_class_regression("AGENT_OBSERVE", "AGENT_DECIDE", 100, 100)

    def test_non_whitelisted_regression_raises(self):
        with pytest.raises(KernelAbort) as exc:
            check_class_regression("AGENT_OBSERVE", "ORDER_ARRIVAL", 100, 200)
        assert exc.value.abort_code == "CLASS_REGRESSION_NOT_WHITELISTED"

    def test_whitelisted_regression_without_advance_raises(self):
        with pytest.raises(KernelAbort) as exc:
            check_class_regression("AGENT_DECIDE", "ORDER_ARRIVAL", 100, 100)
        assert exc.value.abort_code == "CLASS_REGRESSION_NOT_WHITELISTED"

    def test_whitelisted_regression_with_negative_advance_raises(self):
        with pytest.raises(KernelAbort) as exc:
            check_class_regression("MARGIN_CALL", "ORDER_ARRIVAL", 200, 100)
        assert exc.value.abort_code == "CLASS_REGRESSION_NOT_WHITELISTED"

    def test_whitelist_has_exactly_two_entries(self):
        assert len(CLASS_REGRESSION_WHITELIST) == 2
        assert ("AGENT_DECIDE", "ORDER_ARRIVAL") in CLASS_REGRESSION_WHITELIST
        assert ("MARGIN_CALL", "ORDER_ARRIVAL") in CLASS_REGRESSION_WHITELIST


# --------------------------------------------------------------------------- #
# Abort codes (§6.2)
# --------------------------------------------------------------------------- #


class TestAbortCodes:
    def test_all_six_codes_present(self):
        assert len(ABORT_CODES) == 6
        for code in [
            "QUEUE_KEY_MONOTONICITY",
            "CLASS_REGRESSION_NOT_WHITELISTED",
            "CONSERVATION_BREACH",
            "ILLEGAL_STATE_TRANSITION",
            "CONFIG_INVARIANT",
            "INTERNAL",
        ]:
            assert code in ABORT_CODES

    def test_kernel_abort_rejects_unknown_code(self):
        with pytest.raises(ValueError, match="Unknown abort_code"):
            KernelAbort(abort_code="MADE_UP", detail="x")  # type: ignore[arg-type]

    def test_kernel_abort_carries_code_and_detail(self):
        e = KernelAbort(abort_code="INTERNAL", detail="boom")
        assert e.abort_code == "INTERNAL"
        assert e.detail == "boom"
        assert "INTERNAL" in str(e)
        assert "boom" in str(e)
