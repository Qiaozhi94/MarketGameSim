"""T810 skeleton: client control, idempotency, disconnect, and terminal states."""

import pytest


@pytest.mark.xfail(strict=True, reason="T810 interactive control is not implemented yet")
def test_interactive_control_contract():
    pytest.fail("T810 pending")
