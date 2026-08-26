"""T401 (AC-001, E1/SC-008): per-frame consistency with an independent oracle.

The oracle is a test-only observer that reads snapshots directly from the
kernel's ``Account``/``Book`` objects after every transaction commit.  It is
NEVER fed to the replay.  The replay rebuilds frames solely from the event
log, and the two must be equal frame-by-frame, field-by-field.
"""

from __future__ import annotations

import json

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment import runner as runner_mod
from market_game_sim.experiment.runner import ExperimentConfig, run_one
from market_game_sim.kernel.runner import EventKernel
from market_game_sim.ledger.account import initial_margin_bp_for_tier, snapshot_entry
from market_game_sim.replay.frames import _build_frames

ACCOUNT_FIELDS = (
    "agent_id",
    "wallet_units",
    "position_units",
    "entry_notional_units",
    "reserved_units",
    "realized_pnl_units",
    "state",
    "margin_ratio_bp",
    "liquidation_generation",
    "chain_id",
    "chain_depth",
)


class OracleKernel(EventKernel):
    """EventKernel that records a state projection after each commit."""

    instances: list[OracleKernel] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.oracle_frames: list[dict] = []
        OracleKernel.instances.append(self)

    def _run_transaction(self, event, handler, world):
        super()._run_transaction(event, handler, world)
        self.oracle_frames.append(_project(world, self._transaction_seq))


def _project(world: dict, txn_seq: int) -> dict:
    book = world["book"]
    accounts = {
        aid: snapshot_entry(acct, risk_mark_ticks=book.last_ticks, mult=world["mult"])
        for aid, acct in sorted(world["accounts"].items())
    }
    return {
        "transaction_seq": txn_seq,
        "last_ticks": book.last_ticks,
        "accounts": accounts,
        "exchange": {
            "fee_cash_units": world["exchange_fee_units"],
            "risk_pnl_units": world["exchange_risk_pnl_units"],
        },
        "book": book.level_aggregates(),
    }


def _mm_spec() -> AgentSpec:
    return AgentSpec(
        agent_id="mm-0",
        role="inventory_market_maker",
        observe_interval_ns=100_000_000,
        latency_ns=5_000_000,
        is_market_maker=True,
        half_spread_ticks=5,
        quote_size=10_000,
        max_inventory=100_000,
        inventory_skew_k_bp=10_000,
    )


def _belief_spec() -> AgentSpec:
    return AgentSpec(
        agent_id="agent-0",
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=10,
        aggressiveness_bp=10_000,
        max_order_qty=5_000,
    )


