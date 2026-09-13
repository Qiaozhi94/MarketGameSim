"""V032-DOC-002 回归门：委托幂等键的重试语义不得回退。

同一逻辑委托断线重试必须复用原 `client_request_id`，新委托或不同 payload 才用新键；
恢复「委托幂等键不可复用」等旧措辞时本测试必须变红。
"""

from __future__ import annotations

from pathlib import Path

DESIGN = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "features"
    / "0.3"
    / "0.3.2-web-trading-terminal"
    / "design.md"
).read_text(encoding="utf-8")


def test_order_idempotency_key_retry_contract_locked():
    assert "复用原 `client_request_id`" in DESIGN
    assert "新委托或不同 payload 才使用新键" in DESIGN
    assert "幂等键不可复用" not in DESIGN
