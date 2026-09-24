"""0.4.1 perf: the incremental bar aggregate changes cost, never the stream.

The completed-bar sequence feeds every signal family's decision, so a faster
aggregation that produced even one different bar would change what agents
decide -- and a performance fix that changes behaviour is not a performance
fix.  This drives the real live assembly twice, once on the incremental path
and once with the pre-0.4.1 full rebuild restored underneath it, and requires
the two event streams to be identical record for record.

The old implementation is restored by monkeypatching the aggregate to carry the
cumulative history and render it through ``_completed_bars_with_zero_fill``
(still in tree, still the oracle used by the unit tests).  Patching rather than
copying keeps the comparison honest: everything else in the run -- matching,
ledger, risk, the anchor -- is the same code in both passes.
"""

from __future__ import annotations

import hashlib
import json

from market_game_sim.agent import handler as H
from market_game_sim.experiment.h2.live_market import DEFAULT_LIVE_ROSTER, LiveMarket
from market_game_sim.experiment.roster import parse_roster

#: Long enough for several 60s bars to close and for zero-fill bars to appear;
#: short enough to stay a test rather than a benchmark.
LOGICAL_SECONDS = 40

BAR_NS = 60_000_000_000


def _stored_fills(world, agent_id):
    """The agent's stored history as fills, whichever shape holds it.

    0.4.1 perf (4th growth point) made the committed shape compact
    ``{"count", "cursor_from", "cursor_to"}`` and derives the fills from the
    shared public tape.  These tests assert on the history's *content* and
    *size*, both of which must survive that change, so they read through the
    same accessor the production code uses instead of assuming a list.
    """
    return H._history_fills(
        world.get("agent_bars", {}).get(agent_id),
        world,
        H._history_count(world.get("agent_bars", {}).get(agent_id)),
    )


def _stored_total(world):
    """Total fills recorded across all agents, in either shape."""
    return sum(H._history_count(h) for h in world.get("agent_bars", {}).values())


def _legacy_extend(prior_state, fills, bar_ns):
    """Pre-0.4.1 shape: keep the whole history, aggregate nothing up front."""
    history = list((prior_state or {}).get("_history", ()))
    history.extend(dict(f) if isinstance(f, dict) else f for f in fills)
    return {"_history": history, "first_bar": None, "bars": {}}


def _legacy_from_state(state, bar_ns, up_to_ts):
    """Pre-0.4.1 cost: re-aggregate the entire history on every observation."""
    return H._completed_bars_with_zero_fill(
        list(state.get("_history", ())), bar_ns=bar_ns, up_to_ts=up_to_ts
    )


def _digest(records) -> str:
    """A stream digest that ignores dict ordering but nothing else."""
    sha = hashlib.sha256()
    for record in records:
        sha.update(json.dumps(record, sort_keys=True, default=str).encode("utf-8"))
        sha.update(b"\x1e")
    return sha.hexdigest()


def _run() -> tuple[str, int, int]:
    market = LiveMarket(roster=parse_roster(DEFAULT_LIVE_ROSTER))
    for _ in range(LOGICAL_SECONDS):
        market.advance()
    records = market.kernel.committed_records
    trades = sum(1 for r in records if r.get("event_type") == "TRADE_SETTLE")
    return _digest(records), len(records), trades


def test_incremental_aggregate_reproduces_the_legacy_event_stream(monkeypatch):
    incremental_digest, incremental_count, incremental_trades = _run()

    monkeypatch.setattr(H, "_extend_bar_state", _legacy_extend)
    monkeypatch.setattr(
        H, "_bar_state_from_history", lambda history, bar_ns: _legacy_extend(None, history, bar_ns)
    )
    monkeypatch.setattr(H, "_completed_bars_from_state", _legacy_from_state)
    legacy_digest, legacy_count, legacy_trades = _run()

    assert incremental_count == legacy_count
    assert incremental_trades == legacy_trades
    # The market has to actually trade, or the comparison proves nothing.
    assert incremental_trades > 0
    assert incremental_digest == legacy_digest