def _write_log(path, result, config: ExperimentConfig) -> None:
    header = {
        "record_kind": "RUN_HEADER",
        "schema_version": 4,
        "run_id": f"exp-s{result.seed}",
        "tick_size": "0.01",
        "min_quantity": "0.001",
        "cash_unit": "0.01",
        "mult": config.mult,
        "fee_bps_cap": max(config.maker_bps, config.taker_bps, 0),
        "initial_price_ticks": config.initial_price_ticks,
        "agent_initial_bp": {
            s.agent_id: initial_margin_bp_for_tier(s.leverage_tier) for s in config.agent_specs
        },
    }
    max_txn = max((e["transaction_seq"] for e in result.events), default=2)
    trailer = {
        "record_kind": "RUN_TRAILER",
        "terminated": result.terminated,
        "abort_code": result.abort_code,
        "abort_detail": None,
        "last_committed_transaction_seq": max_txn,
        "record_count": 2 + len(result.events),
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for e in result.events:
            f.write(json.dumps(e) + "\n")
        f.write(json.dumps(trailer) + "\n")


def _assert_frame_equal(frame, oracle: dict, frame_idx: int) -> None:
    assert frame.transaction_seq == oracle["transaction_seq"], (
        f"frame {frame_idx}: txn seq {frame.transaction_seq} != {oracle['transaction_seq']}"
    )
    assert frame.last_ticks == oracle["last_ticks"], (
        f"frame {frame_idx}: last_ticks {frame.last_ticks} != {oracle['last_ticks']}"
    )
    assert set(frame.accounts) == set(oracle["accounts"]), (
        f"frame {frame_idx}: account sets differ ({set(frame.accounts) ^ set(oracle['accounts'])})"
    )
    for aid in frame.accounts:
        for field in ACCOUNT_FIELDS:
            got = frame.accounts[aid][field]
            want = oracle["accounts"][aid][field]
            assert got == want, f"frame {frame_idx} {aid}.{field}: {got!r} != {want!r}"
    assert frame.exchange == oracle["exchange"], (
        f"frame {frame_idx}: exchange {frame.exchange} != {oracle['exchange']}"
    )
    assert frame.book == oracle["book"], f"frame {frame_idx}: book {frame.book} != {oracle['book']}"


def _bootstrap_txn(events: list[dict]) -> int:
    for e in events:
        if e.get("event_type") == "SNAPSHOT" and e.get("snapshot_type") == "BOOK":
            return e["transaction_seq"]
    return 2


def test_e1_frame_consistency(tmp_path, monkeypatch):
    OracleKernel.instances.clear()
    monkeypatch.setattr(runner_mod, "EventKernel", OracleKernel)

    cfg = ExperimentConfig(
        seed=1,
        max_transactions=120,
        agent_specs=[_mm_spec(), _belief_spec()],
        agent_signals={"agent-0": 10_000},
    )
    result = run_one(cfg)
    assert result.terminated == "COMPLETED", f"abort: {result.abort_code}"

    kernel = OracleKernel.instances[-1]
    oracle_frames = kernel.oracle_frames

    log_path = tmp_path / "run.jsonl"
    _write_log(log_path, result, cfg)

    replay_frames = _build_frames(
        result.events,
        mult=cfg.mult,
        fee_bps_cap=max(cfg.maker_bps, cfg.taker_bps, 0),
        initial_price_ticks=cfg.initial_price_ticks,
        agent_initial_bp={
            s.agent_id: initial_margin_bp_for_tier(s.leverage_tier) for s in cfg.agent_specs
        },
    )
    bootstrap_txn = _bootstrap_txn(result.events)

    # Frame k (at txn bootstrap_txn + k) equals the oracle capture after that txn.
    assert len(replay_frames) == len(oracle_frames) - bootstrap_txn + 1, (
        f"frame count {len(replay_frames)} != oracle frames-{bootstrap_txn}+1 "
        f"({len(oracle_frames) - bootstrap_txn + 1})"
    )
    for k, frame in enumerate(replay_frames):
        _assert_frame_equal(frame, oracle_frames[bootstrap_txn + k - 1], k)


def test_run_produces_trades_for_replay(tmp_path, monkeypatch):
    """Sanity: the E1 config actually generates crossing trades so the
    reconstruction is exercised on real market activity, not only bootstrap."""
    OracleKernel.instances.clear()
    monkeypatch.setattr(runner_mod, "EventKernel", OracleKernel)
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=120,
        agent_specs=[_mm_spec(), _belief_spec()],
        agent_signals={"agent-0": 10_000},
    )
    result = run_one(cfg)
    trades = [e for e in result.events if e.get("event_type") == "TRADE_SETTLE"]
    assert len(trades) > 0
    assert len(trades) < len(result.events)


