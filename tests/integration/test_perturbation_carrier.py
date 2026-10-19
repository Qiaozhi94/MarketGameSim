"""0.4.2 T1125（AC-608）：载体 C 的按种子清单与 live 市场开放终端前的预热。

规格见 docs/features/0.4/0.4.2-human-perturbation/spec.md FR-605、§6；设计见 design.md §5。
"""

from __future__ import annotations

import json
import pathlib
import shutil

import pytest

from market_game_sim.experiment.h2.live_market import (
    TERMINAL_NOT_APPLICABLE,
    TERMINAL_OPEN,
    TERMINAL_WARMING_UP,
    WARMUP_BURN_IN_NS,
    WARMUP_CAP_NS,
    LiveMarket,
    build_market,
    main,
)
from market_game_sim.experiment.perturbation import carrier, session
from market_game_sim.experiment.roster import RosterError, load_roster
from market_game_sim.kernel.abort import KernelAbort
from market_game_sim.metrics.anchor_scan import load_preregistration
from market_game_sim.metrics.quality_run import BURN_IN_NS
from market_game_sim.metrics.stability_effect import WINDOW_END_NS

S = 1_000_000_000
SEED7 = "roster-e7c9bdeeb558c5b7ed849d73e0e33704"
_MARKET = {"side": "BUY", "order_type": "MARKET", "quantity_units": 1, "price_ticks": None}


def _value_family(roster):
    (family,) = [f for f in roster.families if f.family_id == "value_investor"]
    return family


def test_carrier_roster_hashes_to_id_with_value_family_params():
    """AC-608：载体清单内容哈希到 roster_id，价值族参数为 count 6 / sensitivity 150"""
    files = sorted(carrier.ROSTER_DIR.glob("roster-*.json"))
    assert [f.stem for f in files] == [SEED7]
    prereg = load_preregistration()
    for path in files:
        roster = load_roster(carrier.ROSTER_DIR, path.stem)
        family = _value_family(roster)
        assert family.count == carrier.CARRIER_COUNT == 6
        assert dict(family.params) == {
            **prereg["value_family_params"],
            "sensitivity_x1000": carrier.CARRIER_SENSITIVITY_X1000,
        }
        assert family.params["sensitivity_x1000"] == 150
        # 文件就是生成函数的输出：载体只有一个来源，不会和 0.4.3 的固定项漂开。
        assert path.read_text(encoding="utf-8") == carrier.carrier_roster(roster.seed).to_json()
    assert load_roster(carrier.ROSTER_DIR, SEED7).seed == 7
    # 每个种子一个 roster_id；载体 C 不是 0.4.3 的锚定清单（载体 B）。
    assert carrier.carrier_roster(8).roster_id not in {
        SEED7,
        "roster-2425a8200ca1a1e748a34a7e9d8b99ba",
    }


def test_tampered_carrier_file_is_refused(tmp_path):
    shutil.copy(carrier.ROSTER_DIR / f"{SEED7}.json", tmp_path / f"{SEED7}.json")
    path = tmp_path / f"{SEED7}.json"
    path.write_text(
        path.read_text().replace('"sensitivity_x1000": 150', '"sensitivity_x1000": 151')
    )
    with pytest.raises(RosterError):
        load_roster(tmp_path, SEED7)
    with pytest.raises(RosterError):
        build_market(7, str(path))


def test_warmup_constants_are_the_0_4_1_window():
    assert WARMUP_BURN_IN_NS == BURN_IN_NS == 3660 * S
    assert WARMUP_CAP_NS == WINDOW_END_NS == 5700 * S


def _carrier_market(tmp_path=None, **kwargs):
    return LiveMarket(
        roster=load_roster(carrier.ROSTER_DIR, SEED7),
        warmup=True,
        session_path=None if tmp_path is None else tmp_path / "session.jsonl",
        **kwargs,
    )


