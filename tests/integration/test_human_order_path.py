"""T808 skeleton: human order and cancel production path."""

import pytest


@pytest.mark.xfail(strict=True, reason="T808 human order adapter is not implemented yet")
def test_human_order_uses_existing_production_path():
    pytest.fail("T808 pending")