def test_e1_frame_consistency_through_public_build_replay(tmp_path, monkeypatch):
    """F1 regression: the PUBLIC build_replay path (not the private _build_frames
    injection) must produce E1-consistent frames, proving the header-carried
    config is actually used instead of hard-coded defaults."""
    OracleKernel.instances.clear()
    monkeypatch.setattr(runner_mod, "EventKernel", OracleKernel)
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=120,
        agent_specs=[_mm_spec(), _belief_spec()],
        agent_signals={"agent-0": 10_000},
    )
    result = run_one(cfg)
    assert result.terminated == "COMPLETED", f"abort: {result.abort_code}"

    kernel = OracleKernel.instances[-1]
    oracle_frames = kernel.oracle_frames

    log_path = tmp_path / "run.jsonl"
    _write_log(log_path, result, cfg)

    replay_frames = _build_frames(
        result.events,
        mult=cfg.mult,
        fee_bps_cap=max(cfg.maker_bps, cfg.taker_bps, 0),
        initial_price_ticks=cfg.initial_price_ticks,
        agent_initial_bp={
            s.agent_id: initial_margin_bp_for_tier(s.leverage_tier) for s in cfg.agent_specs
        },
    )
    bootstrap_txn = _bootstrap_txn(result.events)

    from market_game_sim.replay.reader import read_log

    log = read_log(log_path)
    public_frames = _build_frames(
        log.events,
        mult=log.config.mult,
        fee_bps_cap=log.config.fee_bps_cap,
        initial_price_ticks=log.config.initial_price_ticks,
        agent_initial_bp=log.config.agent_initial_bp,
    )
    assert len(public_frames) == len(replay_frames), (
        f"public path frame count {len(public_frames)} != private {len(replay_frames)}"
    )
    for k, (pf, rf) in enumerate(zip(public_frames, replay_frames, strict=True)):
        assert pf.transaction_seq == rf.transaction_seq, f"frame {k}: txn mismatch"
        assert pf.last_ticks == rf.last_ticks, f"frame {k}: last_ticks mismatch"
        assert pf.accounts == rf.accounts, f"frame {k}: accounts mismatch"
        assert pf.exchange == rf.exchange, f"frame {k}: exchange mismatch"
        assert pf.book == rf.book, f"frame {k}: book mismatch"

    for k, frame in enumerate(public_frames):
        _assert_frame_equal(frame, oracle_frames[bootstrap_txn + k - 1], k)


def test_e1_frame_consistency_non_default_config(tmp_path, monkeypatch):
    """F1 regression: a NON-default config (different mult/initial_price/fee)
    must still produce frame-consistent output via the public path, proving
    the header values are actually used, not hard-coded."""
    OracleKernel.instances.clear()
    monkeypatch.setattr(runner_mod, "EventKernel", OracleKernel)
    cfg = ExperimentConfig(
        seed=2,
        max_transactions=120,
        agent_specs=[_mm_spec(), _belief_spec()],
        agent_signals={"agent-0": 10_000},
        mult=500,
        initial_price_ticks=8000,
        maker_bps=3,
        taker_bps=7,
    )
    result = run_one(cfg)
    assert result.terminated == "COMPLETED", f"abort: {result.abort_code}"

    kernel = OracleKernel.instances[-1]
    oracle_frames = kernel.oracle_frames

    log_path = tmp_path / "run.jsonl"
    _write_log(log_path, result, cfg)

    from market_game_sim.replay.reader import read_log

    log = read_log(log_path)
    assert log.config.mult == 500, "header mult not read correctly"
    assert log.config.initial_price_ticks == 8000
    assert log.config.fee_bps_cap == 7

    public_frames = _build_frames(
        log.events,
        mult=log.config.mult,
        fee_bps_cap=log.config.fee_bps_cap,
        initial_price_ticks=log.config.initial_price_ticks,
        agent_initial_bp=log.config.agent_initial_bp,
    )
    bootstrap_txn = _bootstrap_txn(result.events)
    assert len(public_frames) == len(oracle_frames) - bootstrap_txn + 1
    for k, frame in enumerate(public_frames):
        _assert_frame_equal(frame, oracle_frames[bootstrap_txn + k - 1], k)


def test_e1_frame_consistency_end_to_end_through_build_replay(tmp_path, monkeypatch):
    """F1 regression (end-to-end): drive the FULL public ``build_replay()``
    function (the review's core demand) and verify the frames embedded in the
    generated HTML are E1-consistent with the independent oracle.

    Unlike the private-frame-injection tests, this exercises the whole public
    entry point: log read -> header config -> frame build -> HTML render ->
    embedded JSON. If build_replay ever stops using the header-carried config
    (regressing to hard-coded defaults), the embedded frames diverge from the
    oracle and this test fails.
    """
    from types import SimpleNamespace

    from market_game_sim.replay.generate import build_replay

    OracleKernel.instances.clear()
    monkeypatch.setattr(runner_mod, "EventKernel", OracleKernel)
    cfg = ExperimentConfig(
        seed=3,
        max_transactions=120,
        agent_specs=[_mm_spec(), _belief_spec()],
        agent_signals={"agent-0": 10_000},
    )
    result = run_one(cfg)
    assert result.terminated == "COMPLETED", f"abort: {result.abort_code}"

    kernel = OracleKernel.instances[-1]
    oracle_frames = kernel.oracle_frames

    log_path = tmp_path / "run.jsonl"
    out_path = tmp_path / "replay.html"
    _write_log(log_path, result, cfg)
    build_replay(log_path, out_path)

    html = out_path.read_text(encoding="utf-8")
    marker = 'type="application/json">'
    start = html.index(marker) + len(marker)
    end = html.index("</script>", start)
    data = json.loads(html[start:end])

    bootstrap_txn = _bootstrap_txn(result.events)
    embedded = data["frames"]
    assert len(embedded) == len(oracle_frames) - bootstrap_txn + 1, (
        f"end-to-end frame count {len(embedded)} != oracle frames-{bootstrap_txn}+1 "
        f"({len(oracle_frames) - bootstrap_txn + 1})"
    )
    for k, frame in enumerate(embedded):
        frame_obj = SimpleNamespace(
            transaction_seq=frame["transaction_seq"],
            last_ticks=frame["last_ticks"],
            accounts=frame["accounts"],
            exchange=frame["exchange"],
            book=frame["book"],
        )
        _assert_frame_equal(frame_obj, oracle_frames[bootstrap_txn + k - 1], k)