def _materialising_enqueue(real_enqueue):
    """Restage the history snapshot the pre-0.4.1 way: one cumulative list.

    The handler now stages ``(base length, this interval's fills)`` and the
    kernel truncates-then-extends.  This wrapper rebuilds the materialised
    cumulative list the old code staged and hands it over under the legacy
    ``agent_history`` key, so the kernel takes its legacy branch.  Everything
    else about the run is unchanged -- only the snapshot mechanism differs.
    """
    histories: dict[str, list] = {}

    def enqueue(self, event):
        pending = event.get("_pending_agent_state")
        if pending is not None and "agent_history_base" in pending:
            agent_id = pending["agent_id"]
            prior = histories.get(agent_id, [])
            cumulative = prior[: pending["agent_history_base"]] + list(
                pending["agent_history_extend"]
            )
            histories[agent_id] = cumulative
            pending = dict(pending)
            for key in ("agent_history_base", "agent_history_extend", "agent_history_len"):
                pending.pop(key)
            pending["agent_history"] = cumulative
            event["_pending_agent_state"] = pending
        return real_enqueue(self, event)

    return enqueue


def test_length_based_history_snapshot_reproduces_the_copied_snapshot(monkeypatch):
    """Half 2: truncate-then-extend must equal replace-with-a-fresh-copy.

    The risk this covers is overlapping observations and retries: the old code
    replaced the agent's history wholesale, and the cheap version only matches
    if each observation truncates to exactly the base it observed.
    """
    from market_game_sim.kernel.runner import EventKernel

    new_digest, new_count, new_trades = _run()

    monkeypatch.setattr(EventKernel, "enqueue", _materialising_enqueue(EventKernel.enqueue))
    legacy_digest, legacy_count, legacy_trades = _run()

    assert new_count == legacy_count
    assert new_trades == legacy_trades
    assert new_trades > 0
    assert new_digest == legacy_digest


def test_history_snapshot_content_matches_the_copied_snapshot(monkeypatch):
    """The stored history itself, not just the stream it produced."""
    from market_game_sim.kernel.runner import EventKernel

    market = LiveMarket(roster=parse_roster(DEFAULT_LIVE_ROSTER))
    for _ in range(LOGICAL_SECONDS):
        market.advance()
    new_bars = {a: _stored_fills(market.world, a) for a in market.world.get("agent_bars", {})}

    monkeypatch.setattr(EventKernel, "enqueue", _materialising_enqueue(EventKernel.enqueue))
    legacy_market = LiveMarket(roster=parse_roster(DEFAULT_LIVE_ROSTER))
    for _ in range(LOGICAL_SECONDS):
        legacy_market.advance()
    legacy_bars = {
        a: _stored_fills(legacy_market.world, a) for a in legacy_market.world.get("agent_bars", {})
    }

    assert new_bars and legacy_bars
    assert sum(len(h) for h in new_bars.values()) > 0
    # 0.4.1 perf (4th growth point): the compact record stores a cursor range
    # rather than the fills, so this compares what the range *derives* against
    # the fills the legacy path materialised -- the claim is that no agent
    # loses or gains a single trade from its history, not that the container
    # is the same object shape.
    assert new_bars == legacy_bars