def test_terminal_refuses_orders_until_warmup_reaches_window_start(tmp_path):
    """AC-608：预热到 W0 前拒单、之后开放；推进到 5700 s 仍未退出冷启动时拒绝开放（正反两侧）"""
    burn_in = 30 * S
    market = _carrier_market(tmp_path, warmup_burn_in_ns=burn_in)
    path = tmp_path / "session.jsonl"
    assert market.terminal == TERMINAL_WARMING_UP
    assert market.push_order(_MARKET) == {"accepted": False, "reason_code": TERMINAL_WARMING_UP}
    assert market.push_cancel("x") == {"accepted": False, "reason_code": TERMINAL_WARMING_UP}
    assert market.view()["terminal"]["phase"] == TERMINAL_WARMING_UP
    assert not path.exists(), "会话随终端开放而建立"

    while market.terminal == TERMINAL_WARMING_UP:
        before = market.logical_ns
        market.advance()
        assert market.orders.empty(), "预热期间被拒的载荷不入队"
    assert market.terminal == TERMINAL_OPEN
    # 载体 C 种子 7 在第一次决策后就全部退出冷启动，所以 W0 = burn-in；
    # 终端在逻辑时间第一次越过 W0 的那次 advance 后开放，不多等。
    assert market.window_start_ns == burn_in
    assert before < burn_in <= market.logical_ns
    opened_at = market.advance_index

    check = session.load_session(path)
    assert check.ok and check.actions == ()
    assert market.push_order(_MARKET) == {"accepted": True, "reason_code": "QUEUED"}
    market.advance()
    actions = session.load_session(path).actions
    assert [a["advance_index"] for a in actions] == [opened_at]
    assert market.view()["terminal"] == {
        "phase": TERMINAL_OPEN,
        "reason_code": None,
        "window_start_ns": burn_in,
        "warmup_target_ns": burn_in,
    }


def test_terminal_never_opens_when_cold_start_outlasts_the_cap(tmp_path):
    """反侧：推进到上限仍有代理带冷启动锚 → 窗口不成立、终端永不开放、会话不建立。"""
    market = _carrier_market(tmp_path, warmup_burn_in_ns=10 * S, warmup_cap_ns=20 * S)
    tail = market.kernel.committed_records_tail

    def still_anchored(count):
        # 一个始终带锚的代理：它的最后一条决策永远在冷启动里。
        stuck = {
            "event_type": "AGENT_DECIDE",
            "agent_id": "stuck-0",
            "timestamp": market.logical_ns,
            "internal_state": {"bootstrap_anchor": {"source": "fixed"}},
        }
        return [*tail(count), stuck]

    market.kernel.committed_records_tail = still_anchored
    # 有界推进：上限失效时这里变红，而不是让 warm_up() 永远转下去。
    for _ in range(200):
        market.advance()
        if market.terminal != TERMINAL_WARMING_UP:
            break
    assert market.terminal == TERMINAL_NOT_APPLICABLE
    assert market.warm_up() == TERMINAL_NOT_APPLICABLE
    assert market.terminal_reason == "COLD_START_NOT_EXITED"
    assert market.logical_ns >= 20 * S and market.window_start_ns is None
    assert market.push_order(_MARKET) == {"accepted": False, "reason_code": TERMINAL_NOT_APPLICABLE}
    assert not (tmp_path / "session.jsonl").exists()
    assert market.seal_session() is None


def test_market_death_during_warmup_closes_the_terminal(monkeypatch):
    market = _carrier_market()

    def abort(*args, **kwargs):
        raise KernelAbort("INTERNAL", "injected")

    monkeypatch.setattr(market.kernel, "run", abort)
    assert market.warm_up() == TERMINAL_NOT_APPLICABLE
    assert market.terminal_reason == "KERNEL_ABORT"


def test_cli_warms_up_roster_markets_only(tmp_path):
    assert build_market(7).terminal == TERMINAL_OPEN, "0.3.1 配置的既有入口不变"
    roster_file = str(carrier.ROSTER_DIR / f"{SEED7}.json")
    assert build_market(7, roster_file).terminal == TERMINAL_WARMING_UP
    occupied = tmp_path / "taken.jsonl"
    occupied.write_text("x")
    with pytest.raises(FileExistsError):
        build_market(7, roster_file, str(occupied))


def test_tick_seconds_help_no_longer_claims_real_time(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "（1:1 实时）" not in text
    assert "不是 1:1 实时" in text and "预热阶段不等待" in text


def test_carrier_cli_writes_the_same_file(tmp_path):
    assert carrier.main(["--seeds", "7", "--out", str(tmp_path)]) == 0
    written = tmp_path / f"{SEED7}.json"
    assert json.loads(written.read_text()) == json.loads(
        (carrier.ROSTER_DIR / f"{SEED7}.json").read_text()
    )
    assert pathlib.Path(carrier.ROSTER_DIR).is_dir()