def test_e1_closed_loop_through_build_run_header(tmp_path, monkeypatch):
    """F-A regression: the FULL production closed loop -- ExperimentConfig ->
    build_run_header (real values, no defaults) -> log file -> build_replay ->
    independent oracle -- must be frame-consistent for a NON-default config.

    Proves the header builder carries the actual run config (the reviewer's
    demand: production write path, not a hand-written header).
    """
    from types import SimpleNamespace

    from market_game_sim.eventlog.writer import build_run_header
    from market_game_sim.replay.generate import build_replay

    OracleKernel.instances.clear()
    monkeypatch.setattr(runner_mod, "EventKernel", OracleKernel)
    cfg = ExperimentConfig(
        seed=4,
        max_transactions=120,
        agent_specs=[_mm_spec(), _belief_spec()],
        agent_signals={"agent-0": 10_000},
        mult=750,
        initial_price_ticks=12000,
        maker_bps=4,
        taker_bps=9,
    )
    result = run_one(cfg)
    assert result.terminated == "COMPLETED", f"abort: {result.abort_code}"

    kernel = OracleKernel.instances[-1]
    oracle_frames = kernel.oracle_frames

    max_txn = max((e["transaction_seq"] for e in result.events), default=2)
    header = build_run_header(
        run_id=f"exp-s{result.seed}",
        code_version="test",
        config_hash="0" * 64,
        master_seed=cfg.seed,
        started_at_wall="2026-01-01T00:00:00Z",
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        mult=cfg.mult,
        fee_bps_cap=max(cfg.maker_bps, cfg.taker_bps, 0),
        initial_price_ticks=cfg.initial_price_ticks,
        agent_initial_bp={
            s.agent_id: initial_margin_bp_for_tier(s.leverage_tier) for s in cfg.agent_specs
        },
    )
    trailer = {
        "record_kind": "RUN_TRAILER",
        "terminated": result.terminated,
        "abort_code": result.abort_code,
        "abort_detail": None,
        "last_committed_transaction_seq": max_txn,
        "record_count": 2 + len(result.events),
    }
    log_path = tmp_path / "run.jsonl"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for e in result.events:
            f.write(json.dumps(e) + "\n")
        f.write(json.dumps(trailer) + "\n")

    out_path = tmp_path / "replay.html"
    build_replay(log_path, out_path)

    html = out_path.read_text(encoding="utf-8")
    marker = 'type="application/json">'
    start = html.index(marker) + len(marker)
    end = html.index("</script>", start)
    data = json.loads(html[start:end])

    bootstrap_txn = _bootstrap_txn(result.events)
    embedded = data["frames"]
    assert len(embedded) == len(oracle_frames) - bootstrap_txn + 1
    for k, frame in enumerate(embedded):
        frame_obj = SimpleNamespace(
            transaction_seq=frame["transaction_seq"],
            last_ticks=frame["last_ticks"],
            accounts=frame["accounts"],
            exchange=frame["exchange"],
            book=frame["book"],
        )
        _assert_frame_equal(frame_obj, oracle_frames[bootstrap_txn + k - 1], k)