def test_advance_never_rebuilds_bars_from_the_whole_history(monkeypatch):
    """The determinism guard for this class of defect.

    A wall-clock budget is machine-dependent and a short run need not exceed it
    even on an O(n^2) path -- 0.4.1 found three of these in a row, and each time
    the clock gate stayed green while the growth was already there.  So the
    thing that must not happen is asserted directly: driving the live market
    must never re-aggregate an agent's whole trade history.  Restoring that call
    in ``handle_agent_observe`` turns this red immediately.
    """
    calls = 0
    real = H._completed_bars_with_zero_fill

    def counting(trades, *args, **kwargs):
        nonlocal calls
        calls += 1
        return real(trades, *args, **kwargs)

    monkeypatch.setattr(H, "_completed_bars_with_zero_fill", counting)

    market = LiveMarket(roster=parse_roster(DEFAULT_LIVE_ROSTER))
    for _ in range(LOGICAL_SECONDS):
        market.advance()

    trades = sum(
        1 for r in market.kernel.committed_records if r.get("event_type") == "TRADE_SETTLE"
    )
    # The run has to be a real one, or "never called" proves nothing.
    assert trades > 0
    assert _stored_total(market.world) > 0
    assert calls == 0


def test_per_observation_fill_reads_do_not_scale_with_history(monkeypatch):
    """The other half: reads per observation must not grow with the history.

    Counted over the back half of a run (where histories are longest) against
    the front half: the fold touches this interval's fills only, so the totals
    track the trades that arrived, not the trades already stored.
    """
    reads: list[int] = []
    real = H._fill_fields

    def counting(fill):
        reads.append(1)
        return real(fill)

    market = LiveMarket(roster=parse_roster(DEFAULT_LIVE_ROSTER))
    monkeypatch.setattr(H, "_fill_fields", counting)

    per_second = []
    stored = []
    for _ in range(LOGICAL_SECONDS):
        reads.clear()
        market.advance()
        per_second.append(len(reads))
        stored.append(_stored_total(market.world))

    half = LOGICAL_SECONDS // 2
    assert stored[-1] > stored[half] > 0, "history must actually grow, or this proves nothing"
    growth = stored[-1] / stored[half]
    front = sum(per_second[:half]) or 1
    back = sum(per_second[half:])
    # History grew by `growth`; the per-observation reads must not follow it.
    assert back <= front * 2, (
        f"fill reads tracked the history: front={front} back={back} history_growth={growth:.2f}"
    )


def test_pending_snapshot_carries_an_interval_not_a_cumulative_history(monkeypatch):
    """Guard for the snapshot half: staging the cumulative list must stay gone.

    The old shape put every trade the agent had ever seen on every queued
    decision.  Restoring it would not change any result -- the kernel still
    honours that legacy key -- so only a shape assertion catches the
    regression; the wall clock would just quietly grow again.
    """
    from market_game_sim.kernel.runner import EventKernel

    real_enqueue = EventKernel.enqueue
    seen: list[dict] = []

    def recording(self, event):
        pending = event.get("_pending_agent_state")
        if pending is not None:
            seen.append(pending)
        return real_enqueue(self, event)

    monkeypatch.setattr(EventKernel, "enqueue", recording)

    market = LiveMarket(roster=parse_roster(DEFAULT_LIVE_ROSTER))
    for _ in range(LOGICAL_SECONDS):
        market.advance()

    staged = [p for p in seen if "agent_history_base" in p or "agent_history" in p]
    assert staged, "no observation staged a history snapshot -- the run proves nothing"
    stored = _stored_total(market.world)
    assert stored > 0
    assert all("agent_history" not in p for p in staged)
    # Each snapshot carries its own interval only; the biggest one must stay far
    # below the history the agents accumulated.
    biggest = max(len(p["agent_history_extend"]) for p in staged)
    assert biggest < stored


def test_the_comparison_can_fail(monkeypatch):
    """Negative control: a deliberately wrong aggregate must break the digest,
    otherwise the test above would pass no matter what the fold did."""
    baseline_digest, _, _ = _run()

    def dropping_extend(prior_state, fills, bar_ns):
        """Drop the last fill of each interval -- a subtly wrong aggregate."""
        return H._extend_bar_state(prior_state, list(fills)[:-1], bar_ns)

    monkeypatch.setattr(H, "_extend_bar_state", dropping_extend)
    broken_digest, _, _ = _run()

    assert broken_digest != baseline_digest
